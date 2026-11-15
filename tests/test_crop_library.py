import json
from pathlib import Path
import pandas as pd
import pytest
from src import crop_library as L


@pytest.fixture(scope='module')
def library():
    return L.build_library()


def test_every_species_resolves(library):
    assert library.found_in_ecocrop.all() and len(library) == 16
    assert library.scientific_name.is_unique and library.crop_key.is_unique
    assert (library.selection_status == 'declared_pending_agronomist_review').all()


def test_botanical_family_not_fao_use_group(library):
    fao = pd.read_parquet('data/processed/agronomy-crops.parquet')
    assert 'OTHER CROPS' in set(fao.crop_family)  # FAO's column is a use group
    assert set(library.family) & {'Gramineae', 'Leguminosae', 'Solanaceae'} and 'OTHER CROPS' not in set(library.family)
    legumes = set(library[library.family_leguminosae].crop_key)
    assert legumes == {'soybean', 'bean_faba', 'bean_common', 'lentil', 'tarwi', 'clover_red', 'alfalfa'}


def test_values_match_ecocrop_and_respect_valid_flags(library):
    eco = pd.read_parquet('data/processed/ecocrop_validated.parquet')
    maize = eco[eco.scientificname.str.strip() == 'Zea mays'].iloc[0]
    row = library[library.crop_key == 'maize'].iloc[0]
    assert row.cycle_min_days == float(maize.gmin_usable) and row.annual_rain_min_mm == float(maize.rmin_usable)
    assert not bool(maize.ktmp_valid) and pd.isna(row.killing_temperature_c)  # invalid stays null, never 0


def test_frost_gaps_reported(library):
    missing = L.missing_properties(library)
    assert {'maize', 'soybean', 'sorghum', 'lentil', 'rice', 'bean_faba'} <= {k for k, v in missing.items() if 'killing_temperature_c' in v}
    assert missing['wheat'] == []


def test_kc_only_from_declared_mapping(library):
    potato = library[library.crop_key == 'potato'].iloc[0]
    assert 'Sweet Potato' in potato.fao56_table12_candidates  # text match, another species
    assert potato.fao56_table12_label == 'Potato' and potato.kc_mid == 1.15  # declared label, never the text match
    maize = library[library.crop_key == 'maize'].iloc[0]
    assert maize.fao56_table12_label == 'Maize, Field (grain)' and maize.kc_mid == 1.20
    assert pd.isna(maize.kc_end) and maize.kc_end_range == '[0.35, 0.6]'  # footnoted range is not collapsed
    assert pd.isna(maize.kc_initial)  # Table 12 blank; group value never propagated
    clover = library[library.crop_key == 'clover_red'].iloc[0]
    assert pd.isna(clover.fao56_table12_label) and pd.isna(clover.kc_mid)  # only Berseem exists: other species
    mapped = set(library[library.kc_mid.notna()].crop_key)
    assert mapped == {'maize', 'soybean', 'barley', 'oat', 'lentil', 'wheat', 'potato', 'alfalfa', 'bean_common'}


def test_several_labels_keep_only_agreed_values(library):
    wheat = library[library.crop_key == 'wheat'].iloc[0]
    assert wheat.kc_mid == 1.15  # identical in spring and both winter wheats
    assert pd.isna(wheat.kc_initial)  # null / 0.4 / 0.7 disagree: not chosen
    assert L.agreed_kc(['Spring Wheat', 'no such label'], L.fao56_table12()) is None


def test_kc_mid_range_has_no_single_value(library):
    sunflower = library[library.crop_key == 'sunflower'].iloc[0]
    assert pd.isna(sunflower.kc_mid) and sunflower.kc_mid_range == '[1.0, 1.15]'
    assert L.single([1.0, 1.15]) is None and L.single([0.75, 0.75]) == 0.75


def test_csv_export_exists():
    csv = pd.read_csv('data/processed/crop_library.csv')
    assert len(csv) == 16 and {'crop_key', 'family', 'kc_mid', 'source'} <= set(csv.columns)


def test_written_table_carries_policy():
    import pyarrow.parquet as pq
    meta = pq.ParquetFile('data/processed/crop_library.parquet').schema_arrow.metadata
    policy = json.loads(meta[b'fieldshift'])
    assert 'ANNUAL' in policy['rainfall'] and 'declared Table 12 label' in policy['kc'] and policy['ecocrop_sha256']
