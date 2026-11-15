"""Backtest the 3 routes per pilot: calibrate 1981-2015, test 2016-2024.

    python scripts/backtest.py

Writes data/processed/backtest_<pilot>.json (year by year, with provenance) and
reports/backtesting.md (totals per route and per monoculture, verdicts, limitations).
"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.backtesting import backtest_pilots, total, METRICS
from src.pipeline import ROOT

STATES = {'eligible': 'elegible', 'unknown': 'desconocido', 'excluded': 'excluido'}
LABELS = {'frost_days': 'días de helada', 'deficit_mm': 'déficit (mm)', 'rain_below_opt': 'años lluvia < óptimo'}


def fmt(t):
    """Total over the test years, or the known part marked as partial; never a silent zero."""
    if t['total'] is not None:return f"{t['total']:g}"
    return f"desconocido ({t['known_years']}/{t['years']} años)"


def pilot_section(name, r):
    lines = [f"## {name} — {r.get('label')}", '']
    if r['status'] != 'tested':
        return lines + [f"Sin backtesting: {r['status']} ({r.get('reason')}).", '']
    lines += [f"Ventana calibrada: {r['window']} · elegibles en 1981-2015: {', '.join(r['eligible_in_calibration'])}",
              f"Rutas calibradas iguales a las del período completo: "
              f"{', '.join(f'{k} {v}' for k, v in r['calibrated_routes_match_full_period'].items())}",
              f"POWER: `{r['provenance']['power']['file']}` (SHA-256 `{r['provenance']['power']['sha256'][:12]}…`)", '',
              '| Ruta (1981-2015) | Secuencia | ' + ' | '.join(LABELS.values()) + ' |', '|---|---|---|---|---|']
    for route_name, route in r['routes'].items():
        if route is None:continue
        mark = '' if route['from_pareto_front'] else ' (dominada)'
        lines.append(f"| {route_name}{mark} | {' → '.join(route['sequence'])} | "
                     + ' | '.join(fmt(total(route['years'], m)) for m in METRICS) + ' |')
    lines += ['', '| Monocultivo 2016-2024 | estado en calibración | ' + ' | '.join(LABELS.values()) + ' |', '|---|---|---|---|---|']
    for crop, years in r['monocultures'].items():
        lines.append(f"| {crop} | {STATES[r['eligibility_in_calibration'][crop]]} | " + ' | '.join(fmt(total(years, m)) for m in METRICS) + ' |')
    lines += ['', 'Veredicto contra los 15 monocultivos (cuántos monocultivos supera, iguala, pierde o no se puede decidir):', '',
              '| Ruta | Métrica | menos | igual | más | desconocido |', '|---|---|---|---|---|---|']
    for route_name, by_crop in r['comparisons'].items():
        for m in METRICS:
            verdicts = [by_crop[c][m]['verdict'] for c in by_crop]
            lines.append(f"| {route_name} | {LABELS[m]} | " + ' | '.join(str(verdicts.count(v)) for v in ('menos', 'igual', 'más', 'desconocido')) + ' |')
    typical = r['typical_monoculture']
    if typical['crop']:
        lines += ['', f"**Monocultivo típico declarado: {typical['crop']}**", '']
        for route_name, by_crop in r['comparisons'].items():
            c = by_crop[typical['crop']]
            lines.append(f"- {route_name}: " + '; '.join(
                f"{LABELS[m]} {c[m]['verdict']}" + (f" (pareado {c[m]['paired']['years']} años: {c[m]['paired']['route']} vs {c[m]['paired']['monoculture']})"
                                                    if c[m]['verdict'] == 'desconocido' and c[m]['paired'] else '') for m in METRICS))
    else:
        lines += ['', f"Monocultivo típico: **no declarado** ({typical['status']}). Se reporta contra todos."]
    return lines + ['']


def cell(c):
    """Full-period verdict; if unknown, the paired-year comparison, labelled as such."""
    full = f"{c['route']['total']:g} vs {c['monoculture']['total']:g} → **{c['verdict']}**" if c['verdict'] != 'desconocido' else 'desconocido'
    if c['verdict'] == 'desconocido' and c['paired']:
        p = c['paired']
        full += f" (pareado {p['years']} años: {p['route']:g} vs {p['monoculture']:g} → {p['verdict']})"
    return full


def summary(results):
    first = next(r for r in results.values() if r['status'] == 'tested')
    src = first['typical_monoculture']['source'] or {}
    lines = ['## Resumen: rutas contra el monocultivo típico declarado', '',
             f"Monocultivo típico: el cultivo con mayor superficie cosechada media 1981-2015 en el país "
             f"({src.get('dataset')}, `{src.get('file')}`, elemento {src.get('element')}, SHA-256 `{(src.get('sha256') or '')[:12]}…`). "
             'Es **nacional**: no prueba que domine en el punto (en el Valle Central de California es dudoso).', '',
             '"menos" = la ruta tuvo menos que el monocultivo (mejor). Totales 2016-2024.', '',
             '| Piloto | Típico | Ruta | Días de helada | Déficit (mm) | Años lluvia < óptimo |', '|---|---|---|---|---|---|']
    for name, r in results.items():
        t = r.get('typical_monoculture', {})
        if r['status'] != 'tested' or not t.get('crop'):continue
        ev = t['evidence']
        for route_name, by_crop in r['comparisons'].items():
            c = by_crop[t['crop']]
            lines.append(f"| {r['label']} | {t['crop']} ({ev['mean_area_ha']:,} ha en {ev['country']}) | {route_name} | "
                         + ' | '.join(cell(c[m]) for m in METRICS) + ' |')
    return lines + ['']


def main(root=ROOT):
    results = backtest_pilots(root)
    out = Path(root) / 'data/processed'
    for name, r in results.items():
        (out / f'backtest_{name}.json').write_text(json.dumps(r, indent=1, ensure_ascii=False, default=str))
    lines = ['# Backtesting de rutas: calibración 1981-2015, prueba 2016-2024', '',
             'Generado por `scripts/backtest.py` con `src/backtesting.py`. Detalle año por año en `data/processed/backtest_<piloto>.json`.', '',
             '**Pregunta:** ¿la ruta calibrada con el pasado tuvo menos días de helada y menos déficit de agua que un monocultivo en 2016-2024?', '',
             '## Método', '',
             '- Las rutas, la ventana y los cultivos elegibles se recalculan solo con 1981-2015 (ET0 1984-2015: la radiación de POWER empieza en 1984).',
             '- La ruta se siembra tal cual, una campaña por año desde el mes de inicio calibrado, cada cultivo durante su propio ciclo mínimo. 2016-2024 son 9 años = 3 ciclos completos: cada cultivo cuenta 3 veces.',
             '- El monocultivo es el mismo cultivo cada año en la misma ventana. **No hay fuente local del monocultivo típico** (FAOSTAT local solo trae rendimiento; NASS local solo trigo de Fresno), así que se compara contra los 15 cultivos y el típico queda en `config/backtesting_baseline.json`.',
             '- Días de helada: días de la ventana con T2M_MIN bajo la temperatura letal EcoCrop **de cada cultivo**.',
             '- Déficit: max(0, Kc_mid × ET0 − lluvia) en la ventana. Solo existe para los cultivos con Kc FAO-56 verificado (maíz, soja, cebada, avena, lenteja, trigo, papa, alfalfa).',
             '- Años con lluvia < óptimo: lluvia anual de `climate_annual_<piloto>.csv` bajo el mínimo óptimo EcoCrop; es el criterio que el puntaje de agua usa sin Kc.',
             '- El estado en calibración dice si ese monocultivo era elegible en la ventana. Comparar contra uno **excluido** (p. ej. arroz o yuca) no es una comparación justa: se muestra solo para que nada quede oculto.',
             '- Un total existe solo si todos los años se conocen. Si no, se escribe "desconocido (k/9 años)". **Nunca se suma un faltante como cero.**', '']
    lines += summary(results)
    for name, r in results.items():
        lines += pilot_section(name, r)
    lines += ['## Lectura y limitaciones', '',
              '- **Ruta y monocultivo enfrentan el mismo clima cada año.** La diferencia sale solo de los umbrales de cada cultivo: el mínimo óptimo de lluvia de EcoCrop (maíz 600 mm; trébol 700, trigo 750, papa y cebada 500) y el Kc_medio (alfalfa 0,95, cebada/trigo/papa 1,15 frente a maíz 1,20). El déficit "menos" contra maíz es exactamente esa diferencia de Kc.',
              '- Contra maíz la helada es siempre desconocida: EcoCrop no trae temperatura letal válida para maíz.',
              '- **Déficit de agua: las rutas usan Kc FAO-56 verificado** (alfalfa 0,95; cebada, trigo y papa 1,15; maíz 1,20). Desde 2026-11-14 el motor solo puntúa agua con Kc: girasol y trébol no tienen Kc y sus rotaciones quedan fuera de las rutas. Por eso Piura 3 y California pueden quedar sin rutas.',
              '- El "menos déficit" de las rutas frente al maíz viene sobre todo de la alfalfa (Kc 0,95). Kc_medio × ET0 de toda la ventana es una cifra de tamizaje que sobreestima la demanda fuera de mitad de ciclo; no es la ETc por etapas.',
              '- **Helada: el backtest no discrimina.** Todos los cultivos elegibles tienen la misma temperatura letal en EcoCrop (0 °C), así que ruta y monocultivo de un cultivo elegible cuentan los mismos días. Maíz, soja, haba, sorgo, lenteja y arroz no tienen temperatura letal: contra ellos la helada es desconocida.',
              '- **En las ventanas calibradas no hubo ningún día bajo la temperatura letal en 2016-2024, en ningún piloto.** El "0" de helada es real en POWER, pero no distingue rutas de monocultivos.',
              '- **Huancabamba (piura_1): 0 heladas en 44 años según POWER.** MERRA-2 tiene celdas de ~50 km y suaviza la montaña; esto no prueba que no hiele.',
              '- El puntaje de suelo se satura en 100 (tres criterios documentados), por eso no entra en el backtest.',
              '- Cada campaña empieza en el mes calibrado y dura el ciclo mínimo de EcoCrop, no el calendario real; el calendario FAO no cubre EE. UU.',
              '- Las rutas con barbecho no se prueban aquí: tienen un año sin cultivo cada tres y su total no es comparable con un monocultivo de nueve campañas.',
              '- No hay dataset local de reglas de rotación ni pendiente SRTM fuera de California.', '']
    (Path(root) / 'reports/backtesting.md').write_text('\n'.join(lines))
    for name, r in results.items():
        print(name, r['status'], r.get('window'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
