# Calidad vigente

Ver [auditoría local](local_audit.md) para cobertura, registros y bloqueos.
GPM: datos científicos completos leídos por bloques; reportes por variable en data/metadata/audit/gpm_monthly.json.
Sentinel: flags conservadores; ninguna fila NDVI usable. No corregir inconsistencias sin revisar exportación.
NASS: códigos geográficos y variantes preservados, sin conversión de bushels. CV ausente no equivale a cero.
SMAP/MODIS/GPM media hora: originales vacíos; derivados no verificables contra ellos.
GAEZ local derivado de AgERA5 excluido de integración. No se utiliza ERA5, ECOSTRESS ni Landsat.
Los hashes/tamaños GPM coincidían con los sidecars. Se añadió local_audit sin reemplazar hashes correctos.
Originales sin alteraciones: data/metadata/audit/raw_integrity.json. Pruebas: [resultados](test_results.md).
La revisión anterior se conserva como historial en quality_review.md; no sustituye esta auditoría.
