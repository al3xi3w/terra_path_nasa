# Sensibilidad de pesos: agua 40 % → 50 %

Generado por `scripts/sensitivity.py` con `src/sensitivity.py`. Detalle en `data/processed/sensitivity_weights.json`.

## Antes de leer los números

- **El código no tiene pesos.** `pick_routes` toma la mejor ruta en cada eje y desempata con la suma *igual* de los tres ejes. El 40 % de agua se introduce aquí como parámetro explícito. Supuesto: el peso restante (1 - agua) se reparte por igual entre suelo y riesgo; el código no define pesos. Base 40/30/30, alternativa 50/25/25 (agua/suelo/riesgo).
- Se prueban dos selecciones: **por eje** (la actual, con el peso solo como desempate) y **top-3 ponderado** (los tres conjuntos de cultivos con mayor suma ponderada).
- Además se barre el peso del agua en 20 %, 30 %, 40 %, 50 %, 60 %, 70 %, 80 %.

## Resultado por piloto

| Piloto | Rutas por eje cambian | Top-3 ponderado cambia | Cambios en el barrido 20-80 % | Valores distintos: agua / suelo / riesgo |
|---|---|---|---|---|
| Huancabamba, Piura (PE) | no | no | ninguno | 1 (98.1-98.1) / 1 (100-100) / 1 (53.9) |
| Piura sur (PE) | no | no | ninguno | 1 (64-64) / 1 (100-100) / 1 (52.6) |
| piura_3 | no_valid_rotation | | | |
| Iowa central (US) | no | no | ninguno | 1 (78.9-78.9) / 1 (100-100) / 1 (76.1) |
| Nakuru (KE) | no | no | ninguno | 1 (59.2-59.2) / 1 (100-100) / 1 (55.6) |
| california | no_known_water | | | |

## Top-3 ponderado con agua al 40 % y al 50 %

**Huancabamba, Piura (PE)** (12 rotaciones)
- alfalfa → barley → potato: 85.41 → 87.52
- alfalfa → potato → wheat: 85.41 → 87.52

**Piura sur (PE)** (12 rotaciones)
- alfalfa → barley → potato: 71.38 → 70.15
- alfalfa → potato → wheat: 71.38 → 70.15

**Iowa central (US)** (12 rotaciones)
- alfalfa → barley → potato: 84.39 → 83.47
- alfalfa → potato → wheat: 84.39 → 83.47

**Nakuru (KE)** (12 rotaciones)
- alfalfa → barley → potato: 70.36 → 68.5
- alfalfa → potato → wheat: 70.36 → 68.5

## Lectura

- **Las tres rutas no cambian en ningún piloto**, ni de 40 % a 50 % ni en todo el barrido de 20 % a 80 %.
- **Eso no prueba que la recomendación sea confiable.** El riesgo tiene un solo valor por piloto (todos los cultivos elegibles comparten temperatura letal de 0 °C y la misma ventana) y el suelo tiene uno o dos valores (se satura en 100 con tres criterios). Con dos ejes casi constantes, cualquier peso ordena solo por agua: las rutas no *pueden* cambiar. La estabilidad es estructural, no evidencia de robustez.
- El agua solo se puntúa con Kc FAO-56; trigo, cebada y papa comparten Kc 1,15, así que muchas rotaciones empatan también en agua.
- Piura 3 y California no tienen rutas con agua conocida (solo dos cultivos elegibles con Kc), así que no hay nada que probar ahí.
- Los tres primeros conjuntos empatan exactamente en los pilotos con rutas; el orden entre ellos lo decide el desempate por nombre, que no tiene significado agronómico.
- Para que esta prueba diga algo hace falta que suelo y riesgo varíen: temperatura letal para maíz, soja, haba, sorgo, lenteja y arroz; más criterios de suelo documentados; reglas de rotación con fuente.
