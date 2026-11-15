# Estado real del repositorio frente al plan del hackathon

Verificado el 2026-11-14 inspeccionando los archivos, no los documentos previos.
**`ESTADO_Y_PLAN.md` está desactualizado**: dice 18 pruebas y "NASA POWER sin descargar"; ambas cosas ya no son ciertas.

## Verificado en disco

| Elemento | Estado real |
|---|---|
| Pruebas | ~92 aprobadas, 3 omitidas (originales vacíos de SMAP, MODIS y GPM de media hora) |
| NASA POWER | **Un solo punto**: 36,59 / −119,52 (valle de San Joaquín, California), 2021-01-01 a 2025-12-31, LST, con elevación MERRA-2 en el encabezado |
| GPM IMERG mensual | 57 gránulos validados; lluvia mensual **ya extraída para los 6 puntos piloto** (Piura ×3, Iowa, Kenia, California), 399 filas |
| Sentinel-2 NDVI | 426 filas para los 6 pilotos, 2021-01 a 2026-11, **0 filas usables** (marcadas inconsistentes) |
| SRTM | Solo el tile N37W120 (California) |
| MODIS | Solo el tile h08v05 (suroeste de EE. UU.) |
| Calendario FAO | 57 países, incluye PE y KE; **no incluye EE. UU.** |
| GAEZ | 14 capas globales; códigos SIX sin leyenda verificada, se usan solo como contexto |
| EcoCrop | 2568 especies validadas; los 15 cultivos de la biblioteca existen con rangos reales |
| FAO-56 | Kc de la Tabla 12 (57 etiquetas) y 18 filas de la Tabla 11 con duraciones de etapa |
| Motor | Optimizador determinista + restricciones de tres estados + evidencia + ET₀/ETc + Kc inicial |

## Lo que falta, por orden de bloqueo

1. **POWER para los demás puntos.** Es lo único que bloquea el perfil climático, el riesgo de helada y el backtesting fuera de California. `scripts/download_power_points.py` lo resuelve; la API es pública y no pide credenciales.
2. **Serie larga.** Con 2021–2025 no existe el backtesting 1981–2015 / 2016–2024 que propone el plan.
3. **Capa de puntajes (agua, suelo, riesgo), frente de Pareto y las 3 rutas.** No existe; es el núcleo del hackathon.
4. **Altitud fuera de California.** SRTM no cubre Piura ni Kenia, pero el encabezado de POWER trae la elevación MERRA-2 de cualquier punto y ya se usa para la ET₀.
5. **Helada letal ausente** para maíz, soja, haba, sorgo, lenteja y arroz: EcoCrop no trae `ktmp` válido para esas seis especies, así que el puntaje de helada quedaría desconocido para ellas.
6. **NDVI bloqueado por calidad, no por descarga.** Ninguna fila de Sentinel-2 es usable y MODIS no cubre los pilotos.
7. **Figma, radar, calendario de riesgo, informe, video y pitch.**

## La decisión pendiente

El motor actual **se abstiene** cuando falta información, y hoy se abstendría en los tres pilotos. La demo necesita mostrar tres rutas. La salida recomendada es no relajar el motor, sino añadir encima una capa de puntajes que ordene bajo supuestos declarados y muestre al lado qué proviene de datos, qué declaró el agricultor y qué se desconoce.

## Correcciones al plan tal como está escrito

- **El CSV del paso 3 trae valores sin fuente** (maíz: helada −2 °C, lluvia mínima 500 mm, altitud 2800 m). EcoCrop tiene esos campos verificados; `src/crop_library.py` los toma de ahí y deja en nulo lo que no está validado.
- **La regla de "no repetir familia"** usaría `crop_family` de la FAO, que es un grupo de uso ("OTHER CROPS"). La familia botánica real está en `famname` de EcoCrop (Gramineae, Leguminosae, Solanaceae…).
- **La fijación de nitrógeno no se almacena.** La biblioteca solo registra si la especie pertenece a Leguminosae; la nodulación depende de la especie y del manejo.
- **`frente_pareto` no calcula un frente de Pareto**: elige el mejor en cada dimensión por separado.
- **`puntaje_agua` multiplica la ET₀ anual por el Kc medio**, lo que sobreestima la demanda. `src/water_requirement.py` ya calcula la ETc por etapas, que es el procedimiento correcto.
