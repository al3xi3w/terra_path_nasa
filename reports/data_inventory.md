# Inventario vigente

165 archivos originales inventariados por tamaño y SHA-256; bytes originales sin cambios.
Cobertura y limitaciones por fuente: [auditoría local](local_audit.md).
Inventario completo: data/metadata/audit/raw_integrity.json. Fuentes existentes: data/metadata/audit/existing_sources.json.

## Derivados nuevos
- data/processed/sentinel2_monthly.parquet: 61582 bytes; SHA-256 7eb0b871a30277a86a80e4be6d7b4d2c25cb61bc2cd7d3e1e283bff48ed20414.
- data/processed/usda_nass.parquet: 36038 bytes; SHA-256 9b182b319b782686b13ff56d04235e2e287194f503c18777548f24f965418724.
- data/processed/gpm_monthly_index.parquet: 26641 bytes; SHA-256 4d1be8231f3400b746f165c9dd8ea2d53138ca09ec58635779b71c18a6e24cb2.
- data/processed/gpm_monthly_points.parquet: 21169 bytes; SHA-256 ce74494776a66254645f3082fcc8fa0c0edd88bc6dde06a650fec91294e02666.
- data/integrated/observations.parquet: 139005 bytes; SHA-256 684e2979cd49d7879fa3fb572719980bc6ed274efb4a6959f79a3b2d41c80ea4.
- data/integrated/locations.parquet: 5064 bytes; SHA-256 e08624b68d189a23eb8bb2605f2d161b467f31e826a9ee656798e4b2a7083099.
- data/integrated/catalog.parquet: 34003 bytes; SHA-256 9dac73223c1cf239f3e4859efe650bdeaeeff914c56a5bf7c8aa9be4812828ff.

## Originales vacíos
- data/raw/gaez/GAEZ-V5.RES02-CYL.HP0120.AGERA5.HIST.SOYB.HRLM.tif
- data/raw/gpm/3B-HHR.MS.MRG.3IMERG.20240601-S000000-E002959.0000.V07B.HDF5
- data/raw/modis/MOD13Q1.A2024145.h08v05.061.2024162165128.hdf
- data/raw/smap/SMAP_L3_SM_P_20240601_R19240_001.h5

Las grillas originales permanecen nativas; no se materializa una tabla global de píxeles.
