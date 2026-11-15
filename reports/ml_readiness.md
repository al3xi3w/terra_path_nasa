# Preparación real para ML y rotaciones

Corte: 2026-11-14. Evaluación local, sin entrenamiento ni optimizador. Se reutilizan lectores y consultas de la auditoría. Las 14.425 observaciones son valores de variables, no 14.425 ejemplos supervisados.

## Calidad y tratamiento

Sentinel contiene 426 filas de seis pilotos y 71 meses. Hay 23 filas sin índices; los 403 registros con NDVI presente violan el orden de estadísticas o sitúan la media fuera de sus extremos. 27 filas contienen algún NDVI fuera de [-1,1]; solo 379 medias NDVI están dentro del intervalo. La media llega aproximadamente de -2.907195e11 a 4.189830e10: no puede interpretarse como NDVI válido. NDMI presenta 402 inconsistencias, dos filas fuera de rango y 23 faltantes. Noviembre 2026 es incompleto.

La causa demostrable es la incompatibilidad matemática de columnas que se presentan como resúmenes del mismo índice. La causa del cálculo no se puede identificar con este CSV: no hay escenas, bandas, máscaras, geometrías ni script de exportación. Un denominador próximo a cero podría explicar magnitudes extremas, y agregaciones espaciales/temporales distintas podrían explicar percentiles fuera de extremos, pero son hipótesis, no diagnósticos confirmados. No se recortan a [-1,1], no se reordenan columnas ni se reemplazan medias. Ningún NDVI se habilita para entrenamiento; el único NDMI que pasa el cribado tampoco tiene procedencia suficiente para validación supervisada. El archivo readiness_issues.json identifica fila CSV, piloto, mes, campo, valor y motivo para cada anomalía detectada. Las tablas existentes ya contienen los flags correctos; no se reescriben ni duplican.

Calendarios: se revisaron las 109 filas en 19 países. Hay 31 en meses de 30 días, febrero 30, un día 151 en Timor-Leste y secuencias 41,55,69,83,97,111 en Ruanda. La secuencia sugiere error de edición/arrastre, pero no demuestra el día correcto. Tampoco se puede asumir que 31 significa fin de mes o reemplazar febrero 30 por 28. **Cero correcciones numéricas inequívocas**. Las 109 filas quedan explícitamente no utilizables para programación en el registro de incidencias; se conservan los extremos originales. Las consultas existentes añaden seasonal_date_invalid. Las otras 9.309 filas pasan este control de extremos, no necesariamente todos los requisitos para optimizar: algunas carecen de fechas, zona georreferenciada o duración numérica. Febrero 29 exige revisar el año efectivo; el calendario no aporta un año observado.

Originales vacíos: data/raw/smap/SMAP_L3_SM_P_20240601_R19240_001.h5; data/raw/modis/MOD13Q1.A2024145.h08v05.061.2024162165128.hdf; data/raw/gpm/3B-HHR.MS.MRG.3IMERG.20240601-S000000-E002959.0000.V07B.HDF5. Sus derivados no aportan filas a observations.parquet. No se recuperan por descarga. También permanece vacío un GAEZ. GAEZ con procedencia AgERA5 sigue excluido.

## Compatibilidad y ejemplos reales

- GPM: 57 meses por siete ubicaciones registradas, 399 filas. Son siete series de celdas de 0.1°, no 399 parcelas independientes. Con un retardo mensual hay como máximo 56 pares por serie, 392 candidatos antes de QA, pero las series comparten meses y tres puntos de Piura están próximos; la validación no debe dividir aleatoriamente filas. Son etiquetas futuras de precipitación estimada por el mismo producto, no eventos de daño ni necesidades de riego observadas.
- POWER: 1.826 días con siete variables, un único punto 36.59/-119.52, LST. Son 1.826 vectores diarios, no 12.782 muestras. Hay 57 meses coincidentes con GPM extraído en esa misma coordenada (enero 2021–septiembre 2025). Se pueden comparar/agregar tras documentar LST frente a meses UTC, cobertura diaria y diferencias de soporte. No son observaciones intercambiables ni precipitación de parcela. No se materializa ahora ese cruce.
- Sentinel California está en 36.95/-120.28: no coincide con POWER. Los pilotos restantes tampoco son sustitutos del punto meteorológico. El mosaico SRTM N37W120 cubre aproximadamente 37–38 N y 120–119 O; ninguno de estos dos puntos californianos está dentro. No asignarles elevación de ese mosaico. No hay ejemplos locales completos clima+terreno+etiqueta de aptitud.
- NASS: 392 etiquetas anuales de Fresno, 1945–2021, diez Data Item con subtipos y manejo diferentes. Solo una fila de 2021 coincide **temporalmente** con GPM mensual. Se corrige la interpretación de la etapa anterior: no hay una coincidencia espacial validada. Una celda puntual dentro o cerca de Fresno no representa el rendimiento medio del condado; faltan límites y una agregación espacial con soporte justificable. **Cero ejemplos supervisados clima–rendimiento alineados** en el almacén actual. Incluso una futura agregación válida dejaría una sola etiqueta, insuficiente. No combinar trigo general, irrigado y subtipos como réplicas independientes; conservar BU/ACRE.
- FAOSTAT: 823.058 etiquetas de rendimiento kg/ha, por área/producto/año, 1961–2024. Podrían servir para pronósticos históricos univariados por serie, conservando flags y separando agregados; no están alineadas con clima a su soporte. El conteo de pares temporales válidos por serie no está calculado: no se afirma que haya 823.058 muestras utilizables. Cero ejemplos clima+rendimiento alineados actualmente.
- EcoCrop (2.568 registros), FAO-56 (57 variantes) y calendarios son referencias, no etiquetas observadas. Las 706 especies con alguna anomalía EcoCrop requieren selección por campo *_usable. Solo 26 variantes FAO-56 tienen los tres Kc explícitos. No existen correspondencias taxonómicas revisadas entre todas las fuentes. Mantener códigos/nombres nativos y condiciones de cada variante; no unir por coincidencias aproximadas de texto.

## Modelos por objetivo

**Viable como herramienta determinista de referencia:** cribado climático con rangos EcoCrop válidos y datos del lugar, tras seleccionar manualmente cultivos y períodos compatibles. No entrenar un clasificador de aptitud usando estos mismos umbrales como etiquetas: sería circular. Cero etiquetas observadas de aptitud disponibles; terreno local no alineado. No atribuir causalidad ni probabilidades de éxito.

**Experimental:** pronóstico de precipitación mensual con las siete series GPM; máximo 392 pares de un retardo, con QA pendiente y evaluación temporal común, preferiblemente frente a persistencia y estacionalidad. Solo 57 meses por serie limitan modelos complejos. POWER permite descriptivos de calor, lluvia y humedad durante cinco años, no una climatología extensa ni etiquetas de pérdidas. No hay eventos de daño etiquetados (cero muestras supervisadas de daño).

**Necesidades de agua:** cálculo físico experimental, no ML supervisado. POWER proporciona temperatura, humedad, viento, radiación y precipitación; faltan revisar altura de viento, elevación, radiación neta/estimación, etapa fenológica, ETo, lluvia efectiva y condiciones locales de Kc. No afirmar ETc ni déficit de riego validado. Hay cero demandas de riego observadas y cero ejemplos completos validados cultivo–temporada–agua. Los 57 meses POWER/GPM son candidatos a análisis climático, no etiquetas hídricas. Lluvia no equivale a disponibilidad de agua.

**Rendimiento:** bloqueado para predicción supervisada multifuente. Cero ejemplos alineados actuales. Eventual experimento univariado NASS/FAOSTAT requiere inventario de series homogéneas, continuidad, fechas de disponibilidad y partición por años; no sustituye un modelo agronómico climático. No entrenar ahora.

**Rotaciones:** cero secuencias de cultivo previo/siguiente con resultados observados. No son viables aprendizaje supervisado de rotaciones ni evaluación de una política. Puede diseñarse un sistema de escenarios con reglas transparentes y restricciones incompletas, sin llamarlo recomendación validada.

## Esquema de optimización futuro (solo diseño)

Unidad de decisión: parcela o zona explícita, cultivo y temporada; variable binaria de selección. Definir horizonte y granularidad con el usuario. Evaluar escenarios por compatibilidad térmica/pluviométrica y calendario, no maximizar un rendimiento supuesto.

Restricciones implementables tras revisión: un cultivo por unidad/intervalo; duración y no solapamiento cuando estén documentados; ventanas de siembra/cosecha válidas de la zona seleccionada; exclusión de registros con QA inválida; dominios de variables/unidades; rangos EcoCrop como cribado condicionado, no prohibición universal. No asignar calendarios nacionales a puntos sin identificar zona. Un rango de ciclo no se reemplaza por una media inventada: evaluar escenarios o intervalos.

Restricciones todavía sin datos: balance real de agua (riego disponible, suelo y almacenamiento), nutrientes/NPK, cultivo previo, familias y enfermedades relevantes verificadas, pendientes/terreno de la parcela, costos/precios, mano de obra, maquinaria y preferencias. No aplicar créditos de nitrógeno ni beneficios de rotación supuestos. Kc sin ETo/etapas no permite consumo hídrico; rendimiento nacional no permite ingreso parcelario.

Una primera evaluación debería devolver factible, incompatible o desconocido por criterio, con procedencia y motivo. Los pesos de objetivos y umbrales requieren decisión explícita. Casos desconocidos no deben convertirse en cero penalización. Se pospone cualquier solver hasta cerrar estas decisiones.

## Próxima etapa concreta

1. Obtener del equipo el script/configuración de exportación Sentinel y aclaraciones de calendarios, sin descargar datasets; corregir únicamente cuando se demuestre la transformación errónea.
2. Elegir un punto y cultivos identificados explícitamente. Para el punto POWER construir una tabla de 57 meses con cobertura y unidades, conservando el desfase LST/UTC y GPM como fuente independiente; no añadir NASS como etiqueta.
3. Preparar especificación de evaluación temporal para el experimento GPM (baseline estacional/persistencia), sin entrenarlo todavía. Verificar QA y contar pares completos después del filtrado.
4. Completar una ficha de restricciones y variables desconocidas para un escenario de rotación; decidir si se prioriza herramienta de cribado o adquisición futura de etiquetas parcelarias.

No se modificaron datos originales ni valores sospechosos; se añadió un registro compacto de incidencias y pruebas. No se entrenaron modelos, implementó optimizador, descargaron datos ni ejecutaron commits/push.

Pruebas de esta etapa: **45 aprobadas, 3 omitidas** por originales vacíos. El registro de incidencias se regenera con `.venv/bin/python scripts/readiness_local.py`. Las tablas procesadas existentes no requieren cambios numéricos demostrables; se reutilizan sus flags y se evita duplicarlas.
