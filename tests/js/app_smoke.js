// Prueba de humo de app/app.js en Node, con un DOM mínimo falso. Uso: node tests/js/app_smoke.js
const fs = require('fs'), path = require('path'), vm = require('vm'), assert = require('assert'), crypto = require('crypto');
const APP = path.join(__dirname, '..', '..', 'app');
const src = f => fs.readFileSync(path.join(APP, f), 'utf8');

function run(hash) {
  const el = () => ({ innerHTML: '', hidden: false, innerText: '', addEventListener() {}, remove() {},
    querySelector(sel) { return this.innerHTML.includes(sel.replace('.', 'class="')) ? {} : null; } });
  const els = { app: el() };
  const window = { scrollTo() {} };
  const ctx = {
    window, console, URLSearchParams, Date, Math, JSON, Object, Array, String, Set, Blob: function () {}, unescape, encodeURIComponent,
    location: { hash, protocol: 'file:' }, navigator: {}, localStorage: { getItem: () => null, setItem() {} },
    document: { getElementById: id => els[id] || null, addEventListener() {}, documentElement: {}, body: { classList: { toggle() {} }, appendChild() {} } }
  };
  window.document = ctx.document; window.location = ctx.location;
  vm.createContext(ctx);
  for (const f of ['data/app_data.js', 'i18n.js', 'i18n_more.js']) vm.runInContext(src(f), ctx);
  vm.runInContext(src('app.js'), ctx);
  return { html: els.app.innerHTML };
}
const text = h => h.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ');
const U = '#lang=es&user=Ana&';
const E0 = '#user=Ana&';
let tx;

let r = run('');
assert(r.html.includes('TerraPath') && text(r.html).includes('Get started') && r.html.includes('data-act="lang-toggle"') && r.html.includes('aria-expanded="false"'), 'bienvenida en inglés, idioma en lista desplegable cerrada');
r = run(E0 + 'view=routes&pilot=piura_1&care=water&now=potato&lang=pt');
assert(text(r.html).includes('Suas rotas para') && text(r.html).includes('Colheita segura') && text(r.html).includes('Início'), 'portugués');
assert(text(run(E0 + 'view=account&lang=pt').html).includes('Tradução automática'), 'aviso de traducción automática');
r = run(E0 + 'view=farm&pilot=iowa&route=0&farm=2026-11-15&today=2027-06-10&tab=month&lang=zh');
assert(text(r.html).includes('我的田地') && text(r.html).includes('6月'), 'chino');
r = run(E0 + 'view=inicio&lang=ar');
assert(text(r.html).includes('مرحبًا'), 'árabe');
r = run('#view=home&lang=qu');
assert(text(r.html).includes('Runasimi (Quechua) is not available yet'), 'idioma sin traducción → aviso, app en inglés');

// Interfaz en inglés (por defecto) y botón del asistente (IA): visible en Inicio, Mi chacra, Rutas y Cuenta, sin funciones.
const E = '#user=Ana&';
r = run(E + 'view=routes&pilot=piura_1&care=water&now=potato');
tx = text(r.html);
assert(tx.includes('Your routes for') && tx.includes('Compare your routes') && tx.includes('Reliable harvest') && tx.includes('For you'), 'rutas en inglés');
assert(r.html.includes('class="fab-ai"') && !r.html.includes('class="sheet"'), 'botón IA en Rutas, cerrado');
assert(text(r.html).includes('Home') && text(r.html).includes('My field') && text(r.html).includes('Account'), 'pestañas en inglés');
for (const v of ['view=inicio', 'view=account', 'view=farm&pilot=iowa&route=0&farm=2026-11-15&today=2027-06-10'])
  assert(run(E + v).html.includes('class="fab-ai"'), 'botón IA en ' + v);
for (const v of ['view=why&pilot=iowa&care=water&route=1', 'view=calendar&pilot=iowa&care=water&route=1', 'view=where', 'view=home'])
  assert(!run(E + v).html.includes('class="fab-ai"'), 'sin botón IA en ' + v);
r = run(E + 'view=farm&pilot=iowa&route=0&farm=2026-11-15&today=2027-06-10&tab=week');
assert(text(r.html).includes('Day by day') && (r.html.match(/class="wk-day"/g) || []).length === 7 && text(r.html).includes('Typical conditions, not a forecast.'), 'día a día: 7 días');

r = run('#view=routes&pilot=iowa&care=water&lang=es');
assert(text(r.html).includes('Iniciar sesión') && text(r.html).includes('Crear cuenta'), 'sin sesión → acceso');
assert(!r.html.includes('f_name'), 'iniciar sesión no pide nombre');
r = run('#view=login&auth=signup');
assert(r.html.includes('id="f_name"') && r.html.includes('id="f_pin2"'), 'crear cuenta');

r = run(U + 'view=where');
assert(text(r.html).includes('Chacra a 1921 m') && text(r.html).includes('dato del clima a 2038 m'), 'altitudes rotuladas');
assert(text(r.html).includes('dato del clima a 878 m') && text(r.html).includes('Chacra a 2864 m'), 'Piura norte');
assert(!r.html.includes('tabbar'), 'sin pestañas durante los pasos');

r = run(U + 'view=routes&pilot=piura_1&care=water&now=potato');
assert(r.html.includes('Compara tus rutas') && text(r.html).includes('Tu rotación'), 'comparación');
assert(text(r.html).includes('Lo que ya siembras') && text(r.html).includes('papa tres campañas seguidas'), 'un cultivo = monocultivo');
assert(!r.html.toLowerCase().includes('polygon'), 'sin radar');
assert((r.html.match(/class="hbar/g) || []).length >= 9 + 3 + 12, 'barras con número');
assert(r.html.includes('class="tabbar"') && !text(r.html).includes('Pregúntame'), 'pestañas, sin chat');

// Maíz este año, trigo el año pasado, soya hace dos años (Iowa): su rotación aparece con sus cultivos.
r = run(U + 'view=routes&pilot=iowa&care=water&now=maize&history=wheat,soybean');
tx = text(r.html);
assert(tx.includes('Lo que ya siembras') && tx.indexOf('Soya') < tx.indexOf('Trigo') && tx.indexOf('Trigo') < tx.indexOf('Maíz'), 'orden de siembra: ' + tx.slice(0, 400));
assert(tx.includes('Trigo y maíz son de la misma familia'), 'regla de familia');
assert(tx.includes('Sin dato de cuánta helada aguanta: soya y maíz'), 'helada desconocida');
assert(tx.indexOf('Ruta 2') < tx.indexOf('Ruta 1') && tx.includes('Lleva trigo, como ahora'), 'ruta con trigo primero');
r = run(U + 'view=routes&pilot=iowa&care=water&now=clover_red');
assert(r.html.includes('class="unk"'), 'dato faltante = guion gris');

r = run(U + 'view=why&pilot=iowa&care=water&route=1');
assert(!/1981|2024/.test(text(r.html)) && text(r.html).includes('En los últimos 9 años'), 'sin años');
assert(!text(r.html).includes('De dónde salen'), 'sin fuentes');

r = run(U + 'view=inicio');
assert(text(r.html).includes('Hola, Ana') && text(r.html).includes('Aún no eliges tu rotación'), 'inicio sin rotación');
r = run(U + 'view=inicio&pilot=iowa&care=water&route=0&farm=2026-11-15&today=2027-06-10');
const home = text(r.html);
assert(home.includes('Iowa central') && home.includes('Ahora en tu chacra') && home.includes('Alfalfa') && home.includes('Creciendo'), 'inicio: ' + home);
assert(home.includes('Esta semana') && / mm /.test(home) && home.includes('Tu rotación'), 'inicio: semana y rotación');
assert(r.html.includes('data-nav="inicio" aria-current="page"'), 'pestaña Inicio activa');
r = run(U + 'view=account');
assert(text(r.html).includes('Cerrar sesión') && text(r.html).includes('Ana'), 'cuenta');

r = run(U + 'view=farm&pilot=iowa&route=0&farm=2026-11-15&today=2027-06-10&tab=year');
assert((r.html.match(/class="step /g) || []).length === 3, 'tres campañas');
r = run(U + 'view=farm&pilot=iowa&route=0&farm=2026-11-15&today=2027-06-10&tab=month');
assert((r.html.match(/class="cd( dark)?( now)?"/g) || []).length === 30, 'junio = 30 días: ' + (r.html.match(/class="cd( dark)?( now)?"/g) || []).length);
assert(text(r.html).includes('Lluvia del mes') && /\d+ mm/.test(text(r.html)), 'total del mes');
assert(text(r.html).includes('no es un pronóstico'), 'rotulado como año normal');

// La clave se guarda como SHA-256: la función de la app coincide con la de Node.
const js = src('app.js'), start = js.indexOf('  function sha256('), end = js.indexOf('\n  }\n', start) + 4;
const sha = vm.runInNewContext(js.slice(start, end) + '; sha256', { unescape, encodeURIComponent });
for (const s of ['', 'abc', 'a1b2c3d4e5f6a7b81234', 'x'.repeat(100), 'ñandú']) {
  assert.strictEqual(sha(s), crypto.createHash('sha256').update(s, 'utf8').digest('hex'), 'sha256 ' + s);
}
console.log('ok');
