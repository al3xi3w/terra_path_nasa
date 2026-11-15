"""Download NASA POWER daily point series for any set of coordinates (global by design).

Reuses Pipeline.fetch (raw bytes + SHA-256 sidecar) and Pipeline.local_environment
(validated Parquet + lineage manifest), so new points get the same provenance as the
existing California series. Nothing already on disk is overwritten.

    python scripts/download_power_points.py                        # registered pilot points
    python scripts/download_power_points.py --point lima:-12.05:-77.04
    python scripts/download_power_points.py --start 1981-01-01 --end 2024-12-31

Any latitude/longitude works: the engine is not tied to a region. The default list is the
pilot set already registered in data/integrated/locations.parquet, so POWER lines up with
the GPM rainfall and Sentinel-2 NDVI already extracted for those exact points.
"""
import argparse, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.pipeline import Pipeline, ROOT, read_power_csv
from src.climate_profile import pilots

PILOTS = [(p['name'], p['latitude'], p['longitude']) for p in pilots()]


def power_filename(lat, lon, start, end):
    """NASA's own export naming, so files are recognisable next to the existing series."""
    ns = f"{abs(lat):06.2f}".replace('.', 'd') + ('N' if lat >= 0 else 'S')
    ew = f"{abs(lon):07.2f}".replace('.', 'd') + ('E' if lon >= 0 else 'W')
    return f"POWER_Point_Daily_{start.replace('-', '')}_{end.replace('-', '')}_{ns}_{ew}_LST.csv"


def download(points, start, end, root=ROOT):
    pipeline = Pipeline(root)
    variables = pipeline.settings['power_variables']
    results = []
    for name, lat, lon in points:
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):raise ValueError(f'Invalid coordinates for {name}')
        filename = power_filename(lat, lon, start, end)
        params = dict(latitude=lat, longitude=lon, start=start.replace('-', ''), end=end.replace('-', ''),
                      parameters=','.join(variables), community='AG', format='CSV')
        params['time-standard'] = 'LST'
        try:
            path = pipeline.fetch('power', filename, 'https://power.larc.nasa.gov/api/temporal/daily/point', params)
            output = pipeline.local_environment('power', path)
            _, quality = read_power_csv(path)
            results.append(dict(point=name, latitude=lat, longitude=lon, raw=str(path.relative_to(Path(root))),
                                processed=str(output.relative_to(Path(root))), rows=quality['rows'],
                                missing_percent={k: round(v, 2) for k, v in quality['missing_percent'].items() if v},
                                missing_days=quality['missing_days'], period=quality['period']))
            print(f"OK  {name:<11} {lat:>7.2f} {lon:>8.2f}  {quality['rows']} días  -> {output.name}")
            for variable, percent in quality['missing_percent'].items():
                if percent:print(f"    faltante {variable}: {percent:.1f}% (POWER devuelve -999; no se rellena)")
        except Exception as error:
            results.append(dict(point=name, latitude=lat, longitude=lon, error=str(error)))
            print(f"ERROR {name}: {error}")
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--point', action='append', default=[], metavar='nombre:lat:lon',
                        help='punto adicional o único; repetible')
    parser.add_argument('--start', default='1981-01-01')
    parser.add_argument('--end', default='2024-12-31')
    parser.add_argument('--only-given', action='store_true', help='usar solo los --point, sin los pilotos por defecto')
    args = parser.parse_args()
    extra = []
    for item in args.point:
        try:
            name, lat, lon = item.split(':');extra.append((name, float(lat), float(lon)))
        except ValueError:parser.error(f'Formato esperado nombre:lat:lon, recibido {item!r}')
    points = extra if args.only_given else PILOTS + extra
    if not points:parser.error('Sin puntos que descargar')
    print(f'{len(points)} puntos, {args.start} a {args.end}\n')
    results = download(points, args.start, args.end)
    failed = [r for r in results if 'error' in r]
    print(f"\n{len(results) - len(failed)} descargados, {len(failed)} con error")
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
