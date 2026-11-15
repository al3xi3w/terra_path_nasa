"""Monthly climate profile and annual series for each pilot point (or any coordinate).

    python scripts/climate_profiles.py
    python scripts/climate_profiles.py --point lima:-12.05:-77.04

Writes data/processed/climate_profile_<name>.csv and climate_annual_<name>.csv, plus a combined
Parquet with provenance. Nothing is estimated: a point without a local POWER series is reported,
not filled in.
"""
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
from src.climate_profile import pilots, monthly_profile, annual_series
from src.audit import write_table
from src.pipeline import ROOT


def run(points, root=ROOT, frost_threshold=0.0):
    output = Path(root) / 'data/processed'
    frames, provenance = [], {}
    for point in points:
        name, lat, lon = point['name'], point['latitude'], point['longitude']
        profile, meta = monthly_profile(lat, lon, root, frost_threshold=frost_threshold)
        if profile is None:
            print(f"SIN DATOS {name}: {meta['reason']}");provenance[name] = meta;continue
        profile.insert(0, 'pilot', name);profile.insert(1, 'label', point.get('label', name))
        profile.insert(2, 'latitude', lat);profile.insert(3, 'longitude', lon)
        profile.to_csv(output / f'climate_profile_{name}.csv', index=False)
        annual, _ = annual_series(lat, lon, root, frost_threshold)
        annual.insert(0, 'pilot', name)
        annual.to_csv(output / f'climate_annual_{name}.csv', index=False)
        frames.append(profile);provenance[name] = meta
        frost = profile.frost_days_mean.sum() if 'frost_days_mean' in profile else 0
        print(f"{name:<11} {meta['period'][0]}..{meta['period'][1]}  elev {meta['elevation_m']} m  "
              f"lluvia {profile.rain_mean_mm.sum():.0f} mm/año  heladas {frost:.1f} días/año  "
              f"años ET0 {int(profile.years_et0.min())}-{int(profile.years_et0.max())}")
    if frames:
        combined = pd.concat(frames, ignore_index=True)
        write_table(combined, output / 'climate_profiles.parquet',
                    {'source': 'NASA POWER daily point exports', 'provenance': provenance,
                     'frost_threshold_c': frost_threshold,
                     'completeness': 'a calendar month counts only when every day is present and the variable has no gap',
                     'et0': 'FAO-56 Penman-Monteith computed locally; solar radiation starts in 1984 so years_et0 can be lower',
                     'support': 'POWER point export, not a station; MERRA-2 ~0.5x0.625 degrees smooths terrain'})
    return provenance


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--point', action='append', default=[], metavar='nombre:lat:lon')
    parser.add_argument('--only-given', action='store_true')
    parser.add_argument('--frost', type=float, default=0.0, help='umbral de helada en °C (por defecto 0)')
    args = parser.parse_args()
    extra = []
    for item in args.point:
        name, lat, lon = item.split(':');extra.append(dict(name=name, label=name, latitude=float(lat), longitude=float(lon)))
    points = extra if args.only_given else pilots() + extra
    run(points, frost_threshold=args.frost)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
