"""Weight sensitivity of the 3 routes: does the recommendation move when water weighs more?

The scoring layer has no weights of its own: src/rotation_scores.pick_routes takes the best route
on each axis and breaks ties with an equal-weight sum. A 40 % water weight is therefore not in the
code; here it is an explicit parameter, and the 60 % left is split equally between soil and risk
(an assumption, reported in the output). Two selections are tested:

- per_axis: the existing selection (best on each axis), with the weighted sum as tie-break.
- weighted_top3: the three distinct crop sets with the highest weighted total, the selection a
  single-number weighting would actually produce.

Stable routes only mean a robust recommendation when the axes discriminate. If soil is saturated
at 100 and risk is identical across rotations, every weighting ranks by water alone and the
routes cannot change; `axis_spread` reports this so stability is not over-read.
"""
from .pipeline import ROOT
from .climate_profile import pilots
from .rotation_scores import score_point, pick_routes, weighted_total, AXES

BASE = {'water': 0.40, 'soil': 0.30, 'risk': 0.30}
ALTERNATIVE = {'water': 0.50, 'soil': 0.25, 'risk': 0.25}
SWEEP = [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
ASSUMPTION = 'el peso restante (1 - agua) se reparte por igual entre suelo y riesgo; el código no define pesos'


def split(water):
    rest = round((1 - water) / 2, 4)
    return {'water': water, 'soil': rest, 'risk': rest}


def weighted_top3(rows, weights):
    """The three distinct crop sets with the highest weighted total (ties: by sequence name)."""
    out, seen = [], set()
    for row in sorted(rows, key=lambda r: (-weighted_total(r, weights), r['sequence'])):
        key = frozenset(row['sequence'])
        if key in seen:continue
        seen.add(key);out.append(dict(sequence=row['sequence'], total=round(weighted_total(row, weights), 2)))
        if len(out) == 3:break
    return out


def route_sets(routes):
    return {k: (None if v is None else sorted(v['sequence'])) for k, v in routes.items()}


def axis_spread(rows):
    """Range of each axis over all rotations: zero means that axis cannot change any ranking."""
    return {k: dict(min=min(r[k] for r in rows), max=max(r[k] for r in rows), distinct=len({r[k] for r in rows})) for k in AXES}


def sensitivity_point(latitude, longitude, label=None, root=ROOT):
    scored = score_point(latitude, longitude, label, root, keep_rows=True)
    if scored['status'] != 'scored':return dict(status=scored['status'], label=label, reason=scored.get('reason'))
    rows, front = scored['rows'], scored['front']
    per_axis = {name: route_sets(pick_routes(front, rows, w)) for name, w in [('base', BASE), ('alternative', ALTERNATIVE)]}
    top = {name: weighted_top3(rows, w) for name, w in [('base', BASE), ('alternative', ALTERNATIVE)]}
    sets = lambda t: [sorted(r['sequence']) for r in t]
    sweep = {w: sets(weighted_top3(rows, split(w))) for w in SWEEP}
    return dict(status='tested', label=label, weights=dict(base=BASE, alternative=ALTERNATIVE, assumption=ASSUMPTION),
                rotations=len(rows), axis_spread=axis_spread(rows),
                per_axis=dict(**per_axis, changed=[k for k in per_axis['base'] if per_axis['base'][k] != per_axis['alternative'][k]]),
                weighted_top3=dict(**top, same_sets=sets(top['base']) == sets(top['alternative']),
                                   same_order=[r['sequence'] for r in top['base']] == [r['sequence'] for r in top['alternative']]),
                sweep_top3=sweep, sweep_changes=[w for a, w in zip(SWEEP, SWEEP[1:]) if sweep[a] != sweep[w]],
                source=dict(routes='src/rotation_scores.score_point (mismos datos que routes_<piloto>.json)',
                            power_file=scored['point']['file'], sha256=scored['point']['sha256']))


def sensitivity_pilots(root=ROOT):
    return {p['name']: sensitivity_point(p['latitude'], p['longitude'], p.get('label'), root) for p in pilots(root)}
