# Terrapath

Qué sembrar en tus próximas campañas. Un motor de rotación de cultivos que funciona en cualquier coordenada,
construido solo con datos abiertos de la NASA y la FAO, y una app web para agricultores.

- **Motor** (`src/`, `scripts/`): clima diario NASA POWER, Kc FAO-56, límites de EcoCrop, altitud SRTM y lluvia GPM IMERG.
  Propone rutas de 3 campañas puntuadas en Agua, Tierra y Cosecha segura.
- **App** (`app/`): web sin servidor. Ver [app/README.md](app/README.md).
- **Recorrido paso a paso** (`notebooks/terrapath_recorrido.ipynb`): el motor real, de principio a fin, con sus resultados.
- **Pruebas** (`tests/`): `.venv/bin/python -m pytest -q` (las de la app usan Node).

## Los datos no están en el repositorio

`data/` y `app/data/` están en `.gitignore` (≈1,3 GB, de terceros). En **[DATA.md](DATA.md)** está de dónde sale cada
archivo, cómo descargarlo (algunos piden una cuenta gratuita de NASA Earthdata) y el orden para regenerar todo.
Sin esas carpetas, el código está completo pero el motor, la app y la mayoría de las pruebas no tienen datos con qué correr.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
# descargar y regenerar los datos: ver DATA.md
.venv/bin/python scripts/build_app.py
.venv/bin/python -m http.server 8000 -d app   # abrir http://localhost:8000
```

Reglas del proyecto: no se inventan datos (lo que falta queda nulo y se reporta), un faltante nunca cuenta como cero
ni como favorable, y toda salida guarda su procedencia (fuente, archivo, SHA-256, variable, unidad, período y ubicación).

---

*Lo que sigue documenta la etapa anterior del proyecto (Field Shift: auditoría y preparación de datos).*

## Field Shift — preparación de datos para ML

Pipeline local para NASA Space Apps Challenge. La auditoría vigente está en [reports/local_audit.md](reports/local_audit.md); los informes anteriores conservan contexto histórico y no describen por sí solos el estado actual.

## Ejecución reproducible y sin descargas de datos

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/audit_local.py --as-of 2026-11-14
# Alternativa equivalente para la fecha de corte predeterminada:
.venv/bin/python scripts/run_pipeline.py audit
.venv/bin/python -m pytest -q
```

La instalación obtiene dependencias de software, no datasets. La auditoría no necesita credenciales ni red. No ejecutar `run_pipeline.py` sin operación: el comando histórico por defecto `all` incluye adquisición. Tampoco ejecutar `download`, `extend`, `batch*`, `earth`, `power` o `recuperar_gpm.py` para esta etapa.

`src/audit.py` reutiliza `digest`, `decode_array`, `read_power_csv`, `Pipeline.local_environment` y `Pipeline.local_agronomy`. Lee originales exclusivamente; escribe derivados y metadatos. La fecha de corte es explícita para que el indicador de mes incompleto sea reproducible. No hay entrenamiento, frontend, imputación ni correspondencias de cultivos inventadas.

## Disponibilidad comprobada

- **GPM/IMERG mensual V07B:** 57 archivos, enero 2021–septiembre 2025, sin meses duplicados. Faltan octubre–diciembre de 2025 respecto del intervalo configurado. Se comprueban cabecera, producto, versión, fechas/época/calendario, duración, unidades, dimensiones, centros/límites y todas las celdas de cinco variables, por bloques. Tasas en mm/hr; no acumulaciones. La grilla tiene 3600 × 1800 celdas, a 0.1°. Cobertura de meses no equivale a datos válidos en cada píxel. Índice QA sin umbral inventado: sus valores no son porcentajes ni están limitados a uno.
- **Sentinel-2 exportado:** 426 filas, seis pilotos, enero 2021–noviembre 2026. 23 filas sin índices; noviembre 2026 incompleto al corte. Los 403 registros NDVI presentes tienen estadísticas inconsistentes, 27 con algún valor NDVI fuera de [-1,1]. Ninguna fila NDVI pasa el cribado conservador. Se preservan todos los valores y flags. Falta el script de exportación para saber si mínimos/percentiles representan soportes distintos; no se presume que los números sean reparables.
- **USDA NASS:** 392 rendimientos anuales, 1945–2021, trigo/maíz y diez variantes de `Data Item`, exclusivamente Fresno (FIPS 06019), California. BU / ACRE se conserva; no hay conversión supuesta a kg/ha. No es cobertura estatal ni de parcelas. CV falta en 390 registros; incertidumbre desconocida, no cero.
- **NASA POWER:** 1.826 días completos, 2021–2025, un punto 36.59/-119.52, LST, siete variables. La radiación está en MJ/m²/día. No unir sus fechas locales como instantes UTC.
- **SMAP/MODIS/GPM de media hora:** originales locales vacíos. Los derivados son legibles, pero no verificables contra esos originales y quedan fuera de observaciones integradas.
- **SRTM:** un mosaico N37W120, estático de febrero de 2000, en metros, 1 segundo de arco. No hay pendientes calculadas ni cobertura regional completa.
- **GAEZ:** 17 GeoTIFF, 16 legibles y uno vacío. Las capas locales llevan AgERA5 en su procedencia; se auditan e inventarían, pero se excluyen de la integración cuantitativa como interpretación conservadora de la restricción «no usar ERA5». No se descargan ni procesan datos ERA5 adicionales. Varias unidades GAEZ siguen sin corroborar.
- **FAOSTAT:** 823.058 rendimientos kg/ha, 1961–2024, 244 códigos de área y 169 productos; incluye agregados y entidades históricas. Flags A/E/X retenidos, sin duplicados de área/producto/elemento/año.
- **EcoCrop:** 2.568 registros; 706 con al menos una anomalía. Usar `*_usable`/`*_valid`, no valores originales inválidos. No todas las especies son cultivos.
- **FAO-56:** 57 etiquetas/variantes de extracción parcial verificada previamente y ligada al hash del PDF; 31 Kc iniciales nulos. Kc adimensional, bajo las condiciones documentadas; no mm de agua ni calibración local.
- **Crop Calendar:** 57 países publicados, 9.418 filas de sesiones estacionales. Mantiene país, zona, cultivo, sesión, intervalos/unidades y trazabilidad; no asigna años ni geometrías inexistentes. Se detectaron 109 filas con extremos estacionales inválidos en 19 países; las consultas añaden `seasonal_date_invalid` sin alterar los valores. Identificador FAO 0109 repetido en catálogo: no usar como clave única sin desambiguación.

## Archivos producidos

- `data/processed/sentinel2_monthly.parquet`: columnas originales, fecha normalizada, fila fuente, flags y máscaras de uso por índice.
- `data/processed/usda_nass.parquet`: originales, valores numéricos/símbolos de supresión, unidad, FIPS textual, periodo anual y duplicados de clave completa.
- `data/processed/gpm_monthly_index.parquet`: 57 entradas con ruta/hash, fechas, estado y estadísticas; no tabla de píxeles.
- `data/processed/gpm_monthly_points.parquet`: 399 filas en las siete coordenadas existentes de Sentinel/POWER. Conserva celda nativa seleccionada, índices, cinco variables, duración y procedencia. Extracción de celda más cercana, sin interpolación.
- `data/integrated/observations.parquet`: 14.425 observaciones en formato largo. Es un almacén consultable con calidad explícita, **no una tabla lista para entrenar**. Incluye registros que requieren revisión.
- `data/integrated/locations.parquet`: pilotos/punto POWER/condado; el condado conserva coordenadas nulas porque no se dispone de geometría.
- `data/integrated/catalog.parquet`: acceso a fuentes de referencia y grillas, estado de integridad, resoluciones, unidades y metadatos. No duplica FAOSTAT ni grillas globales.
- `data/metadata/audit/*.json`: estadísticas completas, cobertura, flags, hashes de los 165 originales y comprobación antes/después. Los 57 sidecars GPM reciben `local_audit`. Sus hashes/tamaños ya coincidían: no se sustituyeron. Si una futura recuperación requiere corregirlos, se conserva el valor previo y solo se actualiza tras validación científica.

El SHA-256 es una referencia de integridad local, no un checksum independiente del proveedor. `verified` en el catálogo significa integridad de procedencia local comprobada; no exactitud frente a mediciones de campo ni aptitud automática para entrenamiento. Los cuatro originales vacíos quedan explícitamente identificados.

## Consultas por ubicación, fecha y cultivo

Desde Python en la raíz del proyecto:

```python
from src.store import DataStore
store = DataStore()

# Periodos que se solapan con [start, end); conserva todos los estados QA.
series = store.observations(location_id='sentinel2:piura_1',
                            start='2021-01-01', end='2022-01-01')
# Solo coincidencia exacta con coordenadas registradas; no asignación de condado.
point = store.at_point(-5.24, -79.45, source='gpm_monthly')
# Consulta bajo demanda de originales mensuales validados, sin descargar ni expandir grilla.
rain = store.gpm_at_point(-5.24, -79.45, '2021-01-01', '2021-03-01')
# Rendimientos anuales: conserva cada variante de manejo/subtipo en Data Item.
yields = store.observations(location_id='us_county:06019', crop_id='nass:WHEAT')
# Identificadores/nombres nativos exactos; no equivalencias entre fuentes.
calendar = store.crop_reference('calendar', '0056', area='PE')
kc = store.crop_reference('fao56', 'Broccoli')
```

`crop_reference` también admite `faostat` (Item Code, opcional Area Code/año) y `ecocrop` (nombre científico exacto). Las referencias incluyen metadatos de procedencia en `DataFrame.attrs['fieldshift_lineage']`; se verifica el hash actual del original y del derivado antes de devolverlas. Un país sin calendario local devuelve tabla vacía; no se extrapola.

Cada observación conserva variable/unidad, soporte espacial/temporal, periodo con fin exclusivo, ruta/hash fuente, estado de calidad y detalles JSON. Los cultivos son identificadores del origen; las observaciones ambientales no adquieren etiquetas de cultivo por proximidad. Las fechas LST permanecen días locales. Se mantienen los originales y los valores sospechosos; los consumidores deben filtrar la calidad de manera explícita.

## Antes de Machine Learning y optimización

Resolver el export Sentinel y los originales vacíos; definir parcela/área, temporada, objetivo y cultivos; revisar correspondencias entre fuentes y conversiones de rendimiento; acordar QA y agregaciones compatibles con cada soporte; diseñar particiones temporales/espaciales sin fuga. Solo un registro NASS de 2021 solapa con la serie mensual GPM disponible, y los puntos Sentinel/POWER no son una media de Fresno. Faltan historiales de rotación y restricciones verificadas de suelo, riego, plagas y precedencias. Ninguna de estas carencias se completa con valores supuestos.

Pruebas y resultados de esta ejecución: [reports/test_results.md](reports/test_results.md). Configuraciones históricas de adquisición siguen disponibles como referencia, pero no se ejecutan durante la auditoría offline.

## Prototipo de evaluación climática

Ejecutar `.venv/bin/python scripts/evaluate_crops.py --crops 'Zea mays' 'Triticum aestivum'`.
Documentación, supuestos, unidades y limitaciones en [reports/crop_prototype.md](reports/crop_prototype.md); ejemplo completo en [reports/crop_screen_example.json](reports/crop_screen_example.json). Genera 57 filas mensuales POWER–GPM; no recomienda una rotación sin restricciones documentadas. Validación actual: 49 aprobadas, 3 omitidas.

## Escenarios de parcela (etapa actual)

```bash
.venv/bin/python scripts/parcel_scenarios.py --demo
.venv/bin/python scripts/parcel_scenarios.py --input parcela.json
```

La demo usa un **plan hipotético** con datos NASA/FAO locales reales; sus fechas no son una recomendación de siembra. Para proporcionar una parcela, el JSON admite:

```json
{
  "latitude": 36.59,
  "longitude": -119.52,
  "current_crop": null,
  "previous_crops": [],
  "sowing_date": "2023-04-01",
  "horizon_end": "2023-10-31",
  "irrigation": {"available": null},
  "soil": {},
  "candidates": [
    {"crop": "Zea mays", "harvest_date": "2023-09-30"},
    {"crop": "Glycine max", "harvest_date": "2023-09-30"}
  ],
  "assumptions": {"screen_season_mean_temperature": true}
}
```

Los datos suministrados son declaraciones del agricultor, no hechos independientemente verificados. Historial: lista de objetos `crop`, `start`, `end`, con fechas anteriores a la siembra y sin solapamientos. Suelo admite `ph` (0–14), `texture` textual y `nitrogen_kg_ha`; no se infieren nutrientes faltantes. Riego admite disponibilidad booleana/nula y `seasonal_mm` solo si se declara disponible. Cantidad declarada no equivale a agua efectiva. Valores ausentes siguen desconocidos. Los cultivos se buscan por nombre científico exacto. No se aplica la hipótesis térmica salvo activación explícita.

Se valida ubicación, fechas ISO reales, horizonte, cosecha, historial, tipos, unidades admitidas, límites y candidatos duplicados. El JSON de salida distingue entrada del agricultor, evidencia NASA/FAO, supuestos y restricciones desconocidas. `rotation_sequence` y el ranking permanecen nulos.

**Temporada:** suma diaria POWER entre siembra y cosecha, ambas inclusivas, solamente con cobertura diaria completa y sin lluvia ausente/negativa. No se prorratea GPM mensual ni se extrapolan años parciales. Para otras coordenadas sin serie POWER local se devuelve desconocido, sin reutilizar California. El POWER es estimación de grilla servida como punto, no medición de parcela. Fechas futuras no se pronostican. La lluvia estacional nunca se contrasta con límites de precipitación anual EcoCrop. Sin demanda estacional, lluvia efectiva, almacenamiento y eficiencia de riego, no se declara balance hídrico favorable.

Las fechas propuestas forman un plan calendario válido sintácticamente, **no un calendario agronómico verificado**. Opcionalmente cada candidato admite `fao_calendar` con `country`, `crop_id`, `aez_id`, `source_record`, `session_index`: selecciona una referencia local exacta. Se rechazan extremos inválidos y se comparan las ventanas estacionales, incluso cuando cruzan el año; extremos ausentes producen desconocido. Aun con fechas compatibles falta verificar correspondencia taxonómica y pertenencia de la parcela a la zona agroecológica. Un selector proporcionado por el agricultor no certifica esas correspondencias. No se fabrican calendarios de California.

**GAEZ — rectificación de etapas anteriores:** la restricción aclarada permite productos FAO derivados de AgERA5, sin descargar ERA5 directamente. Se muestrean solo seis capas SIX existentes (maíz, trigo, soja; secano/irrigado con altos insumos), con hash, resolución, escenario y periodo 2001–2020. Hay una discrepancia objetiva: los rásteres locales son uint8 con códigos 0–9 y NoData=0, sin unidad declarada; la descripción histórica «índice 0–10000» no es aplicable a esos valores almacenados. Se muestran como **códigos con leyenda pendiente**, sin ordenarlos, convertirlos a porcentaje ni inferir que 8 sea mejor que 3. Las capas YCX/WDE/CYL conservan unidades pendientes; el archivo vacío no se usa. LT5 no es etiqueta de aptitud por cultivo. GAEZ no suma votos climáticos independientes a POWER/GPM y no representa la parcela ni el año del escenario. Las exclusiones y unidades descritas en informes anteriores son históricas; esta revisión prevalece para los escenarios nuevos.

Ejemplo ejecutado: abril–septiembre 2023, 183 días completos, 64,21 mm POWER para ambos candidatos. Maíz: códigos SIX secano/irrigado 8/3; soja: 8/2, **sin interpretación de aptitud**. Ambos escenarios quedan insuficientemente documentados. La comparación expone factores y límites EcoCrop válidos para pH declarado y temperatura media estacional si se habilita esa hipótesis; no agrega puntuaciones ni decide viabilidad por precipitación anual.

Para un optimizador faltan calendario local y correspondencias verificados, historia real de cultivos, reglas de transición/familias, balance de nutrientes y agua, restricciones de manejo y objetivos/costos. La estructura permite registrar esas entradas, pero no inventa relaciones ni implementa optimización. El evaluador anual anterior se mantiene como cribado separado.

Pruebas de esta ampliación: 59 aprobadas y 3 omitidas por originales vacíos. Código: `src/parcel_scenarios.py`, terminal: `scripts/parcel_scenarios.py`, pruebas: `tests/test_parcel_scenarios.py`. No se duplicaron tablas de datos ni se alteraron originales.

## Optimizador experimental de 2–3 temporadas

```bash
.venv/bin/python scripts/optimize_rotation.py examples/rotations/hypothetical.input.json
.venv/bin/python scripts/optimize_rotation.py examples/rotations/real_incomplete.input.json
```

Motor puro: `src/rotation_optimizer.py::optimize`. Reutiliza las validaciones de parcela; el comando adjunta el evaluador `scenarios` como evidencia separada. No transforma automáticamente información insuficiente del evaluador en restricciones favorables. Ejemplos JSON de entrada/salida en `examples/rotations/`.

Enumeración exhaustiva determinista, máximo ocho candidatos y dos/tres temporadas (512 secuencias). No necesita solver ni dependencias nuevas. Se registran todas las secuencias, incluidas las descartadas con sus motivos; no se poda para mantener la explicación completa de este conjunto pequeño.

Parámetros numéricos: `value`, `unit`, `provenance`, `status` (documented o hypothetical). Unidades admitidas: duración `day`, requerimiento y presupuesto de riego `mm` por temporada, costo `USD/ha`. Se comparan sobre la misma parcela. La disponibilidad es volumen equivalente declarado; no se infiere a partir de lluvia. No se suman monedas ni superficies diferentes.

Obligatorias: cultivo precedente declarado; revisión explícita de restricciones del historial; transición permitida/prohibida para cada par posible, incluido el precedente; duración entera positiva que quepa en el intervalo; fechas ordenadas sin solapamientos; permiso de calendario, clima y suelo/nutrientes por candidato y temporada; riego requerido frente al presupuesto. Los permisos contienen `allowed`, `provenance`, `status`. Son **certificados de restricciones suministrados**, no cálculos agronómicos inferidos por el motor. El proveedor debe verificar ventanas, manejo, taxonomía, familia, nutrientes y efectos del historial antes de marcarlos como documentados. Un texto de procedencia no constituye validación científica automática. Reglas familiares solo se representan mediante transiciones explícitas; no se adivinan familias. El motor no simula nutrientes dinámicos ni efectos acumulados de tres temporadas: deben estar cubiertos por las restricciones externas o el escenario sigue siendo experimental.

Criterios opcionales: lista ordenada de `min_cost`, `min_irrigation`. Se minimizan lexicográficamente, no mediante pesos ocultos. Costos solo son necesarios si se activa ese objetivo. Si falta un dato obligatorio o un costo requerido, se abstiene. Sin objetivos devuelve secuencias factibles sin seleccionar mejor. Empates: orden lexicográfico de nombres, declarado y sin significado agronómico. Todos los resultados se etiquetan experimental_not_agronomically_validated, incluso con parámetros declarados documentados.

Demo **enteramente hipotética en sus restricciones y costos**, sin resultados agrícolas: tres cultivos, dos temporadas, cultivo precedente maíz, ciclos de 100 días, presupuesto 100 mm/temporada, prohibición de repetir inmediatamente cultivo. Costos artificiales soja/trigo/maíz: 10/20/30 USD/ha; riego artificial: 40/60/90 mm. Hay nueve secuencias: cuatro factibles y cinco descartadas por repetición. Soja→trigo y trigo→soja empatan en costo 30 y riego total 100; se selecciona soja→trigo únicamente por el desempate declarado. Soja→maíz cuesta 40 y requiere 130; trigo→maíz cuesta 50 y requiere 150. Los totales de agua se suman en el horizonte; el límite obligatorio es por temporada, no 100 mm en todo el horizonte. No se afirma ventaja biológica de soja→trigo.

El caso real incompleto usa las coordenadas con POWER disponible, pero desconoce cultivo actual, restricciones de transición, requerimientos y presupuestos de temporada. Fechas/candidatos son un horizonte propuesto, no registros reales del agricultor. Se abstiene; los datos NASA y FAO no rellenan esos vacíos. GAEZ conserva códigos sin interpretar, Sentinel inconsistente no se consume y NASS no aporta etiquetas de rendimiento.

Para recomendaciones reales: validar restricciones con agrónomos, ventanas y ciclos locales, identidad/familias de cultivos e historial, suelo/nutrientes y efectos entre temporadas, demanda y suministro de agua, costos locales y objetivo del agricultor. Incorporar evaluación de incertidumbre y validación independiente. Un óptimo bajo entradas hipotéticas es una demostración de software, no una recomendación definitiva.

Validación del motor: **68 pruebas aprobadas y 3 omitidas** por originales vacíos. Pruebas añadidas: óptimo reproducible, factibilidad, restricciones climáticas/calendario/suelo, riego insuficiente, duración excesiva, transición ausente, unidades/procedencia obligatorias, tres temporadas, ausencia de objetivos y abstención del caso incompleto. Hashes de los 165 originales comprobados sin cambios.

## Restricciones derivadas de datos NASA/FAO (integración con el optimizador)

```bash
.venv/bin/python scripts/optimize_with_evidence.py examples/rotations/california_evidence.input.json
```

Módulo: `src/constraints.py::optimize_with_evidence`. Construye cada restricción por cultivo y temporada con tres estados: `allowed`, `prohibited`, `unknown`. Lo desconocido nunca se convierte en permitido. Prohibido domina; un desconocido en una temporada no excluida, o en una transición entre cultivos no excluidos, provoca abstención con la lista de información requerida. Solo si no queda nada desconocido se llama a `rotation_optimizer.optimize`. Cada decisión conserva evidencia: fuente, archivo, SHA-256, variable, unidad, período, ubicación, valor y motivo. Detalle completo y estado de cada restricción en `reports/constraints_integration.md`.

Entrada: `parcel` (mismo esquema que escenarios), `seasons` (`start`, `end`), `objectives` y un bloque `farmer` opcional con declaraciones explícitas, cada una con `provenance`: `country_iso2`, `water_available` (mm por temporada), `irrigation_required` (mm por cultivo y temporada; declarado, nunca calculado), `cycle` (días del cultivar), `soil_nutrients`, `transitions` y `history_review`. Los estados del optimizador aceptan además `declared` (agricultor) y `derived` (calculado de datos locales verificados). Una declaración no anula una prohibición derivada de datos.

El ejemplo hipotético (`hypothetical.input.json`) sigue siendo la prueba del motor. `california_evidence.input.json` usa el punto real con POWER/GPM; sin declaraciones del agricultor se abstiene. No es una recomendación.

### Necesidad de riego calculada (FAO-56)

```bash
.venv/bin/python scripts/optimize_with_evidence.py examples/rotations/california_fao56.input.json
```

`src/water_requirement.py` calcula ET₀ (Penman-Monteith FAO-56) desde NASA POWER y ETc como intervalo con las Tablas 11–12 verificadas (`config/fao56_stages_verified.json`, ligado al SHA-256 de `FAO56.pdf`). Se activa con `farmer.fao56[cultivo] = {table11_id, table12_label, provenance}`. Si la Tabla 12 no trae Kc inicial, se calcula con el Anexo 7 a partir de la lluvia POWER y de `initial_irrigation = {events: [{day, depth_mm}], provenance}` (lista vacía = sin riego). La restricción de agua usa cotas: requiere `irrigation_efficiency` para la cota superior e `initial_soil_water_mm` para la inferior. No se supone lluvia efectiva. Detalle en `reports/constraints_integration.md`.

