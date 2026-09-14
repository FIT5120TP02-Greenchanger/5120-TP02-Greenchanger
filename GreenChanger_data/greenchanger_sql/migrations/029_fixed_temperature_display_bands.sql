BEGIN;

CREATE OR REPLACE VIEW current_environmental_classification_threshold AS
SELECT
    scheme.classification_scheme_id,
    scheme.version_label,
    scheme.analysis_area_id,
    CASE WHEN threshold.metric_code = 'heat'
         THEN 'fixed_temperature_display_bands'
         ELSE scheme.method END AS method,
    CASE WHEN threshold.metric_code = 'heat'
         THEN 'application_defined_temperature_display_band'
         ELSE scheme.classification_scope END AS classification_scope,
    scheme.calculated_at,
    threshold.metric_code,
    threshold.source_dataset_version_id,
    CASE WHEN threshold.metric_code = 'heat' THEN 27.0
         ELSE threshold.lower_threshold END AS lower_threshold,
    CASE WHEN threshold.metric_code = 'heat' THEN 30.0
         ELSE threshold.upper_threshold END AS upper_threshold,
    threshold.unit,
    threshold.sample_count,
    threshold.low_label,
    threshold.medium_label,
    threshold.high_label,
    threshold.missing_label,
    CASE WHEN threshold.metric_code = 'heat' THEN
        'GreenChanger display bands: Low <=27 C, Medium >27 C and <=30 C, High >30 C. Application-defined only; not a BOM heatwave, health-risk or comfort classification.'
    ELSE threshold.explanation END AS explanation
FROM environmental_classification_scheme AS scheme
JOIN environmental_classification_threshold AS threshold
  USING (classification_scheme_id)
WHERE scheme.status = 'active';

CREATE OR REPLACE FUNCTION classify_temperature_band(p_temperature_c NUMERIC)
RETURNS TEXT
LANGUAGE SQL
IMMUTABLE
PARALLEL SAFE
RETURN CASE
    WHEN p_temperature_c IS NULL
      OR p_temperature_c::TEXT IN ('NaN', 'Infinity', '-Infinity')
        THEN 'Unavailable'
    WHEN p_temperature_c <= 27.0 THEN 'Low'
    WHEN p_temperature_c <= 30.0 THEN 'Medium'
    ELSE 'High'
END;

COMMENT ON FUNCTION classify_temperature_band(NUMERIC) IS
    'GreenChanger product display bands: Low <=27 C, Medium >27 C and <=30 C, High >30 C. These are application-defined display bands, not BOM heatwave, health-risk or comfort classifications.';

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
    ELSE COALESCE((
        SELECT CASE
            WHEN p_value <= threshold.lower_threshold THEN threshold.low_label
            WHEN p_value <= threshold.upper_threshold THEN threshold.medium_label
            ELSE threshold.high_label
        END
        FROM current_environmental_classification_threshold AS threshold
        WHERE threshold.metric_code = p_metric_code
          AND (p_version_label IS NULL OR threshold.version_label = p_version_label)
        LIMIT 1
    ), 'Unavailable')
END;

COMMENT ON FUNCTION classify_environmental_value(TEXT, NUMERIC, TEXT) IS
    'Uses fixed GreenChanger 27/30 C display bands for heat and the active versioned Melbourne threshold scheme for canopy. Missing and non-finite values return Unavailable.';

COMMIT;
