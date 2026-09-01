BEGIN;

ALTER TABLE environmental_classification_reference
    -- PostgreSQL shortens migration 020's generated name to 63 characters.
    DROP CONSTRAINT environmental_classification_referen_classification_label_check;

ALTER TABLE environmental_classification_reference
    ALTER COLUMN classification_label DROP NOT NULL,
    ADD COLUMN evidence_role TEXT NOT NULL DEFAULT 'classification_threshold'
        CHECK (evidence_role IN (
            'classification_threshold', 'historical_percentile_context_only'
        )),
    ADD COLUMN minimum_consecutive_days INTEGER
        CHECK (minimum_consecutive_days IS NULL OR minimum_consecutive_days > 0),
    ADD COLUMN status TEXT NOT NULL DEFAULT 'historical_context';

UPDATE environmental_classification_reference
SET classification_label = NULL,
    evidence_role = 'historical_percentile_context_only',
    minimum_consecutive_days = 2,
    status = 'historical_context',
    limitation = 'The 27.2 C percentile requires two or more consecutive summer days. It is historical percentile context only and is not used to classify a single forecast pair.'
WHERE metric_code = 'daily_mean_air_temperature'
  AND threshold_code = 'elevated_daily_mean';

UPDATE environmental_classification_reference
SET classification_label = 'At or above historical 30 C threshold',
    evidence_role = 'classification_threshold',
    status = 'historical_context',
    limitation = 'Historical Victorian Central District context only. The system ended in 2021-22 and is not comparable with the current BOM national heatwave warning.'
WHERE metric_code = 'daily_mean_air_temperature'
  AND threshold_code = 'historical_central_heat_health';

DROP FUNCTION classify_melbourne_daily_mean_air_temperature(NUMERIC, NUMERIC);

CREATE FUNCTION classify_melbourne_daily_mean_air_temperature(
    p_forecast_maximum_c NUMERIC,
    p_following_overnight_minimum_c NUMERIC
)
RETURNS JSONB
LANGUAGE SQL
IMMUTABLE
PARALLEL SAFE
RETURN JSONB_BUILD_OBJECT(
    'classification', CASE
        WHEN p_forecast_maximum_c IS NULL
          OR p_following_overnight_minimum_c IS NULL
          OR p_forecast_maximum_c::TEXT IN ('NaN', 'Infinity', '-Infinity')
          OR p_following_overnight_minimum_c::TEXT IN ('NaN', 'Infinity', '-Infinity')
            THEN 'Unavailable'
        WHEN (p_forecast_maximum_c + p_following_overnight_minimum_c) / 2.0 >= 30.0
            THEN 'At or above historical 30 C threshold'
        ELSE 'Below historical 30 C threshold'
    END,
    'daily_mean_c', CASE
        WHEN p_forecast_maximum_c IS NULL
          OR p_following_overnight_minimum_c IS NULL
          OR p_forecast_maximum_c::TEXT IN ('NaN', 'Infinity', '-Infinity')
          OR p_following_overnight_minimum_c::TEXT IN ('NaN', 'Infinity', '-Infinity')
            THEN NULL
        ELSE ROUND((p_forecast_maximum_c + p_following_overnight_minimum_c) / 2.0, 3)
    END,
    'method', 'historical_victorian_central_daily_mean_threshold',
    'status', 'historical_context',
    'limitation', 'Historical Victorian Central District context only. The system ended in 2021-22 and is not comparable with the current BOM heatwave warning. The 27.2 C research percentile requires two or more consecutive days and is not used to classify this one-day pair.',
    'source', JSONB_BUILD_OBJECT(
        'title', 'Planning for extreme heat and heatwaves',
        'publisher', 'Victorian Department of Health',
        'url', 'https://www.health.vic.gov.au/environmental-health/planning-for-extreme-heat-and-heatwaves',
        'locator', 'Calculating the average temperature; Figure 1'
    ),
    'historical_percentile_context', JSONB_BUILD_OBJECT(
        'threshold_c', 27.2,
        'minimum_consecutive_days', 2,
        'used_for_this_classification', FALSE,
        'source', JSONB_BUILD_OBJECT(
            'title', 'The impact of heatwaves on mortality in Australia: a multicity study',
            'publisher', 'BMJ Open',
            'url', 'https://pmc.ncbi.nlm.nih.gov/articles/PMC3931989/',
            'locator', 'Table 2: Heatwave days and threshold'
        )
    )
);

COMMENT ON FUNCTION classify_melbourne_daily_mean_air_temperature(NUMERIC, NUMERIC) IS
    'Returns structured historical context for one forecast maximum/following-minimum pair. It never returns a current heat warning; 27.2 C is recorded only as two-consecutive-day percentile context.';

COMMIT;
