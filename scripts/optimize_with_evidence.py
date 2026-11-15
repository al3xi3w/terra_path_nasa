"""Evidence-based rotation evaluation: NASA/FAO constraints + farmer declarations → optimizer or abstention."""
import json, sys, argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.constraints import optimize_with_evidence

p = argparse.ArgumentParser(); p.add_argument('input', type=Path); a = p.parse_args()
print(json.dumps(optimize_with_evidence(json.loads(a.input.read_text())), indent=2, ensure_ascii=False, allow_nan=False, default=str))
