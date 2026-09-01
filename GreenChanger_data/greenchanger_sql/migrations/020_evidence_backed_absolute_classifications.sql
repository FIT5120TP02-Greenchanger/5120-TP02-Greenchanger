BEGIN;

CREATE TABLE environmental_classification_reference (
    classification_reference_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    metric_code TEXT NOT NULL CHECK (
        metric_code IN ('daily_mean_air_temperature', 'canopy_progress')
    ),
    threshold_code TEXT NOT NULL,
    threshold_value NUMERIC NOT NULL,
    unit TEXT NOT NULL,
    classification_label TEXT NOT NULL CHECK (
        classification_label IN ('Medium', 'High')
    ),
    source_title TEXT NOT NULL,
    source_publisher TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_locator TEXT NOT NULL,
    evidence_scope TEXT NOT NULL,
    limitation TEXT NOT NULL,
    reviewed_on DATE NOT NULL,
    UNIQUE (metric_code, threshold_code, source_url)
);

INSERT INTO environmental_classification_reference (
    metric_code, threshold_code, threshold_value, unit,
    classification_label, source_title, source_publisher, source_url,
    source_locator, evidence_scope, limitation, reviewed_on
) VALUES
(
    'daily_mean_air_temperature', 'elevated_daily_mean', 27.2, 'degC',
    'Medium',
    'The impact of heatwaves on mortality in Australia: a multicity study',
    'BMJ Open',
    'https://pmc.ncbi.nlm.nih.gov/articles/PMC3931989/',
    'Table 2: Heatwave days and threshold',
    'Melbourne 95th-percentile summer daily-mean threshold.',
    'The study definition requires two or more consecutive summer days; this is not an instantaneous reading.',
    DATE '2026-09-01'
),
(
    'daily_mean_air_temperature', 'historical_central_heat_health', 30.0, 'degC',
    'High',
    'Planning for extreme heat and heatwaves',
    'Victorian Department of Health',
    'https://www.health.vic.gov.au/environmental-health/planning-for-extreme-heat-and-heatwaves',
    'Weather forecast districts; Calculating the average temperature; Figure 1',
    'Historical Central District threshold calculated from forecast maximum and following overnight minimum.',
    'The page states this Victorian system ended in 2021-22 and is not comparable with the current BOM national warning trigger.',
    DATE '2026-09-01'
),
(
    'canopy_progress', 'official_2018_metro_baseline', 15.3, 'percent',
    'Medium',
    'Melbourne''s vegetation, heat and land use data',
    'Victorian Government Department of Transport and Planning',
    'https://www.planning.vic.gov.au/guides-and-resources/Data-spatial-and-insights/melbournes-vegetation-heat-and-land-use-data',
    '2018 tree cover',
    'Official metropolitan Melbourne 2018 urban tree-canopy baseline of 15.3 percent.',
    'Metropolitan baseline context, not proof of property-level compliance.',
    DATE '2026-09-01'
),
(
    'canopy_progress', 'plan_for_victoria_urban_target', 30.0, 'percent',
    'High',
    'Action 12: Protect and enhance our canopy trees',
    'Victorian Government Department of Transport and Planning',
    'https://www.planning.vic.gov.au/planforvictoria/measuring-success/actions-and-outcomes/action-12-protect-and-enhance-our-canopy-trees',
    'What we''ll do',
    'Official Plan for Victoria target of 30 percent tree-canopy cover in urban areas.',
    'Urban-area target context, not proof of property-level compliance; do not apply to the rendered canopy proxy.',
    DATE '2026-09-01'
);

CREATE OR REPLACE FUNCTION classify_melbourne_daily_mean_air_temperature(
    p_forecast_maximum_c NUMERIC,
    p_following_overnight_minimum_c NUMERIC
)
RETURNS TEXT
LANGUAGE SQL
IMMUTABLE
PARALLEL SAFE
RETURN CASE
    WHEN p_forecast_maximum_c IS NULL
      OR p_following_overnight_minimum_c IS NULL
      OR p_forecast_maximum_c::TEXT IN ('NaN', 'Infinity', '-Infinity')
      OR p_following_overnight_minimum_c::TEXT IN ('NaN', 'Infinity', '-Infinity')
        THEN 'Unavailable'
    WHEN (
        p_forecast_maximum_c + p_following_overnight_minimum_c
    ) / 2.0 >= 30.0 THEN 'High'
    WHEN (
        p_forecast_maximum_c + p_following_overnight_minimum_c
    ) / 2.0 >= 27.2 THEN 'Medium'
    ELSE 'Low'
END;

COMMENT ON FUNCTION classify_melbourne_daily_mean_air_temperature(NUMERIC, NUMERIC) IS
    'Evidence-backed historical Melbourne daily-mean air-heat category. Uses forecast maximum plus following overnight minimum divided by two. Not valid for instantaneous BOM observations, Landsat LST or current BOM heatwave warnings.';

CREATE OR REPLACE FUNCTION classify_canopy_benchmark(
    p_canopy_percentage NUMERIC
)
RETURNS TEXT
LANGUAGE plpgsql
IMMUTABLE
PARALLEL SAFE
AS $function$
BEGIN
    IF p_canopy_percentage IS NULL
       OR p_canopy_percentage::TEXT IN ('NaN', 'Infinity', '-Infinity') THEN
        RETURN 'Unavailable';
    END IF;
    IF p_canopy_percentage < 0 OR p_canopy_percentage > 100 THEN
        RAISE EXCEPTION 'canopy percentage must be between 0 and 100';
    END IF;
    IF p_canopy_percentage >= 30.0 THEN
        RETURN 'High';
    END IF;
    IF p_canopy_percentage >= 15.3 THEN
        RETURN 'Medium';
    END IF;
    RETURN 'Low';
END;
$function$;

COMMENT ON FUNCTION classify_canopy_benchmark(NUMERIC) IS
    'Evidence-backed canopy progress against the official 15.3 percent metropolitan baseline and current 30 percent Victorian urban-area target. Not valid for the rendered Vicmap proxy or proof of property-level compliance.';

COMMIT;
