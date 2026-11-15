"""Score 3-campaign rotations for each pilot (or any coordinate) and export the 3 routes.

    python scripts/rotation_routes.py
    python scripts/rotation_routes.py --point lima:-12.05:-77.04

Writes data/processed/routes_<name>.json with the routes, the Pareto front, the per-crop scores
and the eligibility table. Screening only: see the simplifications inside each file.
"""
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.climate_profile import pilots
from src.rotation_scores import score_point
from src.pipeline import ROOT


def show(routes, tag):
    for name, route in (routes or {}).items():
        if route is None:print(f"   {name:<12} sin ruta: no hay otro conjunto de cultivos válido{tag}");continue
        mark = '' if route['from_pareto_front'] else '  (dominada)'
        print(f"   {name:<12} {' -> '.join(route['sequence']):<42} "
              f"agua {route['water']:>5}  suelo {route['soil']:>5}  riesgo {route['risk']:>5}{mark}{tag}")


def run(points, root=ROOT):
    output = Path(root) / 'data/processed'
    for point in points:
        result = score_point(point['latitude'], point['longitude'], point.get('label'), root)
        (output / f"routes_{point['name']}.json").write_text(
            json.dumps(result, indent=1, ensure_ascii=False, default=str))
        if result['status'] != 'scored':
            print(f"{point['name']:<11} {result['status']}: {result.get('reason')}")
        else:
            print(f"{point['name']:<11} ventana {result['window']}  {result['rotations']} rotaciones  "
                  f"frente de Pareto {result['pareto']}")
        show(result.get('routes'), '')
        show(result.get('routes_with_fallow'), ' [barbecho]')
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--point', action='append', default=[], metavar='nombre:lat:lon')
    parser.add_argument('--only-given', action='store_true')
    args = parser.parse_args()
    extra = [dict(zip(('name', 'latitude', 'longitude'), (n, float(a), float(b))), label=n)
             for n, a, b in (item.split(':') for item in args.point)]
    return run(extra if args.only_given else pilots() + extra)


if __name__ == '__main__':
    raise SystemExit(main())
