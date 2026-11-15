# Integración NASA/FAO → optimizador de rotación

Fecha: 2026-11-14 (America/Lima). Módulo `src/constraints.py`; pruebas `tests/test_constraints.py`. Sin descargas, sin ML, sin frontend. No se modificó ningún original.

## Qué se calcula realmente con datos locales

| Restricción | Fuente | Regla | Estados posibles hoy |
|---|---|---|---|
| Ciclo cabe en la temporada | EcoCrop `gmin`/`gmax` (días) | duración < gmin → prohibido; ≥ gmax → permitido; entre ambos → desconocido salvo ciclo de cultivar declarado (dentro de [gmin, gmax]) | los tres |
| Clima: temperatura | NASA POWER `T2M` diario completo en coordenadas exactas + EcoCrop `tmin`/`tmax` absolutos | media de la temporada dentro del rango. Requiere el supuesto explícito `screen_season_mean_temperature`; sin él → desconocido | los tres |
| Clima: precipitación | NASA GPM IMERG mensual (vía `california_monthly_climate.parquet`) | solo evidencia de contexto. Los límites de lluvia de EcoCrop son anuales; no se comparan con una temporada | no condiciona |
| Calendario FAO | FAO Crop Calendar (país declarado) + correspondencia exacta de nombre científico | inicio de temporada en ventana de siembra y fin en ventana de cosecha. Todas las sesiones de todas las AEZ del país lo contienen → permitido; ninguna → prohibido; mezcla → desconocido (sin geometría AEZ local) | los tres; para EE. UU. siempre desconocido |
| Agua: necesidad de riego | NASA POWER (T máx/mín, HR media, viento 2 m, radiación, lluvia) + FAO-56 Tablas 11–12 verificadas visualmente (`config/fao56_stages_verified.json`) | ET₀ Penman-Monteith diaria → ETc = Kc × ET₀ como intervalo [bajo, alto] (ec. 62 con HRmín ∈ [20, min(HRmedia, 80)] %). Disponible < ETc_bajo − lluvia − agua inicial del suelo → prohibido; disponible ≥ ETc_alto / eficiencia → permitido; entre ambos → desconocido | los tres; requiere selección FAO-56 declarada |
| Suelo: pH | pH declarado por el agricultor + EcoCrop `phmin`/`phmax` | fuera del rango → prohibido | prohibido o desconocido |
| Suelo: nutrientes | ningún dato local válido (SMAP es humedad y su original está vacío) | solo declaración explícita | desconocido salvo declaración |

## Qué depende del agricultor

- País (ISO2): no se deduce de coordenadas sin límites administrativos locales.
- Agua disponible por temporada (mm). Se distingue de la necesidad de riego.
- Selección FAO-56 por cultivo: fila de la Tabla 11 y etiqueta de la Tabla 12. La correspondencia cultivo ↔ fila y región no se infiere (las regiones de la Tabla 11 son texto, sin geometría).
- Riegos durante la etapa inicial (día después de la siembra y lámina en mm; lista vacía si no hay), solo cuando la Tabla 12 deja en blanco el Kc inicial (maíz, soja). Con eso el Kc inicial se **calcula** (FAO-56 Anexo 7). Alternativa: declarar el Kc inicial directamente. El valor del grupo nunca se hereda.
- Eficiencia de riego (0–1] y agua inicial aprovechable del suelo (mm). Sin ellas no existe cota superior o inferior. La lluvia efectiva nunca se supone: las cotas usan 0 % y 100 % de la lluvia.
- Necesidad de riego declarada (opcional): si existe, tiene prioridad sobre el cálculo.
- Ciclo del cultivar cuando la temporada cae entre gmin y gmax.
- pH del suelo y evaluación de nutrientes.
- Cultivo precedente, revisión del historial y reglas de transición (no hay un dataset local de reglas de rotación).

## Qué sigue desconocido

- Calendario para California: el calendario FAO local cubre 59 países y no incluye EE. UU.
- Trigo: EcoCrop `Triticum aestivum` no coincide exactamente con ningún nombre FAO (FAO usa `Triticum aestivum L. subsp. aestivum`). No se asume equivalencia.
- Zona agroecológica de la parcela: no hay geometría AEZ local.
- Balance hídrico diario (lluvia efectiva, percolación, ascenso capilar), requerimiento de lavado de sales y efectos de nutrientes o historial.
- Soja en California: ninguna fila de la Tabla 11 corresponde a California; la fila "Central USA" tiene L_dev "30/35" y no se usa.
- GAEZ SIX: los códigos se conservan sin interpretar y no condicionan.

## Correspondencia EcoCrop ↔ FAO

`crop_name_map`: igualdad exacta de cadena entre `scientificname` (EcoCrop, 2568 registros, sin duplicados) y `crop_scientific_name` (FAO, 240 registros). Resultado: **59 correspondencias**, 0 ambiguas. No se eliminan autores ("L."), no se usan sinónimos, padres ni familias. `crop_family` de FAO es un grupo de uso (p. ej., "OTHER CROPS"), no una familia taxonómica. Hay registros FAO con nombres dudosos (p. ej., "Red clover" = `Triticum pratense`); por eso no se acepta una coincidencia parcial.

Maíz → FAO 0338 "Corn" (`Zea mays`); soja → FAO 0326 "Soya" (`Glycine max`); trigo → sin correspondencia.

## Integración y abstención

1. `build_constraints` evalúa cada cultivo × temporada × restricción, más transiciones e historial.
2. `missing_information` ignora las temporadas ya prohibidas y reúne los desconocidos restantes.
3. Si falta algo → `abstained`, `optimizer: null` y la lista `missing`.
4. Si no → `to_optimizer_input` pasa las restricciones con estado `derived` o `declared`, y el optimizador aplica sus propias comprobaciones (ciclo, riego frente a presupuesto, transiciones). `recommendation` es siempre `null`.

Cambios mínimos en código existente: `rotation_optimizer.py` acepta los estados `declared`/`derived`, y permite omitir el requerimiento de riego o el ciclo solo cuando la temporada ya está excluida (no se inventan métricas). `store.py` expone `verified_table`, con la misma verificación de linaje que `crop_reference`.

## Ejemplo real (California, 36.59, −119.52)

Temporadas 2023-03-01/06-30 y 2023-07-01/11-30; candidatos maíz, soja y trigo; supuesto de temperatura activado; sin declaraciones. Resultado: clima `allowed` para los tres cultivos en ambas temporadas (p. ej., maíz T2M medio 16,97 °C en la temporada 1, dentro de 10–47 °C). Ciclo, calendario, suelo, agua, transiciones e historial quedan `unknown`. Estado final `abstained` con 47 requisitos listados. Salida: `examples/rotations/california_evidence.output.json`.

## Pruebas

`tests/test_constraints.py` (12): tres estados y combinación, correspondencia exacta de nombres, abstención del caso real con explicación, procedencia (hash POWER recalculado, unidad, período, ubicación, meses GPM), supuesto de temperatura obligatorio, calendario FAO real de Perú (prohibido y desconocido), integración factible con declaraciones completas, prohibición que excluye sin bloquear, transición desconocida → abstención, agua declarada frente a requerida, reglas de ciclo y solicitud inválida.

## Cálculo FAO-56 (módulo `src/water_requirement.py`)

- ET₀ diaria: FAO-56 ec. 6 con P (ec. 7), γ (ec. 8), e° (ec. 11–12), ea desde HR media (ec. 19, alternativa aceptada por FAO cuando falta HRmáx/HRmín), Ra (ec. 21–25), Rso (ec. 37), Rnl (ec. 39, Rs/Rso ≤ 1), G = 0. Altitud: promedio MERRA-2 del encabezado POWER (249,47 m), no la de la parcela. Verificado contra el Ejemplo 18 de FAO-56 (3,88 frente a 3,9 mm/día).
- Kc diario: curva de la ec. 66. Kc medio y final ajustados con la ec. 62 como intervalo (u2 entre 1 y 6 m/s; altura con rango de la Tabla 12; sin ajuste si Kc final < 0,45). Kc final con rango de la Tabla 12, salvo que se declare.
- Tablas: 18 filas de la Tabla 11 (maíz grano, trigo de invierno, grupo cebada/avena/trigo, soja) y 5 de la Tabla 12, leídas de las páginas renderizadas 131, 132 y 137. La capa de texto no se usó porque fusiona superíndices con los números ("202" = 20²). Se recomienda una revisión manual.
- El ciclo usa la duración total de la fila FAO-56 seleccionada, solo si el mes de siembra coincide con la columna "Plant Date"; se contrasta con el rango gmin–gmax de EcoCrop.

Ejemplo `california_fao56.input.json` (36,59, −119,52): trigo de invierno sembrado el 2023-12-01 → ET₀ 481,9 mm, ETc 414,5–474,8 mm, lluvia 394,7 mm (180 días). Maíz sembrado el 2023-04-01 → ET₀ 875,2 mm; la ETc queda pendiente del Kc inicial. Agua `unknown` hasta que se declaren disponibilidad, eficiencia y agua inicial del suelo; resultado `abstained`.

Pruebas `tests/test_water_requirement.py` (9): Ejemplo 18 FAO-56, integridad de tablas y fusiones de superíndices, curva Kc y ec. 62, requerimiento real del trigo con procedencia (hash POWER, período, altitud), desconocidos (Kc inicial en blanco, mes de siembra fuera de fila, L_dev ambiguo, coordenadas sin serie, selección sin procedencia), PDF alterado, estados del agua por cotas, integración factible con agua calculada e infactibilidad cuando el presupuesto es menor que la cota inferior.

## Kc inicial calculado (FAO-56 Anexo 7, PDF pp. 289–294)

Forma numérica de las Figuras 29–30: ec. 7-1 (Eso = 1,15·ET₀), 7-3/7-4 (Kc ini ≤ 1,15), 7-7 (tw = L_ini / (nw + 0,5)), 7-8 (lámina media) y parámetros TEW/REW de las Figuras 29, 30a (suelo grueso) y 30b (medio/fino). Interpolación por lámina con la ec. 59. Eventos: días con agua < 0,2·ET₀ se ignoran y los días contiguos forman un solo evento.

- Datos: lluvia diaria POWER y ET₀ calculada en la etapa inicial, más los riegos declarados (mojado de toda la superficie; surco o goteo con fw < 1 no está soportado).
- Intervalo: como la lluvia infiltrada es desconocida (escorrentía), se evalúan dos escenarios (lluvia infiltrada por completo e ignorada) y se toma la envolvente. Si no se declara la textura del suelo (`parcel.soil.texture` = coarse/medium/fine), se usan las Figuras 30a y 30b.
- Validación: Figura 30a = 0,75, igual al Anexo; interpolación = 0,60, igual al Ejemplo 25. Para la Figura 29 la ec. 7-3 da 0,533. El Ejemplo 25 lee ≈0,55 del gráfico y el Ejemplo 7-1 imprime 0,57, un error aritmético del manual: sus propios datos dan 0,533.

Ejemplo `california_fao56`: maíz sembrado el 2023-04-01 con etapa inicial de secano declarada. Hubo 1 evento de lluvia (1,1 mm) en 30 días, así que el Kc inicial queda en 0,045–0,134 (suelo seco) y la ETc en 751–825 mm.
