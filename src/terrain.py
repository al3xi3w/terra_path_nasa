"""Elevation and slope around each pilot from NASA SRTMGL1 v003 (1 arc-second, February 2000).

    python -m src.terrain        # writes data/processed/terreno.csv

Reads the original .hgt.zip tiles in data/raw/srtm without modifying them. A tile is a 3601 x 3601
grid of big-endian int16 metres, rows from north to south, whose edges overlap the neighbouring
tiles. -32768 marks a void: voids stay null and are counted, never filled.

Slope uses central differences with the real cell size in metres at that latitude (about 30.9 m
north-south, 30.9 x cos(latitude) east-west). Within the 1 km radius the statistics use only the
cells whose centre is inside the circle; a radius that crosses the tile edge is reported as such
rather than silently truncated.
"""
import io, json, math, zipfile
from pathlib import Path
import numpy as np
import pandas as pd
from .pipeline import ROOT, digest
from .climate_profile import pilots, power_file

SIZE = 3601
VOID = -32768
ARCSEC_M = 6371008.8 * math.pi / 180 / 3600  # metres per arc-second along a meridian (mean Earth radius)
RADIUS_M = 1000.0


def tile_name(latitude, longitude):
    lat, lon = math.floor(latitude), math.floor(longitude)
    return f"{'N' if lat >= 0 else 'S'}{abs(lat):02d}{'E' if lon >= 0 else 'W'}{abs(lon):03d}"


def read_tile(path):
    """Elevation grid in metres as float, voids as NaN."""
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if n.endswith('.hgt')]
        if len(names) != 1:raise ValueError(f'{path}: expected one .hgt member')
        raw = np.frombuffer(z.read(names[0]), dtype='>i2')
    if raw.size != SIZE * SIZE:raise ValueError(f'{path}: {raw.size} cells, expected {SIZE * SIZE} (SRTMGL1)')
    grid = raw.reshape(SIZE, SIZE).astype(float)
    grid[grid == VOID] = np.nan
    return grid


def cell_of(latitude, longitude):
    """Row and column of the cell centred nearest to the point (row 0 = northern edge)."""
    lat0, lon0 = math.floor(latitude), math.floor(longitude)
    return round((lat0 + 1 - latitude) * 3600), round((longitude - lon0) * 3600)


def slope_degrees(grid, dy, dx):
    """Slope from central differences; NaN wherever a neighbour is void."""
    gy, gx = np.gradient(grid, dy, dx)
    slope = np.degrees(np.arctan(np.hypot(gx, gy)))
    slope[np.isnan(grid)] = np.nan  # central differences skip the cell itself: a void must not get a slope
    return slope


def terrain_at(latitude, longitude, grid, radius_m=RADIUS_M):
    dy = ARCSEC_M
    dx = ARCSEC_M * math.cos(math.radians(latitude))
    row, col = cell_of(latitude, longitude)
    ry, rx = math.ceil(radius_m / dy), math.ceil(radius_m / dx)
    r0, r1, c0, c1 = row - ry, row + ry + 1, col - rx, col + rx + 1
    inside_tile = r0 >= 0 and c0 >= 0 and r1 <= SIZE and c1 <= SIZE
    # one extra cell on each side so the slope at the circle edge has both neighbours
    pad = grid[max(r0 - 1, 0):min(r1 + 1, SIZE), max(c0 - 1, 0):min(c1 + 1, SIZE)]
    slope = slope_degrees(pad, dy, dx)
    off_r, off_c = max(r0 - 1, 0), max(c0 - 1, 0)
    rows, cols = np.mgrid[off_r:off_r + pad.shape[0], off_c:off_c + pad.shape[1]]
    circle = ((rows - row) * dy) ** 2 + ((cols - col) * dx) ** 2 <= radius_m ** 2
    elev, slp = pad[circle], slope[circle]
    ok = ~np.isnan(elev)
    point = grid[row, col]
    stats = lambda a: a[~np.isnan(a)]
    s = stats(slp)
    return dict(elevation_point_m=None if np.isnan(point) else float(point),
                elevation_mean_1km_m=round(float(elev[ok].mean()), 1) if ok.any() else None,
                elevation_min_1km_m=float(elev[ok].min()) if ok.any() else None,
                elevation_max_1km_m=float(elev[ok].max()) if ok.any() else None,
                slope_point_deg=None if np.isnan(slope[row - off_r, col - off_c]) else round(float(slope[row - off_r, col - off_c]), 2),
                slope_mean_1km_deg=round(float(s.mean()), 2) if s.size else None,
                slope_p90_1km_deg=round(float(np.percentile(s, 90)), 2) if s.size else None,
                cells_1km=int(circle.sum()), void_cells_1km=int((~ok).sum()), radius_inside_tile=inside_tile)


_TILES = {}


def point_elevation(latitude, longitude, root=ROOT):
    """SRTM elevation of the cell nearest to the point, with provenance; None when the tile is absent or void."""
    path = Path(root) / 'data/raw/srtm' / f'{tile_name(latitude, longitude)}.SRTMGL1.hgt.zip'
    if not path.exists():return None
    if path not in _TILES:_TILES[path] = (read_tile(path), digest(path))
    grid, sha = _TILES[path]
    row, col = cell_of(latitude, longitude)
    value = grid[row, col]
    if np.isnan(value):return None
    return dict(value_m=float(value), source='NASA SRTMGL1 v003, 1 arc-second', file=str(path.relative_to(Path(root))), sha256=sha)


def terrain_table(root=ROOT):
    rows, cache = [], {}
    for p in pilots(root):
        lat, lon = p['latitude'], p['longitude']
        name = tile_name(lat, lon)
        path = Path(root) / 'data/raw/srtm' / f'{name}.SRTMGL1.hgt.zip'
        base = dict(pilot=p['name'], label=p['label'], latitude=lat, longitude=lon, tile=name)
        found = power_file(lat, lon, root)
        base['merra2_elevation_m'] = found[1]['elevation_m'] if found else None
        if not path.exists():
            rows.append(dict(base, status='no_tile', reason=f'falta {path.name} en data/raw/srtm'));continue
        if path not in cache:cache[path] = read_tile(path)
        rows.append(dict(base, status='ok', **terrain_at(lat, lon, cache[path]),
                         source='NASA SRTMGL1 v003 (LP DAAC), 1 arc-second, febrero 2000', file=str(path.relative_to(Path(root))),
                         sha256=digest(path), unit_elevation='m', unit_slope='degrees', radius_m=RADIUS_M,
                         method='celda más cercana al punto; estadísticas sobre celdas con centro dentro del radio; pendiente por diferencias centrales'))
    return pd.DataFrame(rows)


def write_terrain(root=ROOT):
    table = terrain_table(root)
    path = Path(root) / 'data/processed/terreno.csv'
    table.to_csv(path, index=False)
    return path, table


if __name__ == '__main__':
    path, table = write_terrain()
    print(path)
    print(table[['pilot', 'tile', 'elevation_point_m', 'merra2_elevation_m', 'elevation_min_1km_m', 'elevation_max_1km_m',
                 'slope_mean_1km_deg', 'slope_p90_1km_deg', 'void_cells_1km', 'radius_inside_tile']].to_string(index=False))
