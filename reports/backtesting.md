# Backtesting de rutas: calibración 1981-2015, prueba 2016-2024

Generado por `scripts/backtest.py` con `src/backtesting.py`. Detalle año por año en `data/processed/backtest_<piloto>.json`.

**Pregunta:** ¿la ruta calibrada con el pasado tuvo menos días de helada y menos déficit de agua que un monocultivo en 2016-2024?

## Método

- Las rutas, la ventana y los cultivos elegibles se recalculan solo con 1981-2015 (ET0 1984-2015: la radiación de POWER empieza en 1984).
- La ruta se siembra tal cual, una campaña por año desde el mes de inicio calibrado, cada cultivo durante su propio ciclo mínimo. 2016-2024 son 9 años = 3 ciclos completos: cada cultivo cuenta 3 veces.
- El monocultivo es el mismo cultivo cada año en la misma ventana. **No hay fuente local del monocultivo típico** (FAOSTAT local solo trae rendimiento; NASS local solo trigo de Fresno), así que se compara contra los 15 cultivos y el típico queda en `config/backtesting_baseline.json`.
- Días de helada: días de la ventana con T2M_MIN bajo la temperatura letal EcoCrop **de cada cultivo**.
- Déficit: max(0, Kc_mid × ET0 − lluvia) en la ventana. Solo existe para los cultivos con Kc FAO-56 verificado (maíz, soja, cebada, avena, lenteja, trigo, papa, alfalfa).
- Años con lluvia < óptimo: lluvia anual de `climate_annual_<piloto>.csv` bajo el mínimo óptimo EcoCrop; es el criterio que el puntaje de agua usa sin Kc.
- El estado en calibración dice si ese monocultivo era elegible en la ventana. Comparar contra uno **excluido** (p. ej. arroz o yuca) no es una comparación justa: se muestra solo para que nada quede oculto.
- Un total existe solo si todos los años se conocen. Si no, se escribe "desconocido (k/9 años)". **Nunca se suma un faltante como cero.**

## Resumen: rutas contra el monocultivo típico declarado

Monocultivo típico: el cultivo con mayor superficie cosechada media 1981-2015 en el país (FAOSTAT Production_Crops_Livestock, `data/raw/faostat/crops_livestock_global.zip`, elemento Area harvested (5312), SHA-256 `c5835418c18f…`). Es **nacional**: no prueba que domine en el punto (en el Valle Central de California es dudoso).

"menos" = la ruta tuvo menos que el monocultivo (mejor). Totales 2016-2024.

| Piloto | Típico | Ruta | Días de helada | Déficit (mm) | Años lluvia < óptimo |
|---|---|---|---|---|---|
| Huancabamba, Piura (PE) | maize (436,511 ha en Peru) | ruta_agua | desconocido | 942.1 vs 1137.7 → **menos** | 6 vs 8 → **menos** |
| Huancabamba, Piura (PE) | maize (436,511 ha en Peru) | ruta_suelo | desconocido | 942.1 vs 1137.7 → **menos** | 7 vs 8 → **menos** |
| Piura sur (PE) | maize (436,511 ha en Peru) | ruta_agua | desconocido | 1691.3 vs 1808.1 → **menos** | 8 vs 9 → **menos** |
| Piura sur (PE) | maize (436,511 ha en Peru) | ruta_suelo | desconocido | 1691.3 vs 1808.1 → **menos** | 8 vs 9 → **menos** |
| Iowa central (US) | maize (29,410,943 ha en United States of America) | ruta_agua | desconocido | 1494.3 vs 1869.8 → **menos** | 0 vs 0 → **igual** |
| Iowa central (US) | maize (29,410,943 ha en United States of America) | ruta_suelo | desconocido | 1494.3 vs 1869.8 → **menos** | 1 vs 0 → **más** |
| Nakuru (KE) | maize (1,582,661 ha en Kenya) | ruta_agua | desconocido | 1207.5 vs 1772.8 → **menos** | 0 vs 0 → **igual** |
| Nakuru (KE) | maize (1,582,661 ha en Kenya) | ruta_suelo | desconocido | 1207.5 vs 1772.8 → **menos** | 0 vs 0 → **igual** |

## piura_1 — Huancabamba, Piura (PE)

Ventana calibrada: inicio ene · elegibles en 1981-2015: wheat, potato, barley, sunflower, tarwi, cassava, clover_red, alfalfa
Rutas calibradas iguales a las del período completo: ruta_agua True, ruta_suelo True, ruta_riesgo None
POWER: `data/raw/power/POWER_Point_Daily_19810101_20241231_005d24S_0079d45W_LST.csv` (SHA-256 `80bf5a45ff40…`)

| Ruta (1981-2015) | Secuencia | días de helada | déficit (mm) | años lluvia < óptimo |
|---|---|---|---|---|
| ruta_agua | alfalfa → barley → potato | 0 | 942.1 | 6 |
| ruta_suelo | alfalfa → potato → wheat | 0 | 942.1 | 7 |

| Monocultivo 2016-2024 | estado en calibración | días de helada | déficit (mm) | años lluvia < óptimo |
|---|---|---|---|---|
| maize | desconocido | desconocido (0/9 años) | 1137.7 | 8 |
| wheat | elegible | 0 | 1027.5 | 9 |
| soybean | desconocido | desconocido (0/9 años) | 1027.5 | 8 |
| bean_faba | desconocido | desconocido (0/9 años) | desconocido (0/9 años) | 8 |
| potato | elegible | 0 | 1027.5 | 6 |
| sorghum | desconocido | desconocido (0/9 años) | desconocido (0/9 años) | 2 |
| barley | elegible | 0 | 1027.5 | 6 |
| sunflower | elegible | 0 | desconocido (0/9 años) | 8 |
| lentil | desconocido | desconocido (0/9 años) | 917.3 | 8 |
| tarwi | elegible | 0 | desconocido (0/9 años) | 6 |
| cassava | elegible | 0 | desconocido (0/9 años) | 9 |
| oat | desconocido | 0 | 1420.9 | 8 |
| clover_red | elegible | 0 | desconocido (0/9 años) | 8 |
| rice | excluido | desconocido (0/9 años) | desconocido (0/9 años) | 9 |
| alfalfa | elegible | 0 | 859.2 | 8 |
| bean_common | desconocido | desconocido (0/9 años) | 788.4 | 6 |

Veredicto contra los 15 monocultivos (cuántos monocultivos supera, iguala, pierde o no se puede decidir):

| Ruta | Métrica | menos | igual | más | desconocido |
|---|---|---|---|---|---|
| ruta_agua | días de helada | 0 | 9 | 0 | 7 |
| ruta_agua | déficit (mm) | 6 | 0 | 3 | 7 |
| ruta_agua | años lluvia < óptimo | 11 | 4 | 1 | 0 |
| ruta_suelo | días de helada | 0 | 9 | 0 | 7 |
| ruta_suelo | déficit (mm) | 6 | 0 | 3 | 7 |
| ruta_suelo | años lluvia < óptimo | 11 | 0 | 5 | 0 |

**Monocultivo típico declarado: maize**

- ruta_agua: días de helada desconocido; déficit (mm) menos; años lluvia < óptimo menos
- ruta_suelo: días de helada desconocido; déficit (mm) menos; años lluvia < óptimo menos

## piura_2 — Piura sur (PE)

Ventana calibrada: inicio ene · elegibles en 1981-2015: wheat, potato, barley, sunflower, tarwi, clover_red, alfalfa
Rutas calibradas iguales a las del período completo: ruta_agua True, ruta_suelo True, ruta_riesgo None
POWER: `data/raw/power/POWER_Point_Daily_19810101_20241231_005d34S_0079d42W_LST.csv` (SHA-256 `6e407f2c9ffa…`)

| Ruta (1981-2015) | Secuencia | días de helada | déficit (mm) | años lluvia < óptimo |
|---|---|---|---|---|
| ruta_agua | alfalfa → barley → potato | 0 | 1691.3 | 8 |
| ruta_suelo | alfalfa → potato → wheat | 0 | 1691.3 | 8 |

| Monocultivo 2016-2024 | estado en calibración | días de helada | déficit (mm) | años lluvia < óptimo |
|---|---|---|---|---|
| maize | desconocido | desconocido (0/9 años) | 1808.1 | 9 |
| wheat | elegible | 0 | 1689.7 | 9 |
| soybean | excluido | desconocido (0/9 años) | 1689.7 | 9 |
| bean_faba | desconocido | desconocido (0/9 años) | desconocido (0/9 años) | 9 |
| potato | elegible | 0 | 1689.7 | 8 |
| sorghum | desconocido | desconocido (0/9 años) | desconocido (0/9 años) | 7 |
| barley | elegible | 0 | 1689.7 | 8 |
| sunflower | elegible | 0 | desconocido (0/9 años) | 9 |
| lentil | desconocido | desconocido (0/9 años) | 1571.1 | 9 |
| tarwi | elegible | 0 | desconocido (0/9 años) | 8 |
| cassava | excluido | 0 | desconocido (0/9 años) | 9 |
| oat | desconocido | 0 | 2278.3 | 9 |
| clover_red | elegible | 0 | desconocido (0/9 años) | 9 |
| rice | excluido | desconocido (0/9 años) | desconocido (0/9 años) | 9 |
| alfalfa | elegible | 0 | 1632.1 | 9 |
| bean_common | desconocido | desconocido (0/9 años) | 1272.6 | 8 |

Veredicto contra los 15 monocultivos (cuántos monocultivos supera, iguala, pierde o no se puede decidir):

| Ruta | Métrica | menos | igual | más | desconocido |
|---|---|---|---|---|---|
| ruta_agua | días de helada | 0 | 9 | 0 | 7 |
| ruta_agua | déficit (mm) | 2 | 0 | 7 | 7 |
| ruta_agua | años lluvia < óptimo | 11 | 4 | 1 | 0 |
| ruta_suelo | días de helada | 0 | 9 | 0 | 7 |
| ruta_suelo | déficit (mm) | 2 | 0 | 7 | 7 |
| ruta_suelo | años lluvia < óptimo | 11 | 4 | 1 | 0 |

**Monocultivo típico declarado: maize**

- ruta_agua: días de helada desconocido; déficit (mm) menos; años lluvia < óptimo menos
- ruta_suelo: días de helada desconocido; déficit (mm) menos; años lluvia < óptimo menos

## piura_3 — Piura norte (PE)

Sin backtesting: calibration_no_valid_rotation (ninguna combinación de tres cultivos respeta el cambio de familia, contando el paso de la última campaña a la primera).

## iowa — Iowa central (US)

Ventana calibrada: inicio may · elegibles en 1981-2015: wheat, potato, barley, sunflower, tarwi, clover_red, alfalfa
Rutas calibradas iguales a las del período completo: ruta_agua True, ruta_suelo True, ruta_riesgo None
POWER: `data/raw/power/POWER_Point_Daily_19810101_20241231_042d03N_0093d62W_LST.csv` (SHA-256 `3cd5900cbf4e…`)

| Ruta (1981-2015) | Secuencia | días de helada | déficit (mm) | años lluvia < óptimo |
|---|---|---|---|---|
| ruta_agua | alfalfa → barley → potato | 0 | 1494.3 | 0 |
| ruta_suelo | alfalfa → potato → wheat | 0 | 1494.3 | 1 |

| Monocultivo 2016-2024 | estado en calibración | días de helada | déficit (mm) | años lluvia < óptimo |
|---|---|---|---|---|
| maize | desconocido | desconocido (0/9 años) | 1869.8 | 0 |
| wheat | elegible | 0 | 1680 | 5 |
| soybean | desconocido | desconocido (0/9 años) | 1680 | 0 |
| bean_faba | desconocido | desconocido (0/9 años) | desconocido (0/9 años) | 2 |
| potato | elegible | 0 | 1680 | 0 |
| sorghum | desconocido | desconocido (0/9 años) | desconocido (0/9 años) | 0 |
| barley | elegible | 0 | 1680 | 0 |
| sunflower | elegible | 0 | desconocido (0/9 años) | 0 |
| lentil | desconocido | desconocido (0/9 años) | 1497.2 | 0 |
| tarwi | elegible | 0 | desconocido (0/9 años) | 0 |
| cassava | excluido | 44 | desconocido (0/9 años) | 8 |
| oat | desconocido | 0 | 2302.8 | 0 |
| clover_red | elegible | 0 | desconocido (0/9 años) | 4 |
| rice | excluido | desconocido (0/9 años) | desconocido (0/9 años) | 9 |
| alfalfa | elegible | 0 | 1318.8 | 0 |
| bean_common | desconocido | desconocido (0/9 años) | 863.4 | 0 |

Veredicto contra los 15 monocultivos (cuántos monocultivos supera, iguala, pierde o no se puede decidir):

| Ruta | Métrica | menos | igual | más | desconocido |
|---|---|---|---|---|---|
| ruta_agua | días de helada | 1 | 8 | 0 | 7 |
| ruta_agua | déficit (mm) | 7 | 0 | 2 | 7 |
| ruta_agua | años lluvia < óptimo | 5 | 11 | 0 | 0 |
| ruta_suelo | días de helada | 1 | 8 | 0 | 7 |
| ruta_suelo | déficit (mm) | 7 | 0 | 2 | 7 |
| ruta_suelo | años lluvia < óptimo | 5 | 0 | 11 | 0 |

**Monocultivo típico declarado: maize**

- ruta_agua: días de helada desconocido; déficit (mm) menos; años lluvia < óptimo igual
- ruta_suelo: días de helada desconocido; déficit (mm) menos; años lluvia < óptimo más

## kenia — Nakuru (KE)

Ventana calibrada: inicio ene · elegibles en 1981-2015: wheat, potato, barley, sunflower, tarwi, clover_red, alfalfa
Rutas calibradas iguales a las del período completo: ruta_agua True, ruta_suelo True, ruta_riesgo None
POWER: `data/raw/power/POWER_Point_Daily_19810101_20241231_000d33S_0035d94E_LST.csv` (SHA-256 `ea7f0b478e89…`)

| Ruta (1981-2015) | Secuencia | días de helada | déficit (mm) | años lluvia < óptimo |
|---|---|---|---|---|
| ruta_agua | alfalfa → barley → potato | 0 | 1207.5 | 0 |
| ruta_suelo | alfalfa → potato → wheat | 0 | 1207.5 | 0 |

| Monocultivo 2016-2024 | estado en calibración | días de helada | déficit (mm) | años lluvia < óptimo |
|---|---|---|---|---|
| maize | excluido | desconocido (0/9 años) | 1772.8 | 0 |
| wheat | elegible | 0 | 1642.2 | 0 |
| soybean | excluido | desconocido (0/9 años) | 1642.2 | 0 |
| bean_faba | desconocido | desconocido (0/9 años) | desconocido (0/9 años) | 0 |
| potato | elegible | 0 | 1642.2 | 0 |
| sorghum | desconocido | desconocido (0/9 años) | desconocido (0/9 años) | 0 |
| barley | elegible | 0 | 1642.2 | 0 |
| sunflower | elegible | 0 | desconocido (0/9 años) | 0 |
| lentil | desconocido | desconocido (0/9 años) | 1511.5 | 0 |
| tarwi | elegible | 0 | desconocido (0/9 años) | 0 |
| cassava | excluido | 0 | desconocido (0/9 años) | 0 |
| oat | desconocido | 0 | 1178 | 0 |
| clover_red | elegible | 0 | desconocido (0/9 años) | 0 |
| rice | excluido | desconocido (0/9 años) | desconocido (0/9 años) | 4 |
| alfalfa | elegible | 0 | 652.4 | 0 |
| bean_common | desconocido | desconocido (0/9 años) | 1357.2 | 0 |

Veredicto contra los 15 monocultivos (cuántos monocultivos supera, iguala, pierde o no se puede decidir):

| Ruta | Métrica | menos | igual | más | desconocido |
|---|---|---|---|---|---|
| ruta_agua | días de helada | 0 | 9 | 0 | 7 |
| ruta_agua | déficit (mm) | 7 | 0 | 2 | 7 |
| ruta_agua | años lluvia < óptimo | 1 | 15 | 0 | 0 |
| ruta_suelo | días de helada | 0 | 9 | 0 | 7 |
| ruta_suelo | déficit (mm) | 7 | 0 | 2 | 7 |
| ruta_suelo | años lluvia < óptimo | 1 | 15 | 0 | 0 |

**Monocultivo típico declarado: maize**

- ruta_agua: días de helada desconocido; déficit (mm) menos; años lluvia < óptimo igual
- ruta_suelo: días de helada desconocido; déficit (mm) menos; años lluvia < óptimo igual

## california — Valle Central (US)

Sin backtesting: calibration_no_known_water (ninguna rotación tiene agua conocida (todas incluyen un cultivo sin Kc FAO-56)).

## Lectura y limitaciones

- **Ruta y monocultivo enfrentan el mismo clima cada año.** La diferencia sale solo de los umbrales de cada cultivo: el mínimo óptimo de lluvia de EcoCrop (maíz 600 mm; trébol 700, trigo 750, papa y cebada 500) y el Kc_medio (alfalfa 0,95, cebada/trigo/papa 1,15 frente a maíz 1,20). El déficit "menos" contra maíz es exactamente esa diferencia de Kc.
- Contra maíz la helada es siempre desconocida: EcoCrop no trae temperatura letal válida para maíz.
- **Déficit de agua: las rutas usan Kc FAO-56 verificado** (alfalfa 0,95; cebada, trigo y papa 1,15; maíz 1,20). Desde 2026-11-14 el motor solo puntúa agua con Kc: girasol y trébol no tienen Kc y sus rotaciones quedan fuera de las rutas. Por eso Piura 3 y California pueden quedar sin rutas.
- El "menos déficit" de las rutas frente al maíz viene sobre todo de la alfalfa (Kc 0,95). Kc_medio × ET0 de toda la ventana es una cifra de tamizaje que sobreestima la demanda fuera de mitad de ciclo; no es la ETc por etapas.
- **Helada: el backtest no discrimina.** Todos los cultivos elegibles tienen la misma temperatura letal en EcoCrop (0 °C), así que ruta y monocultivo de un cultivo elegible cuentan los mismos días. Maíz, soja, haba, sorgo, lenteja y arroz no tienen temperatura letal: contra ellos la helada es desconocida.
- **En las ventanas calibradas no hubo ningún día bajo la temperatura letal en 2016-2024, en ningún piloto.** El "0" de helada es real en POWER, pero no distingue rutas de monocultivos.
- **Huancabamba (piura_1): 0 heladas en 44 años según POWER.** MERRA-2 tiene celdas de ~50 km y suaviza la montaña; esto no prueba que no hiele.
- El puntaje de suelo se satura en 100 (tres criterios documentados), por eso no entra en el backtest.
- Cada campaña empieza en el mes calibrado y dura el ciclo mínimo de EcoCrop, no el calendario real; el calendario FAO no cubre EE. UU.
- Las rutas con barbecho no se prueban aquí: tienen un año sin cultivo cada tres y su total no es comparable con un monocultivo de nueve campañas.
- No hay dataset local de reglas de rotación ni pendiente SRTM fuera de California.
