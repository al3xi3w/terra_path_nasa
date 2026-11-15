import math
import numpy as np
import pandas as pd
import pytest
from src import terrain as T


def test_tile_names():
    assert T.tile_name(-5.24, -79.45) == 'S06W080'
    assert T.tile_name(42.03, -93.62) == 'N42W094'
    assert T.tile_name(-0.33, 35.94) == 'S01E035'
    assert T.tile_name(36.95, -120.28) == 'N36W121'


def test_slope_of_a_known_plane():
    """A plane rising 1 m per metre eastwards has a 45 degree slope everywhere inside."""
    dx = dy = 30.0
    cols = np.arange(50) * dx
    grid = np.tile(cols, (50, 1))
    slope = T.slope_degrees(grid, dy, dx)
    assert np.allclose(slope[1:-1, 1:-1], 45.0)


def test_voids_stay_null_and_are_counted():
    grid = np.full((T.SIZE, T.SIZE), 100.0)
    row, col = T.cell_of(-5.5, -79.5)
    grid[row, col] = np.nan
    out = T.terrain_at(-5.5, -79.5, grid)
    assert out['elevation_point_m'] is None and out['slope_point_deg'] is None
    assert out['void_cells_1km'] == 1 and out['elevation_mean_1km_m'] == 100.0  # mean of real cells only
    assert out['radius_inside_tile']


def test_circle_has_the_expected_area():
    grid = np.zeros((T.SIZE, T.SIZE))
    out = T.terrain_at(-0.5, 35.5, grid)
    cell_area = T.ARCSEC_M ** 2 * math.cos(math.radians(-0.5))
    assert out['cells_1km'] * cell_area == pytest.approx(math.pi * T.RADIUS_M ** 2, rel=0.02)


def test_real_table_has_provenance():
    path = T.write_terrain()[0]
    table = pd.read_csv(path)
    ok = table[table.status == 'ok']
    assert set(table.pilot) == set(ok.pilot)  # every pilot has its tile
    assert ok.sha256.str.len().eq(64).all() and ok.file.str.startswith('data/raw/srtm/').all()
    assert (ok.unit_elevation == 'm').all() and (ok.radius_m == 1000).all()
    huancabamba = ok[ok.pilot == 'piura_1'].iloc[0]
    assert 1800 < huancabamba.elevation_point_m < 2100 and huancabamba.slope_mean_1km_deg > 5  # Andean slope
