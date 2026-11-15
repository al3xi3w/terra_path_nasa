import sys,argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.pipeline import Pipeline
p=argparse.ArgumentParser(); p.add_argument('operation',nargs='?',default='all',choices=['all','download','process','validate','power','earth','extend','verify-earth','satellite','batch','batch-power','batch-appeears','batch-monthly','audit']); p.add_argument('--lat',type=float); p.add_argument('--lon',type=float); p.add_argument('--start',default='2021-01-01'); p.add_argument('--end',default='2025-12-31'); p.add_argument('--variables',nargs='+'); p.add_argument('--source',choices=['gpm','smap','modis','srtm']); p.add_argument('--bbox',nargs=4,type=float); p.add_argument('--limit',type=int,default=1); p.add_argument('--download-granules',action='store_true'); p.add_argument('--file'); p.add_argument('--max-cells',type=int,default=2000000); a=p.parse_args(); run=Pipeline()
if a.operation=='audit':
    from src.audit import run_audit
    run_audit()
    sys.exit(0)
if a.operation.startswith('batch'):
    from src.batch import run_batch
    run_batch(a.operation)
    sys.exit(0)
if a.operation in ['all','download']: run.globals()
if a.operation=='satellite':
    if not a.file or not a.source: p.error('--file and --source required')
    run.satellite(a.source,a.file,a.max_cells)
if a.operation=='extend': run.extend(); run.process()
if a.operation=='verify-earth': run.verify_earth()
if a.operation=='power':
    if a.lat is None or a.lon is None: p.error('--lat and --lon required')
    run.power(a.lat,a.lon,a.start,a.end,a.variables or run.settings['power_variables'])
if a.operation=='earth':
    if not a.source or not a.bbox: p.error('--source and --bbox required')
    run.earth(a.source,a.bbox,a.start,a.end,a.limit,a.download_granules)
if a.operation in ['all','process','validate','power']: run.process()
run.reports()
