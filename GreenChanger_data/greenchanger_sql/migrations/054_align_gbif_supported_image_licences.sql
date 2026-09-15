BEGIN;

UPDATE dataset_source
SET licence = 'Record-level CC0 or CC BY 4.0 only',
    source_url = 'https://techdocs.gbif.org/en/openapi/v1/occurrence'
WHERE source_name = 'GBIF occurrence media API'
  AND publisher = 'Global Biodiversity Information Facility';

COMMENT ON TABLE tree_species_image_enrichment IS
    'One audited GBIF enrichment result per database scientific name. Published images are exact high-confidence Plantae matches using GBIF-supported CC0 or CC BY 4.0 occurrence filters; unresolved, failed and no-open-image outcomes remain explicit.';

COMMIT;
