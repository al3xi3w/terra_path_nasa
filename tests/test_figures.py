"""The figures must plot the real outputs. Export is stubbed: no browser needed to test the data."""
import json, sys
from pathlib import Path
import pandas as pd
import plotly.graph_objects as go
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import figures as F
from src.pipeline import ROOT


@pytest.fixture
def captured(monkeypatch, tmp_path):
    figs = {}
    monkeypatch.setattr(F, 'save', lambda fig, path, **kw: figs.__setitem__(Path(path).name, fig))
    F.radar(ROOT, tmp_path);F.risk_calendar(ROOT, tmp_path);F.rain_vs_demand(ROOT, tmp_path);F.trends(ROOT, tmp_path)
    return figs


def test_figures_are_built(captured):
    assert set(captured) == {'radar_rutas.png', 'calendario_riesgo.png', 'lluvia_vs_demanda.png',
                             'tendencia_lluvia.png', 'tendencia_heladas.png'}


def test_trend_statistics():
    assert F.ols_slope([2000, 2001, 2002], [1, 3, 5]) == 2.0
    s, p = F.mann_kendall(list(range(30)))
    assert s == 435 and p < 0.001  # strictly increasing series
    s, p = F.mann_kendall([5] * 10)
    assert s == 0 and p is None  # all ties: no variance, no test


def test_trends_use_only_complete_years(captured):
    rain = [t for t in captured['tendencia_lluvia.png'].data if t.name == 'Lluvia anual']
    iowa = pd.read_csv(Path(ROOT) / 'data/processed/climate_annual_iowa.csv')
    assert list(rain[3].y) == iowa[iowa.complete_year].rain_mm.tolist()
    frost_panels = [t for t in captured['tendencia_heladas.png'].data if t.type == 'bar']
    assert len(frost_panels) == 2  # only pilots with any frost get a panel


def test_radar_uses_route_scores(captured):
    routes = json.loads((Path(ROOT) / 'data/processed/routes_iowa.json').read_text())['routes']
    traces = [t for t in captured['radar_rutas.png'].data if t.subplot == 'polar4']  # iowa is the 4th pilot
    for trace in traces:
        key = {v: k for k, v in F.ROUTE_LABEL.items()}[trace.name]
        r = routes[key]
        assert list(trace.r) == [r['water'], r['soil'], r['risk'], r['water']]
        assert all(0 <= v <= 100 for v in trace.r)


def test_calendar_matches_profile_and_keeps_gaps(captured):
    frost, deficit = captured['calendario_riesgo.png'].data
    iowa = pd.read_csv(Path(ROOT) / 'data/processed/climate_profile_iowa.csv')
    assert list(frost.z[3]) == iowa.frost_days_mean.tolist()
    assert list(deficit.z[3]) == [round(e - r) for e, r in zip(iowa.et0_mean_mm, iowa.rain_mean_mm)]
    assert deficit.zmin == -deficit.zmax  # diverging scale centred on zero


def test_demand_band_only_from_crops_with_kc(captured):
    fig = captured['lluvia_vs_demanda.png']
    note = ' '.join(a.text for a in fig.layout.annotations)
    assert 'maize 1.2' in note and 'alfalfa 0.95' in note and 'clover_red' in note  # clover named as missing Kc
    rain = [t for t in fig.data if t.type == 'bar'][0]
    piura = pd.read_csv(Path(ROOT) / 'data/processed/climate_profile_piura_1.csv')
    assert list(rain.y) == piura.rain_mean_mm.tolist()
