import json,sys,argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.rotation_optimizer import optimize
from src.parcel_scenarios import scenarios
p=argparse.ArgumentParser();p.add_argument('input',type=Path);a=p.parse_args()
data=json.loads(a.input.read_text())
result=optimize(data)
try: result['parcel_evidence']=scenarios(data['parcel'])
except (ValueError,KeyError,TypeError) as error: result['parcel_evidence_error']=str(error)
print(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False))
