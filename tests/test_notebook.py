"""notebooks/terrapath_recorrido.ipynb: imports the engine from src/ (no copied code) and was saved without errors."""
import json
from pathlib import Path
import pytest
from src.pipeline import ROOT

NB = Path(ROOT) / 'notebooks/terrapath_recorrido.ipynb'


def test_notebook_saved_without_errors_and_uses_src():
    if not NB.exists():pytest.skip('notebook no generado')
    nb = json.loads(NB.read_text())
    code = [c for c in nb['cells'] if c['cell_type'] == 'code']
    assert code and all(c.get('execution_count') for c in code)  # ejecutado entero
    assert not [o for c in code for o in c.get('outputs', []) if o.get('output_type') == 'error']
    src = '\n'.join(''.join(c['source']) for c in code)
    assert 'from src.rotation_scores import score_point' in src and 'def score_point' not in src
