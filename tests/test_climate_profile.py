from pathlib import Path
import pandas as pd
import pytest
from src import climate_profile as C
from src.pipeline import digest, read_power_csv

PIURA = (-5.24, -79.45)
IOWA = (42.03, -93.62)


@pytest.fixture(scope='module')
def piura():
    return C.monthly_profile(*PIURA)


def test_exact_coordinates_only():
    assert C.power_file(0.0, 0.0) is None  # no nearest-point substitution
    frame, meta = C.power_file(*PIURA)
    assert meta['latitude'] == PIURA[0] and meta['sha256'] == digest(Path(meta['file']))
    assert meta['period'] == ['1981-01-01', '2024-12-31'] and meta['missing_days'] == 0


def test_widest_series_wins():
    """Two downloads share this point (1981 and 1984); the longer one must be chosen."""
    files = [p for p in Path('data/raw/power').glob('*.csv') if read_power_csv(p)[1]['coordinates']['latitude'] == PIURA[0]]
    _, meta = C.power_file(*PIURA)
    if len(files) > 1:
        assert meta['period'][0] == '1981-01-01'
    assert Path(meta['file']).name.startswith('POWER_Point_Daily_1981')


def test_et0_only_where_radiation_exists(piura):
    profile, meta = piura
    assert (profile.years_rain == 44).all() and (profile.years_et0 == 41).all()  # radiation starts 1984
    assert 'ALLSKY_SFC_SW_DWN' in meta['missing_percent'] and meta['missing_percent']['ALLSKY_SFC_SW_DWN'] > 0
    assert set(meta['missing_percent']) == {'ALLSKY_SFC_SW_DWN'}  # nothing else is missing
    frame, _ = C.daily_series(*PIURA)
    assert frame[frame.fecha < '1984-01-01'].et0_mm.isna().all() and frame[frame.fecha >= '1984-01-01'].et0_mm.notna().all()


def test_monthly_values_match_the_raw_series(piura):
    profile, _ = piura
    frame, _ = C.daily_series(*PIURA)
    january = frame[frame.fecha.dt.month.eq(1)]
    assert profile.loc[0, 't_min_absolute_c'] == pytest.approx(round(float(january.T2M_MIN.min()), 2))
    totals = january.groupby(january.fecha.dt.year).PRECTOTCORR.sum()
    assert profile.loc[0, 'rain_mean_mm'] == pytest.approx(round(float(totals.mean()), 2))
    assert len(profile) == 12 and profile.month.tolist() == list(range(1, 13))


def test_frost_separates_the_pilots(piura):
    profile, _ = piura
    assert profile.frost_days_mean.sum() == 0 and profile.t_min_absolute_c.min() > 0  # no frost in 44 years
    iowa, _ = C.monthly_profile(*IOWA)
    assert iowa.frost_days_mean.sum() > 100 and iowa.loc[0, 'frost_year_probability'] == 1.0
    warm, _ = C.monthly_profile(*IOWA, frost_threshold=-10.0)  # a stricter threshold yields fewer days
    assert warm.frost_days_mean.sum() < iowa.frost_days_mean.sum()


def test_annual_series_and_completeness():
    annual, _ = C.annual_series(*PIURA)
    assert len(annual) == 44 and annual.complete_year.all()
    assert annual[annual.year < 1984].et0_mm.isna().all() and annual[annual.year >= 1984].et0_mm.notna().all()
    assert annual.rain_mm.notna().all() and (annual.frost_days == 0).all()


def test_frost_risk_reports_unknown_crops():
    from src.crop_library import build_library
    risk = C.frost_risk_by_crop(None, build_library())
    assert risk['maize']['evaluable'] is False and 'killing temperature' in risk['maize']['reason']
    assert risk['wheat']['evaluable'] is True and risk['wheat']['killing_temperature_c'] == 0.0


def test_exports_written():
    if not Path('data/processed/climate_profiles.parquet').exists():
        pytest.skip('perfiles no generados todavía: corre scripts/climate_profiles.py')
    profile = pd.read_csv('data/processed/climate_profile_iowa.csv')
    assert len(profile) == 12 and profile.pilot.eq('iowa').all()
    combined = pd.read_parquet('data/processed/climate_profiles.parquet')
    assert set(combined.pilot) == {p['name'] for p in C.pilots()} and len(combined) == 72
