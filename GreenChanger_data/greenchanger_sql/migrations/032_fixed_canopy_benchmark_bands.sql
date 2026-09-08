BEGIN;

-- Canopy is now classified against two published Victorian reference values,
-- rather than against distribution-dependent Melbourne terciles. Historical
-- schemes remain in the tables for auditability; this migration changes the
-- effective view and the function used to create future schemes.
ALTER TABLE environmental_classification_scheme
    DROP CONSTRAINT IF EXISTS environmental_classification_scheme_method_check;

ALTER TABLE environmental_classification_scheme
    ADD CONSTRAINT environmental_classification_scheme_method_check
    CHECK (method IN ('tercile_percentile_cont', 'fixed_evidence_bands'));

CREATE OR REPLACE VIEW current_environmental_classification_threshold AS
SELECT
    scheme.classification_scheme_id,
    scheme.version_label,
    scheme.analysis_area_id,
    'fixed_evidence_bands'::TEXT AS method,
    'fixed_temperature_display_bands_and_evidence_backed_canopy_progress_bands'::TEXT
        AS classification_scope,
    scheme.calculated_at,
    threshold.metric_code,
    threshold.source_dataset_version_id,
    CASE WHEN threshold.metric_code = 'heat' THEN 27.0
         WHEN threshold.metric_code = 'canopy' THEN 15.3
         ELSE threshold.lower_threshold END AS lower_threshold,
    CASE WHEN threshold.metric_code = 'heat' THEN 30.0
         WHEN threshold.metric_code = 'canopy' THEN 30.0
         ELSE threshold.upper_threshold END AS upper_threshold,
    threshold.unit,
    threshold.sample_count,
    threshold.low_label,
    threshold.medium_label,
    threshold.high_label,
    threshold.missing_label,
    CASE
        WHEN threshold.metric_code = 'heat' THEN
            'GreenChanger display bands: Low <=27 C, Medium >27 C and <=30 C, High >30 C. Application-defined only; not a BOM heatwave, health-risk or comfort classification.'
        WHEN threshold.metric_code = 'canopy' THEN
            'Canopy progress bands: Low <15.3%, Medium >=15.3% and <30%, High >=30%. The 15.3% value is the official metropolitan Melbourne 2018 tree-canopy baseline and 30% is the Plan for Victoria urban-area target. Progress context only; not proof of property-level compliance, and source imagery spans 2013-2020.'
        ELSE threshold.explanation
    END AS explanation
FROM environmental_classification_scheme AS scheme
JOIN environmental_classification_threshold AS threshold
  USING (classification_scheme_id)
WHERE scheme.status = 'active';

CREATE OR REPLACE FUNCTION refresh_environmental_classifications(
    p_version_label TEXT
)
RETURNS UUID
LANGUAGE plpgsql
AS $function$
DECLARE
    v_scheme_id UUID;
    v_analysis_area_id UUID;
    v_threshold_count INTEGER;
BEGIN
    IF p_version_label IS NULL OR BTRIM(p_version_label) = '' THEN
        RAISE EXCEPTION 'classification version label is required';
    END IF;
    IF EXISTS (
        SELECT 1 FROM environmental_classification_scheme
        WHERE version_label = BTRIM(p_version_label)
    ) THEN
        RAISE EXCEPTION 'classification version % already exists', BTRIM(p_version_label);
    END IF;

    SELECT analysis_area_id
    INTO STRICT v_analysis_area_id
    FROM analysis_area
    WHERE source_area_code = '2GMEL' AND source_year = 2026;

    INSERT INTO environmental_classification_scheme (
        version_label, analysis_area_id, method, classification_scope,
        status, notes
    ) VALUES (
        BTRIM(p_version_label), v_analysis_area_id,
        'fixed_evidence_bands',
        'fixed_temperature_display_bands_and_evidence_backed_canopy_progress_bands',
        'draft',
        'Canopy: Low below the official 15.3% metropolitan Melbourne baseline; Medium from 15.3% to below the 30% Plan for Victoria urban target; High at or above 30%. Temperature retains application-defined 27/30 C display bands. Missing values are Unavailable.'
    )
    RETURNING classification_scheme_id INTO v_scheme_id;

    INSERT INTO environmental_classification_threshold (
        classification_scheme_id, metric_code, source_dataset_version_id,
        lower_threshold, upper_threshold, unit, sample_count, explanation
    )
    SELECT
        v_scheme_id, 'heat', dataset_version_id, 27.0, 30.0,
        'degC_land_surface_temperature', COUNT(*),
        'GreenChanger display bands: Low <=27 C, Medium >27 C and <=30 C, High >30 C. Application-defined only; not a BOM heatwave, health-risk or comfort classification.'
    FROM latest_greater_melbourne_heat_baseline
    WHERE baseline_surface_temperature_c IS NOT NULL
    GROUP BY dataset_version_id;

    INSERT INTO environmental_classification_threshold (
        classification_scheme_id, metric_code, source_dataset_version_id,
        lower_threshold, upper_threshold, unit, sample_count, explanation
    )
    SELECT
        v_scheme_id, 'canopy', dataset_version_id, 15.3, 30.0,
        'percent_neighbourhood_canopy', COUNT(*),
        'Canopy progress bands: Low <15.3%, Medium >=15.3% and <30%, High >=30%. Based on the official metropolitan Melbourne 2018 tree-canopy baseline and Plan for Victoria urban-area target; not proof of property-level compliance.'
    FROM latest_greater_melbourne_canopy_baseline
    WHERE canopy_percentage IS NOT NULL
    GROUP BY dataset_version_id;

    SELECT COUNT(*) INTO v_threshold_count
    FROM environmental_classification_threshold
    WHERE classification_scheme_id = v_scheme_id;

    IF v_threshold_count <> 2 THEN
        RAISE EXCEPTION
            'expected heat and canopy thresholds but calculated % row(s)',
            v_threshold_count;
    END IF;

    UPDATE environmental_classification_scheme
    SET status = 'retired'
    WHERE analysis_area_id = v_analysis_area_id AND status = 'active';

    UPDATE environmental_classification_scheme
    SET status = 'active', calculated_at = CURRENT_TIMESTAMP
    WHERE classification_scheme_id = v_scheme_id;

    RETURN v_scheme_id;
END;
$function$;

COMMENT ON FUNCTION refresh_environmental_classifications(TEXT) IS
    'Creates and activates a versioned fixed-band scheme: temperature uses GreenChanger 27/30 C display bands; canopy uses the official 15.3% metropolitan baseline and 30% Plan for Victoria urban target.';

CREATE OR REPLACE FUNCTION classify_environmental_value(
    p_metric_code TEXT, p_value NUMERIC, p_version_label TEXT DEFAULT NULL
)
RETURNS TEXT
LANGUAGE SQL
STABLE
PARALLEL SAFE
RETURN CASE
    WHEN p_value IS NULL OR p_value::TEXT IN ('NaN', 'Infinity', '-Infinity')
        THEN 'Unavailable'
    WHEN p_metric_code = 'heat' THEN classify_temperature_band(p_value)
    WHEN p_metric_code = 'canopy' THEN classify_canopy_benchmark(p_value)
    ELSE 'Unavailable'
END;

COMMENT ON FUNCTION classify_environmental_value(TEXT, NUMERIC, TEXT) IS
    'Uses fixed GreenChanger 27/30 C display bands for heat and evidence-backed 15.3/30% progress bands for canopy. Missing, non-finite and unknown metrics return Unavailable.';

COMMIT;
