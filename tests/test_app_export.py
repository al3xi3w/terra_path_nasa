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


def test_service_worker_version_follows_data_and_code(data):
    """New data or new app code -> new cache name, so installed phones drop the old copy."""
    import hashlib
    sw = (APP / 'sw.js').read_text()
    files = [APP / 'data/app_data.js'] + [APP / f for f in ('index.html', 'app.js', 'i18n.js', 'i18n_more.js', 'styles.css', 'manifest.webmanifest')]
    assert f"terrapath-{hashlib.sha256(''.join(digest(f) for f in files).encode()).hexdigest()[:10]}" in sw


def string_tables():
    src = (APP / 'i18n.js').read_text()
    en = src.split('\n  en: {')[1].split('\n  es: {')[0]
    es = src.split('\n  es: {')[1].split('\n};')[0]
    return en, es


def test_every_text_key_exists_in_english_and_spanish():
    js = (APP / 'app.js').read_text()
    keys = {k for k in re.findall(r"\bt\('([a-z_0-9]+)'", js) if not k.endswith('_')}  # 'care_' + k is listed below
    keys |= set(re.findall(r"'(m_[a-z]+)'", js))
    keys |= {'year_0', 'year_1', 'year_2', 'care_water', 'care_soil', 'care_safe', 'care_water_sub', 'care_soil_sub', 'care_safe_sub'}
    keys |= {'tab_week', 'tab_month', 'tab_year'}
    keys |= {'status_' + k for k in ('wait', 'sown', 'grow', 'done', 'rest')}
    keys |= {'fail_' + k for k in ('altitude', 'heat', 'cold', 'frost', 'annual_rain', 'cycle')}
    keys |= set(re.findall(r"\['[a-z]+', '(nav_[a-z]+)'", js))
    for table in string_tables():
        missing = [k for k in keys if not re.search(rf"\b{k}:", table)]
        assert not missing, missing


def test_quechua_is_not_machine_filled():
    """Quechua must be written by a native speaker of the local variety; until then it has no table
    and the app shows English with a note."""
    src = (APP / 'i18n.js').read_text()
    assert not re.search(r"\bqu:\s*\{", src)
    assert "['qu', 'Runasimi (Quechua)']" in src


def test_palette_has_no_red():
    css = (APP / 'styles.css').read_text().lower()
    assert not re.search(r'\bred\b', re.sub(r'/\*.*?\*/', '', css, flags=re.S))  # 'reduced-motion' is not a colour
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
    assert 'Rutas de Cultivo' not in joined and '<title>TerraPath</title>' in files['index.html']
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
    for gone in ('Pregúntame', 'De dónde salen los datos', 'sources('):
        assert gone not in es + js + (APP / 'index.html').read_text(), gone


def test_ai_button_is_only_a_placeholder():
    """The assistant (IA) button is a future improvement: it only opens a 'coming soon' note.
    No chat, no model, no network call from the app code."""
    js, strings = (APP / 'app.js').read_text(), (APP / 'i18n.js').read_text()
    assert 'class="fab-ai"' in js and "ai_soon: 'Coming soon. For now, ask your farm adviser.'" in strings
    for gone in ('fetch(', 'XMLHttpRequest', 'WebSocket', '<textarea', 'api.anthropic', 'openai'):
        assert gone not in js, gone


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


def test_every_listed_language_is_complete_or_falls_back_to_english():
    """Each translated language has every English key, the same {placeholders}, 12 months, 7 weekdays and
    every crop. Quechua and Aymara have no table on purpose (native speakers must write them): English + a note."""
    import shutil, subprocess
    node = shutil.which('node')
    if not node:pytest.skip('node no disponible')
    script = """
      global.window = {};
      require(process.argv[1] + '/i18n.js'); require(process.argv[1] + '/i18n_more.js');
      const S = window.STRINGS, en = S.en, out = {};
      for (const [code] of window.LANGUAGES) {
        const t = S[code];
        if (!t) { out[code] = 'english'; continue; }
        const bad = [];
        for (const k of Object.keys(en)) {
          if (k === 'app_name') continue;
          const a = en[k], b = t[k];
          if (b === undefined) { bad.push('missing ' + k); continue; }
          if (typeof a === 'string') {
            const ph = s => (s.match(/\\{[a-zA-Z]+\\}/g) || []).map(x => x.toLowerCase()).sort().join();
            if (ph(a) !== ph(b)) bad.push('placeholders ' + k);
          } else if (Array.isArray(a) && a.length !== b.length) bad.push('length ' + k);
          else if (!Array.isArray(a) && typeof a === 'object' && Object.keys(a).some(c => !b[c])) bad.push('crops ' + k);
        }
        out[code] = bad.length ? bad : 'ok';
      }
      console.log(JSON.stringify({ out, mt: window.MACHINE_TRANSLATED }));
    """
    res = json.loads(subprocess.run([node, '-e', script, str(APP)], capture_output=True, text=True, check=True).stdout)
    out = res['out']
    assert out['en'] == 'ok' and out['es'] == 'ok'
    for code in ('pt', 'fr', 'sw', 'hi', 'zh', 'ar'):
        assert out[code] == 'ok', (code, out[code])
        assert code in res['mt']   # the app tells the farmer it is a machine translation
    assert out['qu'] == 'english' and out['ay'] == 'english'
