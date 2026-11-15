# Auditoría local vigente

Corte de evaluación: 2026-11-14 (America/Lima). Ejecución offline; originales sin cambios.

Este informe reemplaza las afirmaciones históricas de cobertura en los otros informes.

GPM: 57 archivos validados; 57 meses únicos; faltan 2025-10, 2025-11, 2025-12 del intervalo 2021–2025.
Extracción compacta: 399 filas en coordenadas existentes. Sin expansión de la grilla global ni acumulación de tasas.
Se leen todas las celdas de las cinco variables mensuales por bloques, coordenadas/límites, fechas, duración, versión, unidades y rangos. SHA local no es checksum independiente del proveedor.

## Sentinel-2
426 filas; 6 ubicaciones; 2021-01-01 a 2026-11-01.
Indicadores: {"invalid_date": 0, "incomplete_or_future_month": 6, "invalid_coordinates": 0, "duplicate_key": 0, "invalid_scene_counts": 0, "ndvi_inconsistent_summary": 403, "ndvi_outside_range": 27, "ndvi_missing": 23, "ndvi_usable": 0, "ndmi_inconsistent_summary": 402, "ndmi_outside_range": 2, "ndmi_missing": 23, "ndmi_usable": 1}
Export lacks extraction script, cloud mask, geometry, band resolution and scene IDs. Summary inconsistencies retained, not repaired. Current month is incomplete. No crop labels.

## USDA NASS
392 filas, años [1945, 2021], unidades ['BU / ACRE'].
Cobertura: [{"Geo Level": "COUNTY", "State": "CALIFORNIA", "County": "FRESNO", "county_fips": "06019"}]
County annual survey yields; no parcel boundaries or crop rotation histories. Preserve BU / ACRE; no unverified commodity bushel-to-mass conversion. CV absent is unknown uncertainty, not zero.

## Fuentes existentes
- power: 1 manifiestos inspeccionados, estados {'verified': 1}; filas de tablas: 1826.
- smap: 2 manifiestos inspeccionados, estados {'empty_original': 2}; filas de tablas: 0.
- modis: 2 manifiestos inspeccionados, estados {'empty_original': 2}; filas de tablas: 0.
- gpm: 2 manifiestos inspeccionados, estados {'empty_original': 2}; filas de tablas: 0.
- srtm: 2 manifiestos inspeccionados, estados {'verified': 2}; filas de tablas: 0.
- gaez: 39 manifiestos inspeccionados, estados {'verified': 38, 'empty_original': 1}; filas de tablas: 0.
- faostat: 1 manifiestos inspeccionados, estados {'verified': 1}; filas de tablas: 823058.
- ecocrop: 1 manifiestos inspeccionados, estados {'verified': 1}; filas de tablas: 2568.
- fao56: 1 manifiestos inspeccionados, estados {'verified': 1}; filas de tablas: 57.
- agronomy: 59 manifiestos inspeccionados, estados {'verified': 59}; filas de tablas: 9716.

Los conteos de manifiestos no equivalen a datasets únicos. El catálogo conserva cada ruta, hashes, dimensiones, estadísticas y unidades.
SMAP, MODIS y GPM de media hora tienen originales vacíos: sus derivados son legibles pero no se integran como datos verificados. SRTM es un mosaico local estático de febrero de 2000.
GAEZ: 17 GeoTIFF inventariados; se comprueba cada raster legible. Todos llevan AGERA5: se excluyen de integración cuantitativa por la restricción de no usar ERA5. Una capa está vacía. Las unidades no corroboradas siguen pendientes.
FAOSTAT conserva áreas agregadas/históricas y flags A/E/X; no constituye etiquetas de parcela. FAO-56 conserva extracción parcial y condiciones; EcoCrop solo permite cálculos con *_usable. Crop Calendar usa país/zona/sesión estacional sin inventar año ni correspondencias.
Crop Calendar: 109 filas con extremos estacionales inválidos en ['calendar-BO', 'calendar-CM', 'calendar-CO', 'calendar-CV', 'calendar-DZ', 'calendar-ER', 'calendar-ET', 'calendar-GW', 'calendar-MG', 'calendar-NP', 'calendar-PE', 'calendar-RW', 'calendar-SD', 'calendar-SN', 'calendar-TD', 'calendar-TL', 'calendar-TZ', 'calendar-ZM', 'calendar-ZW']. Se retienen; crop_reference añade seasonal_date_invalid y flags por extremo. Faltantes siguen siendo desconocidos; febrero 29 se admite como fecha estacional.

## Integración y bloqueos de Machine Learning
14425 observaciones largas, con soporte espacial/temporal, unidades, ruta/hash, estado de calidad y detalles de origen. No es una tabla de entrenamiento.
- Resolver exportación Sentinel: polígonos, fechas de extracción, máscaras, escenas y significado de mínimos/percentiles. Noviembre 2026 se marca incompleto.
- Revisar integridad de originales vacíos sin modificarlos en esta etapa; no confiar solo en derivados antiguos.
- Definir área, cultivo, objetivo y unidad de predicción; no emparejar Fresno con puntos sin límites administrativos. NASS solo solapa 2021 con la serie mensual GPM disponible.
- Acordar correspondencias taxonómicas/variantes con identificadores de cada fuente. No se ha inventado un crosswalk.
- Definir QA GPM y reglas de agregación; tasas mensuales no son acumulaciones ni mediciones parcelarias.
- Definir temporadas y particiones espaciales/temporales para evitar fuga; datos anuales agregados no identifican rotaciones observadas.
- Documentar restricciones de suelo, riego, plagas, precedencias y función objetivo antes de optimizar rotaciones.

## Trazabilidad
Detalle reproducible en data/metadata/audit/*.json. raw_integrity.json registra todos los tamaños/hashes antes y después; no hubo cambios de bytes en originales. Correcciones de sidecars GPM conservan el hash/tamaño previos.
No se descargaron datasets, entrenaron modelos, desarrolló frontend ni ejecutaron commits/push.
