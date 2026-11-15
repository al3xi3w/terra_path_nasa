# Historial de revisiones — no es el estado vigente

La auditoría actual está en [local_audit.md](local_audit.md). Sus verificaciones sustituyen las afirmaciones históricas siguientes, en particular la disponibilidad de originales SMAP, MODIS y GPM de media hora.

## Revisión histórica — segunda etapa (previa a los gránulos locales)

- FAO entrega dos registros con id 0109: `Colza (rapeseed)` y `Colza(rapeseed)`, ambos Brassica napus L. Es una duplicación semántica en origen, no una duplicación introducida por extracción. Se conservan ambos; no usar id como clave única sin desambiguación.
- `cropParent` está ausente/vacío en muchos originales. No es pérdida del procesamiento. Es una jerarquía parcial; no se inventan padres ni se garantiza que el campo sea obligatorio.
- Las cadenas vacías de agrupación/familia se contaban antes como valores presentes: error de medición de faltantes corregido en Parquet. No se completan con valores inferidos.
- GAEZ LT5: ~75.69 % de celdas NoData sobre una cuadrícula mundial que incluye océanos y zonas no evaluadas. No equivale a 75.69 % de tierra agrícola faltante. Se respeta el NoData del GeoTIFF; atribuir todo el faltante a océanos requeriría una máscara independiente y no se afirma aquí.
- Calendarios: filas por país, cultivo, zona agroecológica y sesión; `source_record` y `session_index` retienen trazabilidad. Mes/día permanecen estacionales, sin año inventado. Duraciones se conservan como intervalos/texto y unidad del proveedor. No se calculan ciclos restando fechas que pueden cruzar el año.
- GAEZ adicional: HP0120, 2001–2020, AgERA5 histórico, secano/altos insumos. SIX es índice 0–10000, no porcentaje directo. Unidades de otras variables siguen pendientes de corroboración y bloquean su integración cuantitativa, aunque los rásteres sean legibles. Sidecars GCS describen dimensiones, NO unidades físicas.
- Las cuatro colecciones NASA se encontraron en CMR; las respuestas globales de metadatos están en `earth-verification.json`. Esto no prueba autorización de descarga. No había credenciales en el entorno del agente.
- GPM/SMAP: lectores probados con archivos HDF5 sintéticos, NoData antes de escala y QA conservada; no validados con gránulos reales. MODIS: implementación condicionada a GDAL/HDF4, pendiente de archivo real. SRTM: lectura nativa implementada, sin pendientes calculadas; pendiente de gránulo real.

- Validación final: 57 calendarios procesados, 9418 filas de sesiones, sin errores de conversión. Catorce pruebas aprobadas. Campos FAO de tipo mixto normalizados a texto nullable; no conversión arbitraria de intervalos a números.

## Etapa actual: gránulos reales

Los estados anteriores de lectores sin validar/HDF4 ausente corresponden a la etapa anterior. Ahora process utiliza matrices comprimidas y pyhdf; las entradas *-native-* del informe contienen el resultado real y sus estadísticas. No se descargaron datos nuevos. Se conservan QA y valores no recomendados por separado de las máscaras recomendadas.

Verificación actual: 18 pruebas aprobadas, incluidas cuatro comparaciones offline con los gránulos reales. SHA-256 de los originales intactos. Segunda ejecución de process/validate reutiliza salidas con hash válido. Se compararon valores SMAP AM/PM completos, muestras IMERG/MODIS/SRTM, duración IMERG y máscara SMAP; todas las matrices de salida se reabrieron para validar dimensiones y faltantes.

## FAOSTAT y FAO-56 — archivos locales

- FAOSTAT: 823.058 filas de rendimiento agrícola (kg/ha), 1961–2024; 244 identificadores de área y 169 de producto. Incluye agregados y entidades históricas: 244 no significa 244 países actuales. Flags conservados: A 393.637, E 416.182, X 13.239; definiciones originales en el diccionario del manifiesto. Sin valores numéricos faltantes ni negativos en la selección. No se sustituyen estimaciones por observaciones ni se mezclan rendimientos ganaderos. No se deduplicó ni calculó rendimiento a partir de producción/área.
- FAO-56: PDF de 333 páginas, tabla 12 localizada en páginas PDF 136–140 (impresas 110–114). Se cotejaron visualmente 57 etiquetas/variantes de páginas 136–138; 26 tienen los tres Kc explícitos y 31 conservan Kc inicial nulo. Las etiquetas incluyen variantes de manejo y grupos, no son 57 especies únicas. Texto de página y notas retenidos. Coeficientes adimensionales, referencias para condiciones estándar; no son agua requerida por hectárea.
- Extracción FAO-56 parcial: restantes filas, rangos/alternativas, notas especiales, frutales/humedales y otras tablas Kc/Kcb requieren revisión. Registro separado: data/metadata/fao56_manual_review.json. No se enlazaron cultivos entre FAOSTAT, FAO-56, calendarios ni GAEZ.
- 22 pruebas aprobadas: incluyen filtrado de rendimiento, rechazo de unidad inesperada, ZIP sin extracción, caché, celdas Kc vacías y bloqueo si cambia el PDF; las 18 pruebas previas siguen pasando. Procesadores NASA sin cambios.

## EcoCrop y POWER local

- EcoCrop: 2.568 registros, 55 columnas originales preservadas y cero duplicados completos. Se registran faltantes/tipos y estadísticas por variable en el manifiesto. 706 filas presentan al menos un campo inválido para cálculos; predominan ciclos cero (gmin: 685; gmax: 686 valores no utilizables, incluyendo inconsistencias de orden). No se eliminan especies ni se declaran inválidos todos sus atributos.
- Barringtonia racemosa: topmn original 160, topmn_usable nulo y topmn_valid falso. Se conservan topmx=28, tmin=12 y tmax=38; sin corrección inventada. Resto de anomalías: límites/orden de temperatura, precipitación, pH y magnitudes de latitud. Umbrales de temperatura son controles amplios de plausibilidad, no modelos ecológicos. Temperaturas letales independientes y convenciones de latitud no se ordenan artificialmente.
- POWER: 1.826 filas de 2021–2025, fecha desde YEAR/DOY, punto 36.59/-119.52, estándar LST. Cero días faltantes, fechas duplicadas o violaciones del orden térmico. Siete variables originales conservadas con sus unidades de cabecera; radiación MJ/m²/día. -999 a NaN; sin conversiones de unidad ni resampling. Se reemplazó reproduciblemente la conversión manual en la misma ruta de salida, sin otra copia.
- No se descargaron datos ni se construyeron correspondencias de especies/cultivos. Los hashes de los originales y salidas, cabecera POWER y trazabilidad quedan en JSON y en metadatos internos del Parquet. Los archivos originales permanecen intactos.

## Ampliación global por lotes

Tres nuevos GeoTIFF RES05-SIX HILM (maíz, soja, trigo) y tres sidecars; globales, periodo modelado 2001–2020, resolución 5 minutos de arco e índice 0–10000. Validados con el procesador ráster existente; no confundir con años 2021–2025 ni rendimiento. Las otras capas GAEZ con unidades pendientes siguen excluidas de cálculos.

POWER histórico configurado 1981–2025 sin puntos obligatorios; solar desde 1984. No se amplió la serie del punto anterior ni se atribuyó cobertura mundial a sus 1.826 filas. Las series SMAP/MODIS por puntos requieren tareas AppEEARS autenticadas; el catálogo está verificado, no la descarga ni el procesamiento de sus exportaciones. IMERG global mensual tiene catálogo parcial y no se descargó por credenciales ausentes. MODIS mensual global excede presupuesto. Estado detallado y meses ausentes en reports/batch_coverage.md.

Las fuentes ERA5/NASS tienen documentación de acceso, pero sus clientes y adquisiciones siguen pendientes. HLS/ECOSTRESS tienen capas descubiertas en el proveedor, no datos locales adicionales. No se inventaron agregaciones mensuales de gránulos individuales.

Validación de lotes: 31 pruebas aprobadas (27 anteriores y 4 nuevas). Catálogo IMERG mensual: 57/60 meses disponibles (95 %), faltan 2025-10, 2025-11 y 2025-12 en el snapshot consultado; 0 meses descargados de esta nueva colección. MODIS mensual: 60/60 disponibles (100 % catálogo), 0 descargados por tamaño estimado de 6.18 GB. Estos porcentajes no describen disponibilidad mundial de observaciones válidas por píxel. Las credenciales Earthdata/CDS/NASS estaban ausentes; no hubo intento autenticado fallido ni se guardaron secretos.
