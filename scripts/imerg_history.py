"""IMERG monthly rain 2001-2020 for the pilots, without keeping the 18 MB granules.

    python scripts/imerg_history.py [--start 2001-01 --end 2020-12] [--limit N]

Needs EARTHDATA_USERNAME / EARTHDATA_PASSWORD in the environment. For each GPM_3IMERGM v07 granule:
download to a temporary folder outside the project, validate it with src.audit.audit_gpm (the same
checks as the 57 granules already on disk), extract the nearest 0.1-degree cell for every pilot with
src.audit.extract_gpm, write a sidecar with URL, bytes and SHA-256, then delete the granule. The disk
holds one granule at a time; the provenance of every value still names the file and its hash.

Resumable: months already in the output are skipped. Writes
data/processed/imerg_history_points.parquet and data/metadata/imerg_history/<granule>.json.
After the download, `python scripts/imerg_history.py --export` writes data/processed/imerg_<pilot>.csv
joining 2001-2020 with the 2021-2025 points already extracted.
"""
import argparse, json, os, sys, tempfile, time
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.pipeline import ROOT, digest
from src.audit import audit_gpm, extract_gpm
from src.climate_profile import pilots

OUT = Path(ROOT) / 'data/processed/imerg_history_points.parquet'
META = Path(ROOT) / 'data/metadata/imerg_history'
PRODUCT, VERSION = 'GPM_3IMERGM', '07'


def points(root=ROOT):
    return [dict(location_id=f"pilot:{p['name']}", latitude=p['latitude'], longitude=p['longitude']) for p in pilots(root)]


def done_months():
    if not OUT.exists():return set()
    return set(pd.read_parquet(OUT).period_start.str[:7])


def append(rows):
    frame = pd.DataFrame(rows)
    if OUT.exists():frame = pd.concat([pd.read_parquet(OUT), frame], ignore_index=True)
    frame.drop_duplicates(['location_id', 'period_start']).sort_values(['location_id', 'period_start']).to_parquet(OUT, index=False)


def download(session, url, target):
    with session.get(url, stream=True, timeout=300) as r:
        r.raise_for_status()
        with open(target, 'wb') as f:
            for chunk in r.iter_content(1 << 20):f.write(chunk)


def run(start, end, limit=None):
    import earthaccess
    if not all(os.getenv(k) for k in ['EARTHDATA_USERNAME', 'EARTHDATA_PASSWORD']):
        raise SystemExit('Faltan EARTHDATA_USERNAME / EARTHDATA_PASSWORD en el entorno')
    if not earthaccess.login(strategy='environment').authenticated:raise SystemExit('Earthdata: autenticación fallida')
    session = earthaccess.get_requests_https_session()
    last = (pd.Period(end, 'M') + 1).start_time - pd.Timedelta(seconds=1)
    granules = earthaccess.search_data(short_name=PRODUCT, version=VERSION, temporal=(f'{start}-01', str(last)))
    META.mkdir(parents=True, exist_ok=True)
    have, pts, n = done_months(), points(), 0
    print(f'{len(granules)} gránulos encontrados; {len(have)} meses ya extraídos', flush=True)
    with tempfile.TemporaryDirectory(prefix='imerg_') as tmp:
        for g in granules:
            links = [l for l in g.data_links() if l.endswith('.HDF5')]
            if len(links) != 1:print('enlaces inesperados', g['meta']['concept-id']);continue
            url = links[0]
            month = url.split('3IMERG.')[1][:6]
            if f'{month[:4]}-{month[4:]}' in have:continue
            path = Path(tmp) / url.split('/')[-1]
            for attempt in range(3):
                try:
                    download(session, url, path);break
                except Exception as e:
                    if attempt == 2:raise
                    print('reintento', month, e, flush=True);time.sleep(5 * (attempt + 1))
            report = audit_gpm(path)
            sidecar = dict(source=dict(product=PRODUCT, version=VERSION, provider='NASA GES DISC'), url=url,
                           concept_id=g['meta']['concept-id'], downloaded=datetime.now(timezone.utc).isoformat(),
                           bytes=report['bytes'], sha256=report['sha256'], month=report.get('month'),
                           local_audit=dict(status=report['status'], errors=report['errors']),
                           storage='granule deleted after point extraction (disk space); re-download from url and verify sha256')
            rows = extract_gpm(path, pts, report)
            for r in rows:r.update(source_path=url, source_sha256=report['sha256'])
            (META / f"{g['meta']['concept-id']}.json").write_text(json.dumps(sidecar, indent=1))
            if rows:append(rows)
            path.unlink()
            n += 1
            print(f"{report.get('month')} {report['status']} ({n})", flush=True)
            if limit and n >= limit:break
    return n


def export(root=ROOT):
    """imerg_<pilot>.csv: monthly rain in mm, 2001-2020 (this script) + 2021-2025 (existing extraction)."""
    hist = pd.read_parquet(OUT) if OUT.exists() else pd.DataFrame()
    recent = pd.read_parquet(Path(root) / 'data/processed/gpm_monthly_points.parquet')
    for p in pilots(root):
        lat, lon = p['latitude'], p['longitude']
        a = hist[(hist.latitude == lat) & (hist.longitude == lon)] if len(hist) else hist
        b = recent[(recent.latitude == lat) & (recent.longitude == lon)]
        frame = pd.concat([a, b], ignore_index=True)
        frame['period_start'] = frame.period_start.astype(str).str[:10]
        frame = frame.drop_duplicates('period_start').sort_values('period_start')
        frame['rain_mm'] = (frame.precipitation * frame.duration_hours).round(2)  # mm/h x hours in the month
        cols = ['period_start', 'rain_mm', 'precipitation', 'duration_hours', 'cell_latitude', 'cell_longitude',
                'gaugeRelativeWeighting', 'quality_status', 'source_path', 'source_sha256']
        frame = frame[cols].rename(columns={'precipitation': 'precipitation_mm_per_h'})
        frame.insert(0, 'pilot', p['name'])
        frame.to_csv(Path(root) / f"data/processed/imerg_{p['name']}.csv", index=False)
        print(p['name'], len(frame), 'meses', frame.period_start.min(), '->', frame.period_start.max())


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--start', default='2001-01');ap.add_argument('--end', default='2020-12')
    ap.add_argument('--limit', type=int);ap.add_argument('--export', action='store_true')
    a = ap.parse_args()
    if a.export:export()
    else:print('descargados', run(a.start, a.end, a.limit))
