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
  for (const f of ['data/app_data.js', 'i18n.js']) vm.runInContext(src(f), ctx);
  vm.runInContext(src('app.js'), ctx);
  return { html: els.app.innerHTML };
}
const text = h => h.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ');
const U = '#user=Ana&';

let r = run('');
assert(r.html.includes('Terrapath') && !r.html.includes('Funciona sin internet'), 'bienvenida');

r = run('#view=routes&pilot=iowa&care=water');
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
let tx = text(r.html);
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
