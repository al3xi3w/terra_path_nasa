# Datos de Terrapath

Los datos **no están en este repositorio**. Las carpetas `data/` y `app/data/` están en `.gitignore` porque:

- pesan unos 1,3 GB (sobre todo `data/raw/`), más de lo que GitHub acepta cómodamente;
- vienen de terceros (NASA, FAO, USDA), cada uno con sus propias condiciones de uso;
- se pueden volver a descargar y regenerar con los scripts del proyecto.

Sin estas carpetas el código está completo, pero el motor, la app y la mayoría de las pruebas no tienen datos con qué correr.

## Estructura esperada

```
data/
├── raw/          originales tal como se descargaron (nunca se modifican)
├── processed/    salidas del motor: perfiles de clima, rutas, backtest, IMERG por piloto, terreno…
├── metadata/     un archivo .json por descarga: URL, bytes, SHA-256, fecha
└── integrated/   observaciones, lugares y catálogo en formato largo
app/data/
└── app_data.js   datos que lee la app (se genera, no se edita a mano)
```

Cada archivo descargado deja un sidecar en `data/metadata/` con su URL y su SHA-256. Así se puede comprobar que un dato regenerado es el mismo que se usó.

## Fuentes

| Carpeta | Fuente | Qué es | Cómo se obtiene | Credenciales |
|---|---|---|---|---|
| `raw/power/` | [NASA POWER](https://power.larc.nasa.gov/) | Clima diario 1981-2024 (temperatura, lluvia, radiación, humedad, viento) por piloto | `python scripts/download_power_points.py --start 1981-01-01 --end 2024-12-31` | No |
| `raw/srtm/` | [NASA SRTMGL1 v003](https://www.earthdata.nasa.gov/data/catalog/lpcloud-srtmgl1-003) | Altitud a 30 m (tiles S06W080, S05W080, N42W094, S01E035, N36W121) | `Pipeline.earth('srtm', …, download=True)` en `src/pipeline.py`, y luego `python -m src.terrain` | Earthdata |
| `raw/gpm_monthly/` | [NASA GPM IMERG mensual V07](https://gpm.nasa.gov/data/imerg) | Lluvia satelital 2021-2025 (57 meses) | `python scripts/recuperar_gpm.py` | Earthdata |
| `processed/imerg_*` | GPM IMERG mensual V07 (GES DISC) | Lluvia 2001-2020 en los pilotos; el archivo se borra después de extraer cada mes | `python scripts/imerg_history.py` y luego `--export` | Earthdata + autorizar «NASA GESDISC DATA ARCHIVE» |
| `raw/fao56/` | [FAO-56](https://www.fao.org/3/x0490e/x0490e00.htm) | PDF de la FAO: coeficientes de cultivo Kc (Tabla 12) | Descarga manual del PDF como `FAO56.pdf` | No |
| `raw/ecocrop/` | [FAO EcoCrop](https://gaez.fao.org/pages/ecocrop) | Límites de cada cultivo: temperatura, lluvia, altitud, ciclo | Archivo `ecocrop.parquet` de la etapa de adquisición | No |
| `raw/faostat/` | [FAOSTAT](https://www.fao.org/faostat/) | Superficie cosechada y rendimientos (para elegir el cultivo típico) | Descarga manual de *Crops and livestock products*, global, como `crops_livestock_global.zip` | No |
| `raw/agronomy/` | [FAO Crop Calendar](https://api-cropcalendar.apps.fao.org/) | Calendarios de siembra por país | Etapa de adquisición de `src/pipeline.py` | No |
| `raw/gaez/`, `raw/modis/`, `raw/smap/`, `raw/gpm/`, `raw/usda/` | GAEZ, MODIS, SMAP, IMERG de media hora, USDA NASS | Fuentes auditadas en etapas anteriores; el motor de rutas no las usa | Ver `config/sources.yaml` y `reports/local_audit.md` | Algunas, Earthdata |

Las URLs y versiones exactas de cada producto están en `config/sources.yaml`. Los pilotos y sus coordenadas están en `config/pilots.json`.

## Credenciales de Earthdata

SRTM e IMERG piden una cuenta gratuita de [NASA Earthdata](https://urs.earthdata.nasa.gov/). Las credenciales se leen **solo** de variables de entorno y nunca se guardan en el proyecto:

```bash
export EARTHDATA_USERNAME='tu_usuario'
export EARTHDATA_PASSWORD='tu_contraseña'   # entre comillas simples si tiene $ u otros símbolos
```

Para IMERG, además, en Earthdata hay que ir a *Applications → Authorized Apps* y autorizar **NASA GESDISC DATA ARCHIVE**.

## Regenerar todo, en orden

```bash
python3 -m venv .venv && .venv/bin/python -m pip install -r requirements.txt
# 1. Datos originales (ver la tabla de arriba)
.venv/bin/python scripts/download_power_points.py --start 1981-01-01 --end 2024-12-31
# 2. Auditoría e integración de lo que haya en data/raw
.venv/bin/python scripts/run_pipeline.py audit
# 3. Clima, terreno, rutas, backtest, sensibilidad e IMERG
.venv/bin/python scripts/climate_profiles.py
.venv/bin/python -m src.terrain
.venv/bin/python scripts/rotation_routes.py
.venv/bin/python scripts/backtest.py
.venv/bin/python scripts/sensitivity.py
.venv/bin/python scripts/imerg_history.py && .venv/bin/python scripts/imerg_history.py --export
# 4. Figuras y datos de la app
.venv/bin/python scripts/figures.py
.venv/bin/python scripts/build_app.py
# 5. Pruebas
.venv/bin/python -m pytest -q
```

## Reglas sobre los datos

- `data/raw/` no se modifica nunca: todo lo derivado va a `data/processed/`.
- No se inventan valores. Un dato que la fuente no trae queda nulo y se reporta como desconocido; nunca cuenta como cero ni como favorable.
- Toda salida guarda su procedencia: fuente, archivo, SHA-256, variable, unidad, período y ubicación.
