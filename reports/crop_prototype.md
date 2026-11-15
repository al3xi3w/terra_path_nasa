# Prototipo reproducible de cribado climático

## Ejecutar

Desde FieldShift_Trabajo:

```bash
.venv/bin/python scripts/evaluate_crops.py --crops 'Zea mays' 'Triticum aestivum'
.venv/bin/python scripts/evaluate_crops.py --crops 'Glycine max' --start 2021-01 --end 2024-12 --current-crop 'Zea mays'
.venv/bin/python -m pytest -q
```

Resultado completo del primer comando: reports/crop_screen_example.json. Tabla compacta: data/processed/california_monthly_climate.parquet. Funciones: src/crop_screen.py. No red, entrenamiento, interfaz ni optimizador.

## Datos y unidades

57 meses enero 2021–septiembre 2025 en 36.59/-119.52. POWER es un producto estimado/modelado servido como extracción puntual, no una estación meteorológica: soporte aproximado 0.5x0.625 grados para meteorología y 1 grado para solar. GPM es una estimación de grilla de 0.1 grados; se conserva el centro de la celda más cercana, hash original, duración y QA. No son dos mediciones directas de parcela ni observaciones globalmente representativas.

Se verifican hashes de entrada/salida POWER, coordenadas, LST, unidades, fechas únicas, meses GPM y sus hashes. Se reutiliza DataStore para seleccionar GPM. POWER agrega medias diarias de temperatura, humedad y viento mediante media; extremos térmicos mediante mínimo/máximo; precipitación mediante suma mm y radiación mediante suma MJ/m². Un mes incompleto o una variable con días faltantes queda sin agregado utilizable. Cada fila registra días esperados/observados.

Los meses locales LST se emparejan con meses UTC GPM por etiqueta de calendario; no hay alineamiento exacto de instantes. GPM conserva tasa media mm/hr, sin convertirla en lluvia acumulada ni promediarla con POWER. Su índice QA no recibe umbral arbitrario. La clasificación utiliza lluvia POWER, cuya agregación diaria es explícita; GPM queda como contraste independiente pendiente de política QA y conversión validada. No se afirma acuerdo entre productos.

## Reglas y supuestos

EcoCrop se consulta por nombre científico exacto con verificación de procedencia. Solo se admiten límites *_usable con *_valid y orden consistente. Los límites de precipitación anual se comparan exclusivamente con años completos: 2021–2024 por defecto. Enero–septiembre 2025 no se extrapola a un año. Temperatura anual: media ponderada por días. Los extremos mensuales permanecen disponibles, pero no son umbrales de daño demostrados.

Regla de cribado explícita: fuera del rango absoluto = unfavorable; dentro del óptimo = favorable; entre límites absolutos y óptimos = marginal y evaluación global insufficiently_documented salvo evidencia desfavorable en otro factor. Un factor desfavorable basta para señalar un riesgo observado durante el horizonte; no significa que todos los años sean desfavorables. Favorable solo describe las reglas climáticas evaluadas, no aptitud agronómica integral. Sin factores suficientes se devuelve insufficiently_documented.

Comparar la temperatura media anual con los rangos EcoCrop es una **hipótesis de cribado**, no una función biológica calibrada ni evaluación de temperatura durante el ciclo. Horizonte, candidatos y cultivo actual son parámetros configurables. Los rangos de origen y unidades no se alteran para obtener un resultado deseado. No hay pesos, etiquetas, rendimientos ni beneficios de rotación inventados. Un cultivo no localizado o ambiguo devuelve información insuficiente.

GAEZ: los archivos locales usan AgERA5 y siguen excluidos bajo la restricción de no utilizar ERA5. Se reutiliza la conclusión de procedencia de la auditoría; no se convierten en evidencia de aptitud ni se muestrean para este cálculo. Habilitar una fuente de aptitud compatible requiere resolver esa restricción y sus unidades.

## Ejemplo real

Zea mays: unfavorable para el cribado del horizonte 2021–2024. POWER aporta 382.70 mm en 2021 y 335.11 mm en 2022, por debajo del mínimo anual EcoCrop de 400 mm. En 2023 aporta 711.12 mm (óptimo 600–1200); 2024 aporta 483.82 mm (marginal). Las temperaturas medias anuales 19.76, 20.02, 18.46 y 20.12 °C están dentro del óptimo usado, 18–33 °C. No se conoce si riego disponible compensa diferencias.

Triticum aestivum: insufficiently_documented. Las lluvias anuales están dentro de límites absolutos 300–1600 mm, pero por debajo del óptimo 750–900 mm. Las temperaturas anuales pasan el cribado, sin identificar estación de crecimiento ni variedad.

## Rotación: estructura y límites

rotation_context registra cultivo actual (opcional/desconocido), candidatos, coordenadas y horizonte. Devuelve recommendation=null y restricciones pendientes. Proporcionar cultivo actual no demuestra una transición válida.

Disponibles: rangos ecológicos por campo y controles climáticos. Faltan correspondencias de familias y reglas de transición verificadas, calendario local y ciclo, historial, suelo/nutrientes, agua de riego, costos y objetivos. El calendario nacional no se asigna automáticamente a este punto. No hay rendimiento etiquetado alineado, ni efecto causal observado de una rotación. Las fuentes son estimaciones y referencias agronómicas; ninguna salida es medición de éxito de cultivo.

Para avanzar: definir parcela y temporadas; verificar taxonomía/familias y calendario; aportar estado del suelo, cultivo previo y balance hídrico; acordar restricciones y objetivo. Primero validar reglas con casos conocidos; después diseñar un optimizador que distinga desconocido de factible. No entrenar un modelo con estas clasificaciones como si fueran observaciones independientes.

Validación: **49 aprobadas, 3 omitidas** (originales SMAP/MODIS/GPM de media hora vacíos). Pruebas nuevas cubren 57 meses, suma real, año parcial, cultivo desconocido, límites óptimos/absolutos, faltantes y abstención de recomendar rotaciones. Los originales permanecen intactos.
