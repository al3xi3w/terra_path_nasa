import json, re
from pathlib import Path
import pytest
from src import app_export as A
from src.pipeline import ROOT, digest

APP = Path(ROOT) / 'app'


@pytest.fixture(scope='module')
def data():
    out, data = A.write()
    return data


def pilot(data, name):
    return next(p for p in data['pilots'] if p['id'] == name)


def test_every_pilot_exported_with_provenance(data):
    assert {p['id'] for p in data['pilots']} == {'piura_1', 'piura_2', 'piura_3', 'iowa', 'kenia', 'california'}
    for p in data['pilots']:
        prov = p['provenance']
        assert len(prov['power_sha256']) == 64 and prov['power_file'].startswith('data/raw/power/')
        assert len(p['monthly']) == 12


def test_routes_are_the_engine_routes(data):
    """The app shows the engine's routes, never new ones: three-crop routes first, then with a rest."""
    for p in data['pilots']:
        engine = json.loads((Path(ROOT) / f"data/processed/routes_{p['id']}.json").read_text())
        allowed = {frozenset(r['sequence']) for g in ('routes', 'routes_with_fallow') for r in (engine.get(g) or {}).values() if r}
        assert all(frozenset(r['sequence']) in allowed for r in p['routes'])
        kinds = [r['kind'] for r in p['routes']]
        assert kinds == sorted(kinds, key=lambda k: k != 'tres_cultivos') and len(p['routes']) <= 3


def test_missing_data_stays_null(data):
    p = pilot(data, 'iowa')
    maize = next(c for c in p['crops'] if c['key'] == 'maize')
    assert maize['frost_evaluable'] is False and maize['frost_days'] is None  # no killing temperature in EcoCrop
    clover = next(c for c in p['crops'] if c['key'] == 'clover_red')
    assert clover['demand_mm'] is None and clover['water'] is None  # no FAO-56 Kc
    for c in p['crops']:
        if c['months'] is None:assert c['rain_mm'] is None and c['risk'] is None


def test_mountain_warning_and_frost(data):
    assert pilot(data, 'piura_1')['terrain']['mountain_warning'] is True   # Huancabamba
    assert pilot(data, 'iowa')['terrain']['mountain_warning'] is False
    assert pilot(data, 'piura_1')['first_frost']['years_with_frost'] == 0
    iowa = pilot(data, 'iowa')['first_frost']
    assert iowa['month'] in (9, 10, 11) and iowa['years_with_frost'] > 30


def test_service_worker_version_follows_data(data):
    sw = (APP / 'sw.js').read_text()
    assert f"terrapath-{digest(APP / 'data/app_data.js')[:10]}" in sw


def test_every_text_key_exists_in_spanish():
    js = (APP / 'app.js').read_text()
    keys = {k for k in re.findall(r"\bt\('([a-z_0-9]+)'", js) if not k.endswith('_')}  # 'care_' + k is listed below
    keys |= set(re.findall(r"'(m_[a-z]+)'", js))
    keys |= {'year_0', 'year_1', 'year_2', 'care_water', 'care_soil', 'care_safe', 'care_water_sub', 'care_soil_sub', 'care_safe_sub'}
    keys |= {'tab_week', 'tab_month', 'tab_year'}
    keys |= {'status_' + k for k in ('wait', 'sown', 'grow', 'done', 'rest')}
    keys |= {'fail_' + k for k in ('altitude', 'heat', 'cold', 'frost', 'annual_rain', 'cycle')}
    keys |= set(re.findall(r"\['[a-z]+', '(nav_[a-z]+)'", js))
    es = (APP / 'i18n.js').read_text().split('qu:')[0]
    missing = [k for k in keys if not re.search(rf"\b{k}:", es)]
    assert not missing, missing


def test_quechua_is_not_machine_filled():
    """Quechua must be written by a native speaker of the local variety; until then it stays empty."""
    assert re.search(r"qu:\s*\{\s*\}", (APP / 'i18n.js').read_text())


def test_palette_has_no_red():
    css = (APP / 'styles.css').read_text().lower()
    assert 'red' not in re.sub(r'/\*.*?\*/', '', css, flags=re.S)
    for hexcolor in re.findall(r'#([0-9a-f]{6})\b', css):
        r, g, b = (int(hexcolor[i:i + 2], 16) for i in (0, 2, 4))
        assert not (r > 180 and g < 90 and b < 90), hexcolor


def test_altitudes_come_from_the_engine_point(data):
    """Farm altitude = SRTM used by the engine; climate-cell altitude = POWER header. Both from routes_<pilot>.json."""
    for p in data['pilots']:
        point = json.loads((Path(ROOT) / f"data/processed/routes_{p['id']}.json").read_text())['point']
        assert p['terrain']['merra2_m'] == round(point['elevation_m'])
        assert p['terrain']['srtm_m'] == round(point['elevation_for_suitability']['value_m'])
    assert pilot(data, 'piura_3')['terrain']['merra2_m'] == 878  # the gap the app labels, never hides


def test_daily_normals_are_normals_not_fill(data):
    for p in data['pilots']:
        d = p['daily']
        assert all(len(d[k]) == 366 for k in ('rain_mm', 't_min_c', 'et0_mm', 'frost_share'))
        assert d['period'] == ['1981-01-01', '2024-12-31']
        assert all(v is None or 0 <= v <= 1 for v in d['frost_share'])
        assert all(v is None or v >= 0 for v in d['rain_mm'])
    iowa = pilot(data, 'iowa')['daily']
    assert iowa['frost_share'][14] > 0.9 and iowa['frost_share'][196] == 0  # 15 Jan vs 15 Jul


def test_app_is_terrapath_and_drops_limitation_texts():
    files = {f.name: f.read_text() for f in [APP / 'index.html', APP / 'app.js', APP / 'i18n.js', APP / 'manifest.webmanifest', APP / 'sw.js']}
    joined = '\n'.join(files.values())
    assert 'Rutas de Cultivo' not in joined and '<title>Terrapath</title>' in files['index.html']
    for gone in ('Funciona sin internet', 'El mapa necesita internet', 'No tenemos datos de cuánto rinde', 'No podemos evaluar la helada'):
        assert gone not in joined, gone
    assert 'Antes de sembrar, consulta con tu técnico agrario.' in files['i18n.js']
    assert "m_safe: 'Cosecha segura'" in files['i18n.js'] and 'Cosechar más' not in joined
    assert 'radar' not in files['app.js'].lower()


def test_no_google_and_leaflet_is_local():
    joined = '\n'.join(f.read_text() for f in APP.glob('*.*') if f.suffix in ('.html', '.js', '.css'))
    assert 'google' not in joined.lower() and 'maps.googleapis' not in joined
    assert (APP / 'vendor/leaflet/leaflet.js').read_text().startswith('/* @preserve\n * Leaflet 1.9.4')
    assert 'src="vendor/leaflet/leaflet.js"' in (APP / 'index.html').read_text()


def test_interface_emoji_replaced_by_vector_icons():
    js = (APP / 'app.js').read_text()
    for emoji in ('💧', '🌱', '🛡', '📍', '📶', '❄', '⚠', '⛰', '📊', '🛰', '🗺'):
        assert emoji not in js, emoji


def test_app_logic_in_node():
    """Runs app.js in a fake DOM (scripts in tests/js) and checks screens, answers and Mi chacra."""
    import shutil, subprocess
    node = shutil.which('node')
    if not node:pytest.skip('node no disponible')
    out = subprocess.run([node, str(Path(ROOT) / 'tests/js/app_smoke.js')], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stdout + out.stderr


def test_no_years_chat_or_sources_in_the_interface():
    js, es = (APP / 'app.js').read_text(), (APP / 'i18n.js').read_text()
    assert not re.search(r'\b(1981|2024)\b', es + js)
    for gone in ('Pregúntame', 'De dónde salen los datos', 'class="fab', 'sources('):
        assert gone not in es + js + (APP / 'index.html').read_text(), gone


def test_account_never_stores_the_plain_pin():
    js = (APP / 'app.js').read_text()
    assert "pin: sha256(salt + pin)" in js and 'localStorage' in js
    assert not re.search(r"pin:\s*pin\b", js)


def test_app_rotation_rules_match_the_engine(data, tmp_path):
    """The farmer's own rotation is scored in the app with the engine's soil and family rules: same results."""
    import itertools, shutil, subprocess
    from src.crop_library import build_library
    from src.rotation_scores import soil_score, families_ok
    node = shutil.which('node')
    if not node:pytest.skip('node no disponible')
    library = build_library(ROOT)
    keys = library.crop_key.tolist()
    family = dict(zip(library.crop_key, library.family))
    seqs = [list(s) for s in itertools.product(keys, repeat=3)] + [list(s) for s in itertools.permutations(keys, 2)]
    expected = [[soil_score(s, library)[0], families_ok([family[c] for c in s])] for s in seqs]
    case = tmp_path / 'case.json'
    case.write_text(json.dumps(dict(seqs=seqs, expected=expected, crops=pilot(data, 'iowa')['crops'])))
    js = (APP / 'app.js').read_text()
    grab = lambda name: js[js.index(f'  function {name}('):js.index('\n  }\n', js.index(f'  function {name}(')) + 4]
    script = tmp_path / 'check.js'
    script.write_text(grab('soilScore') + grab('familiesOk') + """
const c = JSON.parse(require('fs').readFileSync(process.argv[2], 'utf8'));
const p = { crops: c.crops };
function crop(p, k) { return p.crops.find(x => x.key === k); }
let bad = 0;
c.seqs.forEach((s, i) => {
  const got = [soilScore(p, s), familiesOk(s.map(k => crop(p, k).family))];
  if (got[0] !== c.expected[i][0] || got[1] !== c.expected[i][1]) { bad++; if (bad < 5) console.log(s, got, c.expected[i]); }
});
if (bad) { console.log(bad, 'distintas'); process.exit(1); }
""")
    out = subprocess.run([node, str(script), str(case)], capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stdout + out.stderr
