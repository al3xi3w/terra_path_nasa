import pytest
from src import sensitivity as W
from src.rotation_scores import weighted_total


def rows():
    return [dict(sequence=['a', 'b', 'c'], water=100, soil=40, risk=50),
            dict(sequence=['c', 'b', 'a'], water=100, soil=40, risk=50),   # same set, other order
            dict(sequence=['a', 'b', 'd'], water=60, soil=100, risk=50),
            dict(sequence=['a', 'e', 'f'], water=70, soil=60, risk=50)]


def test_split_keeps_weights_summing_to_one():
    for w in W.SWEEP:
        assert sum(W.split(w).values()) == pytest.approx(1.0)
    assert W.split(0.5) == W.ALTERNATIVE and W.split(0.4) == W.BASE


def test_weighted_top3_dedupes_crop_sets_and_follows_weights():
    top = W.weighted_top3(rows(), W.BASE)
    assert len({frozenset(r['sequence']) for r in top}) == len(top) == 3
    soil_heavy = W.weighted_top3(rows(), {'water': 0.1, 'soil': 0.8, 'risk': 0.1})
    assert soil_heavy[0]['sequence'] == ['a', 'b', 'd']
    assert W.weighted_top3(rows(), {'water': 0.8, 'soil': 0.1, 'risk': 0.1})[0]['sequence'] == ['a', 'b', 'c']


def test_axis_spread_flags_constant_axes():
    spread = W.axis_spread(rows())
    assert spread['risk']['distinct'] == 1  # a constant axis cannot change any ranking
    assert spread['water'] == dict(min=60, max=100, distinct=3)


def test_weighted_total_defaults_to_equal_weights():
    assert weighted_total(dict(water=1, soil=2, risk=3)) == 6


@pytest.fixture(scope='module')
def iowa():
    return W.sensitivity_point(42.03, -93.62, 'Iowa central (US)')


def test_iowa_report_states_assumption_and_source(iowa):
    assert iowa['status'] == 'tested'
    assert 'reparte' in iowa['weights']['assumption']
    assert iowa['source']['sha256'] and iowa['source']['power_file'].startswith('data/raw/power/')
    assert set(iowa['sweep_top3']) == set(W.SWEEP)


def test_iowa_risk_axis_is_constant(iowa):
    """Documents the known limitation: with one risk value, weights can only reorder by water and soil."""
    assert iowa['axis_spread']['risk']['distinct'] == 1
