"""Water-weight sensitivity of the 3 routes (40 % -> 50 %) and a 20-80 % sweep.

    python scripts/sensitivity.py

Writes data/processed/sensitivity_weights.json and reports/sensibilidad_pesos.md.
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.sensitivity import sensitivity_pilots, BASE, ALTERNATIVE, SWEEP, ASSUMPTION
from src.pipeline import ROOT

pct = lambda w: '/'.join(f'{round(w[k] * 100):g}' for k in ('water', 'soil', 'risk'))


def main(root=ROOT):
    results = sensitivity_pilots(root)
    (Path(root) / 'data/processed/sensitivity_weights.json').write_text(json.dumps(results, indent=1, ensure_ascii=False, default=str))
    lines = ['# Sensibilidad de pesos: agua 40 % → 50 %', '',
             'Generado por `scripts/sensitivity.py` con `src/sensitivity.py`. Detalle en `data/processed/sensitivity_weights.json`.', '',
             '## Antes de leer los números', '',
             f'- **El código no tiene pesos.** `pick_routes` toma la mejor ruta en cada eje y desempata con la suma *igual* de los tres ejes. '
             f'El 40 % de agua se introduce aquí como parámetro explícito. Supuesto: {ASSUMPTION}. Base {pct(BASE)}, alternativa {pct(ALTERNATIVE)} (agua/suelo/riesgo).',
             '- Se prueban dos selecciones: **por eje** (la actual, con el peso solo como desempate) y **top-3 ponderado** (los tres conjuntos de cultivos con mayor suma ponderada).',
             f'- Además se barre el peso del agua en {", ".join(f"{round(w * 100)} %" for w in SWEEP)}.', '',
             '## Resultado por piloto', '',
             '| Piloto | Rutas por eje cambian | Top-3 ponderado cambia | Cambios en el barrido 20-80 % | Valores distintos: agua / suelo / riesgo |',
             '|---|---|---|---|---|']
    for name, r in results.items():
        if r['status'] != 'tested':
            lines.append(f"| {name} | {r['status']} | | | |");continue
        s = r['axis_spread']
        lines.append(f"| {r['label']} | {'sí: ' + ', '.join(r['per_axis']['changed']) if r['per_axis']['changed'] else 'no'} | "
                     f"{'no' if r['weighted_top3']['same_order'] else ('mismo conjunto, otro orden' if r['weighted_top3']['same_sets'] else 'sí')} | "
                     f"{', '.join(f'{round(w * 100)} %' for w in r['sweep_changes']) or 'ninguno'} | "
                     f"{s['water']['distinct']} ({s['water']['min']:g}-{s['water']['max']:g}) / {s['soil']['distinct']} ({s['soil']['min']:g}-{s['soil']['max']:g}) / "
                     f"{s['risk']['distinct']} ({s['risk']['min']:g}) |")
    lines += ['', '## Top-3 ponderado con agua al 40 % y al 50 %', '']
    for name, r in results.items():
        if r['status'] != 'tested':continue
        lines.append(f"**{r['label']}** ({r['rotations']} rotaciones)")
        for (a, b) in zip(r['weighted_top3']['base'], r['weighted_top3']['alternative']):
            lines.append(f"- {' → '.join(a['sequence'])}: {a['total']} → {b['total']}")
        lines.append('')
    lines += ['## Lectura', '',
              '- **Las tres rutas no cambian en ningún piloto**, ni de 40 % a 50 % ni en todo el barrido de 20 % a 80 %.',
              '- **Eso no prueba que la recomendación sea confiable.** El riesgo tiene un solo valor por piloto (todos los cultivos elegibles comparten temperatura letal de 0 °C y la misma ventana) '
              'y el suelo tiene uno o dos valores (se satura en 100 con tres criterios). Con dos ejes casi constantes, cualquier peso ordena solo por agua: las rutas no *pueden* cambiar. '
              'La estabilidad es estructural, no evidencia de robustez.',
              '- El agua solo se puntúa con Kc FAO-56; trigo, cebada y papa comparten Kc 1,15, así que muchas rotaciones empatan también en agua.',
              '- Piura 3 y California no tienen rutas con agua conocida (solo dos cultivos elegibles con Kc), así que no hay nada que probar ahí.',
              '- Los tres primeros conjuntos empatan exactamente en los pilotos con rutas; el orden entre ellos lo decide el desempate por nombre, que no tiene significado agronómico.',
              '- Para que esta prueba diga algo hace falta que suelo y riesgo varíen: temperatura letal para maíz, soja, haba, sorgo, lenteja y arroz; más criterios de suelo documentados; reglas de rotación con fuente.', '']
    (Path(root) / 'reports/sensibilidad_pesos.md').write_text('\n'.join(lines))
    for name, r in results.items():
        print(name, r['status'], 'cambios:', r.get('per_axis', {}).get('changed'), r.get('sweep_changes'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
