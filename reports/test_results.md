# Pruebas y verificación final

Fecha de corte de la auditoría: 2026-11-14, America/Lima.

Comando: `.venv/bin/python -m pytest -q`

Resultado final: **44 passed, 3 skipped in 3.31s**. Sin fallos.

Las tres omisiones son las comparaciones de gránulos reales SMAP, MODIS y GPM de media hora: sus archivos originales locales están vacíos. No se consideran fuentes validadas. La prueba nueva `test_empty_originals_excluded_from_observations` verifica que la auditoría detecta este estado y que esos derivados no entran en las observaciones integradas. La comparación real SRTM sí se ejecutó.

Antes de los cambios, la suite existente dio 28 aprobadas y tres fallos de hash precisamente por esos originales vacíos. Se conservó el requisito de comparar hashes cuando el original está disponible; se explicita la imposibilidad de la comparación cuando está vacío. No se reparó ni eliminó ningún original.

Cobertura añadida:

- GPM legible pero incorrecto: unidades, fechas/límites, coordenadas repetidas, precipitación negativa y producto equivocado se rechazan.
- Extracción GPM: orden longitud/latitud, selección de celda, FillValue a NaN, QA preservada y rechazo de coordenadas inválidas.
- Meses únicos/duplicados/ausentes; comparación con los 57 archivos reales y sus hashes.
- Sentinel: inconsistencias, duplicados, faltantes y mes incompleto, sin reparar valores de origen.
- NASS: códigos FIPS con ceros iniciales, valores con separador de miles, supresión `(D)`, cero válido, unidades y duplicados.
- Consultas por solapamiento de intervalos y cultivo nativo, sin extrapolar a ubicaciones cercanas.
- Referencias FAO-56/calendarios y consulta real GPM; hashes de procedencia exigidos.
- Fechas estacionales imposibles y columnas nullable de pandas: marca inválidas y conserva faltantes sin asignar años.

Verificación posterior a las pruebas:

- 165 originales: SHA-256 y tamaños idénticos al inventario de entrada.
- Siete Parquet nuevos reabiertos y comprobados contra sus hashes de salida.
- Filas: Sentinel 426; NASS 392; índice GPM 57; puntos GPM 399; observaciones 14.425; ubicaciones 8; catálogo 110 manifiestos (no 110 datasets únicos).
- Los 57 sidecars mensuales ya tenían tamaños/hashes coincidentes. Se añadió la validación científica, sin sustituir hashes correctos.
- Los derivados nuevos suman aproximadamente 331 KB, sin expansión de grilla global.
- Versiones de dependencias en `reports/audit_environment.txt`.

Estas pruebas verifican integridad, procesamiento y contratos de consulta; no exactitud contra mediciones de campo ni suficiencia para entrenar modelos. Las limitaciones científicas permanecen en `reports/local_audit.md`.
