import copy,json
from pathlib import Path
import pytest
from src.rotation_optimizer import optimize

@pytest.fixture
def data():return json.loads(Path('examples/rotations/hypothetical.input.json').read_text())

def test_optimum(data):
 r=optimize(data)
 assert len(r['feasible'])==4 and len(r['discarded'])==5
 assert r['best']['sequence']==['Glycine max','Triticum aestivum']
 assert r['best']['metrics']['min_cost']==30
 assert r==optimize(data)

@pytest.mark.parametrize('field',['calendar','climate','soil_nutrients'])
def test_gates(data,field):
 for c in data['crops'].values():c['seasons'][0][field]['allowed']=False
 assert optimize(data)['status']=='infeasible'

def test_missing_units_and_objectives(data):
 del data['crops']['Zea mays']['cycle']['provenance']
 assert optimize(data)['status']=='abstained'

def test_water_and_cycle(data):
 for s in data['seasons']:s['irrigation_budget']['value']=0
 assert optimize(data)['status']=='infeasible'
 for s in data['seasons']:s['irrigation_budget']['value']=100
 for c in data['crops'].values():c['cycle']['value']=200
 assert optimize(data)['status']=='infeasible'

def test_three_seasons_and_no_objective(data):
 data['parcel']['horizon_end']='2024-06-01'
 s=copy.deepcopy(data['seasons'][0]);s.update(start='2024-01-01',end='2024-05-31');data['seasons'].append(s)
 for c in data['crops'].values():c['seasons'].append(copy.deepcopy(c['seasons'][0]))
 data['objectives']=[]
 r=optimize(data)
 assert len(r['feasible'])==8 and r['best'] is None

def test_missing_transition(data):
 del data['transitions']['Zea mays']['Glycine max']
 assert optimize(data)['status']=='abstained'

def test_real_abstains():
 assert optimize(json.loads(Path('examples/rotations/real_incomplete.input.json').read_text()))['status']=='abstained'
