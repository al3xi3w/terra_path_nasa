"""IMERG monthly rain per pilot (scripts/imerg_history.py): complete, traceable, never filled in."""
import json
from pathlib import Path
import pandas as pd
import pytest
from src.pipeline import ROOT

PILOTS = ['piura_1', 'piura_2', 'piura_3', 'iowa', 'kenia', 'california']
META = Path(ROOT) / 'data/metadata/imerg_history'


def series(name):
    path = Path(ROOT) / f'data/processed/imerg_{name}.csv'
    if not path.exists():pytest.skip(f'{path.name} no exportado')
    return pd.read_csv(path)


@pytest.mark.parametrize('name', PILOTS)
def test_months_are_contiguous_and_unique(name):
    d = series(name)
    months = pd.to_datetime(d.period_start)
    assert months.is_unique and months.is_monotonic_increasing
    assert months.min() == pd.Timestamp('2001-01-01')
    expected = pd.date_range(months.min(), months.max(), freq='MS')
    assert len(months) == len(expected)  # no hole silently skipped


@pytest.mark.parametrize('name', PILOTS)
def test_rain_is_rate_times_hours_and_never_invented(name):
    d = series(name)
    assert d.rain_mm.notna().all() and (d.rain_mm >= 0).all()
    assert ((d.precipitation_mm_per_h * d.duration_hours).round(2) - d.rain_mm).abs().max() < 0.011
    days = pd.to_datetime(d.period_start).dt.days_in_month
    assert (d.duration_hours == days * 24).all()


@pytest.mark.parametrize('name', PILOTS)
def test_every_value_names_its_file_and_hash(name):
    d = series(name)
    downloaded = d.source_path.str.contains('/GPM_3IMERGM.07/')            # 2001-2020, granule deleted
    local = d.source_path.str.startswith('data/raw/gpm_monthly/')          # 2021-2025, granule on disk
    assert (downloaded | local).all()
    assert (pd.to_datetime(d.period_start[downloaded]).dt.year <= 2020).all()
    assert d.source_sha256.str.fullmatch(r'[0-9a-f]{64}').all()
    assert d.cell_latitude.nunique() == 1 and d.cell_longitude.nunique() == 1  # one fixed 0.1° cell


def test_deleted_granules_keep_a_sidecar():
    if not META.exists():pytest.skip('historial IMERG no descargado')
    sidecars = [json.loads(p.read_text()) for p in META.glob('*.json')]
    assert len(sidecars) == 240  # 2001-01 .. 2020-12
    assert {s['month'] for s in sidecars} == {m.strftime('%Y-%m') for m in pd.date_range('2001-01', '2020-12', freq='MS')}
    for s in sidecars:
        assert s['local_audit']['status'] == 'validated' and len(s['sha256']) == 64
        assert s['url'].startswith('https://data.gesdisc.earthdata.nasa.gov/')
    hist = series('iowa')
    by_month = dict(zip(hist.period_start.str[:7], hist.source_sha256))
    assert all(by_month[s['month']] == s['sha256'] for s in sidecars)
