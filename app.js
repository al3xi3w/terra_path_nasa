// Terrapath: app del agricultor. Sin dependencias externas en tiempo de ejecución (Leaflet va en app/vendor).
// Los datos vienen de app/data/app_data.js (scripts/build_app.py). La app nunca rellena un dato:
// si el motor no lo tiene, muestra "—" con un ícono gris. Ningún número está escrito a mano aquí.
(function () {
  'use strict';
  const DATA = window.APP_DATA;
  const S = window.STRINGS;
  const LANGS = window.LANGUAGES;
  // Pestañas con el botón del asistente (IA). Es solo un marcador: abre un aviso de "próximamente".
  const AI_VIEWS = ['inicio', 'farm', 'routes', 'account'];
  let aiOpen = false, langOpen = false, langSheetOpen = false, lastView = null, navBack = false;
  const FALLOW = 'barbecho';
  const NEAR_KM = 30;
  // Colores de la paleta por eje: Agua, Tierra, Cosecha segura. Hoy (lo que siembra) en gris.
  const AXES = [['water', 'm_water', 'drop', '#1E8F6A'], ['soil', 'm_soil', 'sprout', '#21A159'], ['risk', 'm_safe', 'shield', '#C5DD73']];
  const TODAY_GRAY = '#A9B8AD';
  const CARE_AXIS = { water: 'water', soil: 'soil', safe: 'risk' };
  const TABS = ['week', 'month', 'year'];

  let demoSession = false;
  const fresh = () => ({ lang: 'en', view: 'home', pilot: null, history: [null, null, null], care: null, route: 0, campaign: 0,
    farm: null, farmPoint: null, tab: 'week' });
  const NAV = [['inicio', 'nav_home', 'home'], ['farm', 'nav_farm', 'sprout'], ['routes', 'nav_routes', 'cycle'], ['account', 'nav_account', 'user']];
  const OPEN_VIEWS = ['home', 'login'];          // sin sesión solo se ven estas
  // Cuenta local: se guarda solo en este teléfono (no hay servidor). La clave se guarda como SHA-256 con sal.
  let session = readLS('terrapath_session');
  let accounts = readLS('terrapath_accounts') || {};
  if (session && !accounts[session]) session = null;
  const state = Object.assign(fresh(), session ? accounts[session].state : (readLS('terrapath_state') || {}));
  let todayOverride = null, authTab = 'login', authMsg = '';
  // Enlace directo a una pantalla (demo y pruebas), con una sesión de prueba que no se guarda:
  // #user=Ana&view=farm&pilot=piura_1&care=water&now=potato&route=0&farm=2027-01-10&today=2027-02-03&tab=month
  (function deepLink() {
    const q = new URLSearchParams(location.hash.slice(1));
    if (!q.has('view')) return;
    const known = id => DATA.pilots.some(p => p.id === id);
    Object.assign(state, { view: q.get('view'), route: +(q.get('route') || 0), campaign: +(q.get('campaign') || 0) });
    if (known(q.get('pilot'))) state.pilot = q.get('pilot');
    if (['water', 'soil', 'safe'].includes(q.get('care'))) state.care = q.get('care');
    if (LANGS.some(([code]) => code === q.get('lang'))) state.lang = q.get('lang');
    if (TABS.includes(q.get('tab'))) state.tab = q.get('tab');
    if (q.has('now')) state.history = [q.get('now') || null].concat((q.get('history') || '').split(',').filter(Boolean), [null, null]).slice(0, 3);
    if (q.has('today')) todayOverride = parseDay(q.get('today'));
    if (q.has('farm') && pilot() && pilot().routes[state.route]) {
      state.farm = { pilot: state.pilot, route: state.route, seq: orderedSequence(pilot(), pilot().routes[state.route]), start: q.get('farm') };
    }
    if (q.has('user')) { session = 'demo'; accounts = { demo: { name: q.get('user'), state } }; demoSession = true; }
    if (q.get('auth') === 'signup') authTab = 'signup';
  })();
  const app = document.getElementById('app');

  // ---------- utilidades ----------
  function readLS(key) { try { return JSON.parse(localStorage.getItem(key)); } catch (e) { return null; } }
  function writeLS(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* sin almacenamiento */ } }
  function save() {
    if (demoSession) return;
    if (session && accounts[session]) { accounts[session].state = state; writeLS('terrapath_accounts', accounts); }
    else writeLS('terrapath_state', state);
  }
  function user() { return session && accounts[session] ? accounts[session] : null; }
  function esc(s) { return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }
  function t(key, vars) {
    const table = S[state.lang] || {};
    let s = key in table ? table[key] : S.en[key];
    if (typeof s !== 'string') return s;
    for (const k in (vars || {})) s = s.split('{' + k + '}').join(vars[k]);
    return s;
  }
  // Idioma con textos propios (en, es). Los demás se muestran en inglés con un aviso.
  function translated() { return !!S[state.lang]; }
  function cropName(k) { return (S[state.lang] && S[state.lang].crops && S[state.lang].crops[k]) || S.en.crops[k] || k; }
  function cap(s) { return s.charAt(0).toUpperCase() + s.slice(1); }
  function monthName(m) { return t('months')[m - 1]; }
  function listJoin(items) { return items.length < 2 ? items.join('') : items.slice(0, -1).join(', ') + ' ' + t('and') + ' ' + items[items.length - 1]; }
  function pilot() { return DATA.pilots.find(p => p.id === state.pilot); }
  function crop(p, key) { return p.crops.find(c => c.key === key); }
  function go(view, extra) { Object.assign(state, extra || {}, { view }); save(); render(); window.scrollTo(0, 0); }
  function km(a, b) {
    const R = 6371, r = x => x * Math.PI / 180;
    const dLat = r(b.latitude - a.latitude), dLon = r(b.longitude - a.longitude);
    const h = Math.sin(dLat / 2) ** 2 + Math.cos(r(a.latitude)) * Math.cos(r(b.latitude)) * Math.sin(dLon / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(h));
  }
  function nearest(pt) { return DATA.pilots.map(p => ({ p, d: km(pt, p) })).sort((a, b) => a.d - b.d)[0]; }
  function parseDay(s) { const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s || ''); return m ? new Date(+m[1], +m[2] - 1, +m[3]) : null; }
  function isoDay(d) { return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`; }
  function today() { const d = todayOverride || new Date(); return new Date(d.getFullYear(), d.getMonth(), d.getDate()); }
  function addMonths(d, n) { return new Date(d.getFullYear(), d.getMonth() + n, 1); }
  function addDays(d, n) { return new Date(d.getFullYear(), d.getMonth(), d.getDate() + n); }
  // Índice del día en un año bisiesto (0 = 1 de enero, 59 = 29 de febrero): así viene p.daily.
  function dayIndex(d) { return Math.round((Date.UTC(2000, d.getMonth(), d.getDate()) - Date.UTC(2000, 0, 1)) / 864e5); }
  function round(v, digits) { const f = 10 ** (digits || 0); return Math.round(v * f) / f; }

  // Íconos vectoriales simples (trazo), siempre con su palabra al lado.
  const PATHS = {
    drop: '<path d="M12 3c3.5 4.5 6 8 6 11a6 6 0 0 1-12 0c0-3 2.5-6.5 6-11z"/>',
    sprout: '<path d="M12 21v-9"/><path d="M12 12c0-4-3-6-7-6 0 4 3 6 7 6z"/><path d="M12 10c0-4 3-6 7-6 0 4-3 6-7 6z"/>',
    shield: '<path d="M12 3l7 3v5c0 5-3 8-7 10-4-2-7-5-7-10V6z"/><path d="M9 12l2 2 4-4"/>',
    pin: '<path d="M12 21s-6-6-6-11a6 6 0 0 1 12 0c0 5-6 11-6 11z"/><circle cx="12" cy="10" r="2.2"/>',
    locate: '<circle cx="12" cy="12" r="4"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3"/>',
    snow: '<path d="M12 2v20M3.3 7l17.4 10M3.3 17L20.7 7"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4 12H2M22 12h-2M5 5l1.5 1.5M17.5 17.5L19 19M5 19l1.5-1.5M17.5 6.5L19 5"/>',
    rest: '<path d="M8 6v12M16 6v12"/>',
    calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
    mountain: '<path d="M2 20l7-12 4 6 3-4 6 10z"/>',
    alert: '<path d="M12 3l10 18H2z"/><path d="M12 10v5M12 18v.5"/>',
    chart: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
    cycle: '<path d="M20 12a8 8 0 0 1-14 5M4 12a8 8 0 0 1 14-5"/><path d="M18 3v4h-4M6 21v-4h4"/>',
    unknown: '<circle cx="12" cy="12" r="9"/><path d="M8 12h8"/>',
    close: '<path d="M6 6l12 12M18 6L6 18"/>',
    check: '<path d="M5 12l5 5 9-10"/>',
    thermo: '<path d="M10 14V5a2 2 0 0 1 4 0v9a4 4 0 1 1-4 0z"/>',
    leaf: '<path d="M5 19c0-8 5-14 15-14 0 10-6 15-14 15"/><path d="M5 19l7-7"/>',
    home: '<path d="M3 11l9-7 9 7"/><path d="M5 10v10h14V10"/><path d="M10 20v-6h4v6"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4 21c1-4.5 4.5-6.5 8-6.5s7 2 8 6.5"/>',
    logout: '<path d="M14 4h5v16h-5"/><path d="M10 12h10M6 8l-4 4 4 4"/><path d="M2 12h8"/>',
    globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 2.7 3.8 5.7 3.8 9s-1.3 6.3-3.8 9c-2.5-2.7-3.8-5.7-3.8-9S9.5 5.7 12 3z"/>',
    chevron: '<path d="M6 9l6 6 6-6"/>',
    chat: '<path d="M4 20l1.4-4.2A8 8 0 1 1 8.2 18.6z"/>'
  };
  // Íconos de cultivos dibujados (no emojis: algunos teléfonos no tienen esos emojis y salían vacíos).
  const GOLD = '#D9A62E', STEM = '#7A8F2B', LEAF = '#3E9B4F', POD = '#5DAA3C', BROWN = '#A86F32';
  const ear = (c) => `<path d="M12 22V9" stroke="${STEM}" stroke-width="1.6" stroke-linecap="round"/>
    ${[[12, 4.5, 0], [9.6, 8, -30], [14.4, 8, 30], [9.6, 11.5, -30], [14.4, 11.5, 30], [9.8, 15, -30], [14.2, 15, 30]]
      .map(([x, y, r]) => `<ellipse cx="${x}" cy="${y}" rx="1.7" ry="2.7" transform="rotate(${r} ${x} ${y})" fill="${c}"/>`).join('')}`;
  const pod = (c, seed) => `<path d="M4 17c2-7 8-12 16-13-1 8-6 14-13 16-1.5.4-3.3-1-3-3z" fill="${c}"/>
    <circle cx="9" cy="15" r="1.8" fill="${seed}"/><circle cx="12.5" cy="11.5" r="1.8" fill="${seed}"/><circle cx="16" cy="8" r="1.6" fill="${seed}"/>`;
  const CROP_SVG = {
    alfalfa: `<path d="M12 22V6" stroke="${LEAF}" stroke-width="1.6" stroke-linecap="round"/>
      <ellipse cx="12" cy="5" rx="2.2" ry="3" fill="${LEAF}"/>
      <ellipse cx="8" cy="10" rx="2" ry="3" transform="rotate(-45 8 10)" fill="${LEAF}"/><ellipse cx="16" cy="10" rx="2" ry="3" transform="rotate(45 16 10)" fill="${LEAF}"/>
      <ellipse cx="8" cy="16" rx="2" ry="3" transform="rotate(-45 8 16)" fill="#56B05F"/><ellipse cx="16" cy="16" rx="2" ry="3" transform="rotate(45 16 16)" fill="#56B05F"/>`,
    clover_red: `<path d="M12 13v9" stroke="${LEAF}" stroke-width="1.6" stroke-linecap="round"/>
      <circle cx="12" cy="7.5" r="3.6" fill="${LEAF}"/><circle cx="7.6" cy="12" r="3.6" fill="#56B05F"/><circle cx="16.4" cy="12" r="3.6" fill="#56B05F"/>`,
    wheat: ear(GOLD), barley: ear('#E2B84A'), oat: ear('#CDB66A'), rice: ear('#C9BE8E'), sorghum: ear('#B5752E'),
    maize: `<path d="M6 21c0-6 2-10 5-12" stroke="${LEAF}" stroke-width="2" fill="none" stroke-linecap="round"/>
      <ellipse cx="13.5" cy="10" rx="4" ry="7.5" transform="rotate(20 13.5 10)" fill="#F2C230"/>
      <path d="M18 21c0-5-1.5-8-4-10" stroke="${LEAF}" stroke-width="2" fill="none" stroke-linecap="round"/>
      <path d="M11 6.5l4 1.4M10.3 9.5l4.6 1.6M9.8 12.5l4.4 1.6" stroke="#D9A21B" stroke-width="1" stroke-linecap="round"/>`,
    potato: `<path d="M5 13c-1-5 3-9 8-9 5 .2 7 4 6 8-1 5-5 8-9 7.5-3-.4-4.6-3-5-6.5z" fill="#C08A4A"/>
      <circle cx="9" cy="10" r=".9" fill="#7A5226"/><circle cx="14" cy="8.5" r=".9" fill="#7A5226"/><circle cx="12" cy="14" r=".9" fill="#7A5226"/><circle cx="15.5" cy="13" r=".8" fill="#7A5226"/>`,
    cassava: `<path d="M5 19c3-1 9-6 13-12 1-1.5 2.6-.4 2 1.2C18 13 11 19 6.5 21 5 21.6 3.8 19.6 5 19z" fill="${BROWN}"/>
      <path d="M17 6l1-3M19 7l2.5-1.5" stroke="${LEAF}" stroke-width="1.6" stroke-linecap="round"/>`,
    bean_faba: pod(POD, '#A9D86E'), soybean: pod('#8DBF4A', '#E6D47A'), tarwi: pod('#7FB24A', '#F1EBD0'),
    lentil: `<circle cx="8" cy="9" r="3.3" fill="#C9852F"/><circle cx="15.5" cy="8" r="3.3" fill="#D99A3E"/><circle cx="11.5" cy="15" r="3.3" fill="#B97425"/><circle cx="17" cy="15.5" r="2.8" fill="#C9852F"/>`,
    bean_common: `<path d="M5 11c0-4 3-6 6-5 2 .6 2 2.6 1 3.6-1.2 1.2-1 2.9.6 3.4 2 .6 2.6 3.4.4 5C10 20 5 17 5 11z" fill="#8E4A2E"/>
      <path d="M14 8c2-2.4 6-1.2 6 2.4 0 2.4-2 4-4 3.6-1.7-.3-2-1.3-1.6-2.6.3-1.1-1.4-1.6-.4-3.4z" fill="#A65A36"/>`,
    sunflower: `${[0, 45, 90, 135, 180, 225, 270, 315].map(r => `<ellipse cx="12" cy="5" rx="2" ry="3.4" transform="rotate(${r} 12 12)" fill="#F4C21F"/>`).join('')}
      <circle cx="12" cy="12" r="3.8" fill="#7A4E22"/>`,
    barbecho: `<text x="3" y="20" font-family="Nunito, sans-serif" font-weight="900" font-size="11" fill="#2F6F95">z</text>
      <text x="9" y="14" font-family="Nunito, sans-serif" font-weight="900" font-size="14" fill="#2F6F95">Z</text>`
  };
  function cropIcon(k, size) {
    if (!CROP_SVG[k]) return '';
    const s = size || 28;
    return `<svg class="ci" width="${s}" height="${s}" viewBox="2 2 20 20" aria-hidden="true">${CROP_SVG[k]}</svg>`;
  }
  function icon(name, color, size) {
    return `<svg class="i" width="${size || 22}" height="${size || 22}" viewBox="0 0 24 24" fill="none" stroke="${color || 'currentColor'}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${PATHS[name] || ''}</svg>`;
  }
  // Un dato que el motor no tiene: guion con ícono gris, sin texto de disculpa.
  function unknownMark() { return `<span class="unk" role="img" aria-label="${esc(t('no_value'))}">${icon('unknown', '#8A9A8F', 18)}<span aria-hidden="true">—</span></span>`; }

  function dots(n) {
    return `<div class="dots" aria-hidden="true">${[1, 2, 3].map(i => `<span class="${i <= n ? 'on' : ''}"></span>`).join('')}</div>
      <div class="dots-label">${esc(t('step', { n }))}</div>`;
  }
  function mainButton(label, action, disabled, extra) {
    return `<div class="btn-main">${extra || ''}<button data-act="${action}" ${disabled ? 'disabled' : ''}>${esc(label)}</button></div>`;
  }
  function back(action) { return `<button class="back" data-act="${action}" data-dir="back"><span class="flip">←</span> ${esc(t('back'))}</button>`; }
  function langName() { return (LANGS.find(([code]) => code === state.lang) || [])[1] || state.lang; }
  function langNote() {
    if ((window.MACHINE_TRANSLATED || []).includes(state.lang)) return `<div class="warn small" role="note">${esc(t('mt_note'))}</div>`;
    if (translated()) return '';
    return `<div class="warn" role="note">${esc(t('lang_pending', { lang: langName() }))}</div>`;
  }
  // Lista de idiomas (la misma en la bienvenida, que se abre hacia arriba, y en la hoja de Mi cuenta).
  function langList() {
    return `<ul class="lang-menu" role="listbox" id="lang-menu" aria-label="${esc(t('choose_language'))}">${LANGS.map(([code, name]) =>
      `<li><button role="option" data-lang="${code}" lang="${code}" aria-selected="${state.lang === code}">${esc(name)}
        ${state.lang === code ? icon('check', '#00733A', 20) : ''}</button></li>`).join('')}</ul>`;
  }
  // Lista desplegable propia, como en el prototipo: botón con globo y flecha; el menú se abre hacia arriba.
  function langPicker() {
    return `<div class="lang-dd">${langOpen ? langList() : ''}
      <button class="lang-btn" data-act="lang-toggle" aria-haspopup="listbox" aria-expanded="${langOpen}" aria-controls="lang-menu">
        ${icon('globe', '#00733A', 24)}<span class="nm">${esc(langName())}</span>${icon('chevron', '#00733A', 22).replace('class="i"', 'class="i chev"')}</button></div>`;
  }
  function askTech() {
    return `<div class="warn tech" role="note">${icon('alert', '#10301C')}<strong>${esc(t('ask_tech'))}</strong></div>`;
  }
  // Logo del prototipo: brote de dos hojas sobre dos ondas de tierra, con un punto lima.
  function logo() {
    return `<svg width="96" height="96" viewBox="0 0 96 96" aria-hidden="true">
      <path d="M48 62V34" stroke="#00733A" stroke-width="5" stroke-linecap="round"/>
      <path d="M48 40c-12 0-19-6-19-17 11 0 19 6 19 17z" fill="#00733A"/>
      <path d="M48 36c0-11 7-17 19-17 0 11-7 17-19 17z" fill="#21A159" stroke="#00733A" stroke-width="3"/>
      <circle cx="73" cy="16" r="5" fill="#D8E622"/>
      <path d="M18 70c10-7 20-7 30 0s20 7 30 0" fill="none" stroke="#8CC63F" stroke-width="5" stroke-linecap="round"/>
      <path d="M18 80c10-7 20-7 30 0s20 7 30 0" fill="none" stroke="#21A159" stroke-width="5" stroke-linecap="round"/></svg>`;
  }
  // Botón flotante del asistente: mejora futura, todavía sin funciones. Solo abre un aviso.
  function aiButton() {
    return `<button class="fab-ai" data-act="ai" aria-label="${esc(t('ai_button'))}" aria-haspopup="dialog">${icon('sprout', '#FFFFFF', 28)}</button>`;
  }
  function aiSheet() {
    return `<div class="sheet-bg" data-act="ai-close"></div>
      <div class="sheet" role="dialog" aria-modal="true" aria-labelledby="ai-title">
        <h3 id="ai-title">${esc(t('ai_title'))}</h3><p>${esc(t('ai_soon'))}</p>
        <button class="btn-big" data-act="ai-close">${esc(t('close'))}</button></div>`;
  }
  // Hoja con todos los idiomas ("See more" en Mi cuenta).
  function langSheet() {
    return `<div class="sheet-bg" data-act="lang-close"></div>
      <div class="sheet" role="dialog" aria-modal="true" aria-labelledby="lang-title">
        <h3 id="lang-title">${esc(t('choose_language'))}</h3>${langList()}
        <button class="btn-big" data-act="lang-close" style="margin-top:12px">${esc(t('close'))}</button></div>`;
  }
  // Aviso de montaña: arriba si la diferencia de altitud es grande (más de 500 m), si no después de las rutas.
  function bigGap(p) { return p.terrain.srtm_m != null && p.terrain.merra2_m != null && Math.abs(p.terrain.srtm_m - p.terrain.merra2_m) > 500; }
  function mountain(p) {
    if (!p.terrain.mountain_warning) return '';
    return `<div class="warn" role="note"><strong>${icon('mountain', '#10301C')} ${esc(t('mountain_title'))}</strong>${esc(t('mountain', { srtm: p.terrain.srtm_m ?? '—', merra: p.terrain.merra2_m ?? '—' }))}</div>`;
  }
  const GRAIN = ['maize', 'wheat', 'barley', 'oat', 'sorghum', 'rice'], TUBER = ['potato', 'cassava'];
  function cropTile(k, big) {
    const tone = GRAIN.includes(k) ? ' grain' : TUBER.includes(k) ? ' tuber' : '';
    return `<span class="crop${big ? ' big' : ''}"><span class="em${tone}" aria-hidden="true">${cropIcon(k, big ? 46 : 38)}</span><span class="nm">${esc(cap(cropName(k)))}</span></span>`;
  }
  function strip(seq) { return `<div class="seq">${seq.map(k => cropTile(k)).join('<span class="arrow" aria-hidden="true">→</span>')}</div>`; }
  function altitudes(p) {
    const farm = p.terrain.srtm_m, cell = p.terrain.merra2_m;
    return `${farm != null ? esc(t('alt_farm', { m: farm })) : ''}${farm != null && cell != null ? ' · ' : ''}${cell != null ? esc(t('alt_cell', { m: cell })) : ''}`;
  }

  // Barra horizontal con su número escrito al lado. 0 a 100 salvo que se indique otro máximo.
  function hbar(label, value, color, opts) {
    const o = opts || {}, max = o.max || 100;
    const num = value == null ? unknownMark() : `<b class="num">${esc(Math.round(value))}${o.unit ? ' ' + esc(o.unit) : ''}</b>`;
    const width = value == null ? 0 : Math.max(2, Math.min(100, (value / max) * 100));
    return `<div class="hbar${o.small ? ' sm' : ''}"><span class="lbl">${o.icon ? icon(o.icon, o.iconColor || '#10301C') : ''}${esc(label)}</span>
      <span class="track">${value == null ? '' : `<i style="width:${width}%;background:${color}"></i>`}</span>${num}</div>`;
  }

  // La rotación es un ciclo: si el agricultor sembró este año una familia, empezamos por otra.
  function orderedSequence(p, route) {
    const last = state.history[0];
    const fam = k => (k === FALLOW ? null : (crop(p, k) || {}).family);
    const lastFam = last ? (crop(p, last) || {}).family : null;
    const seq = route.sequence;
    for (let k = 0; k < seq.length; k++) {
      const s = seq.slice(k).concat(seq.slice(0, k));
      if (!last || (s[0] !== last && fam(s[0]) !== lastFam)) return s;
    }
    return seq;
  }

  // "Para ti": la mejor en la prioridad elegida entre las rutas de tres cultivos. Las rutas con descanso
  // promedian solo dos cultivos y ganarían por eso; solo cuentan si no hay ninguna de tres.
  function forYou(p) {
    const axis = CARE_AXIS[state.care];
    const three = p.routes.some(r => r.kind === 'tres_cultivos');
    let best = -1, value = -Infinity;
    p.routes.forEach((r, i) => {
      if (three && r.kind !== 'tres_cultivos') return;
      if (r[axis] != null && r[axis] > value) { value = r[axis]; best = i; }
    });
    return best;
  }

  // ---------- pantallas ----------
  function home() {
    const offline = navigator.serviceWorker && navigator.serviceWorker.controller;
    return `<section class="welcome">
      ${offline ? `<span class="badge-offline">${icon('check', '#00733A', 18)} ${esc(t('works_offline'))}</span>` : ''}
      <div class="logo-wrap" ${offline ? '' : 'style="margin-top:110px"'}>${logo()}</div>
      <h1>${esc(t('app_name'))}</h1>
      <p class="tagline">${esc(t('tagline'))}</p>
    </section>${mainButton(t('start'), 'start', false,
      `${langNote()}<p class="lang-label">${icon('chat', '#4A6354', 18)} ${esc(t('choose_language'))}</p>${langPicker()}`)}`;
  }

  function where() {
    const list = DATA.pilots.map(p => `<button class="place" data-pilot="${esc(p.id)}" aria-pressed="${state.pilot === p.id}">
        <span class="pin">${icon('pin', '#00733A', 24)}</span><span><strong>${esc(p.label)}</strong>
        <span class="alt">${altitudes(p)}</span></span></button>`).join('');
    return `${back('to-home')}${dots(1)}
      <h2>${esc(t('q_where'))}</h2>
      <p class="soft">${esc(t('where_help'))}</p>
      <div id="map" class="map" aria-label="${esc(t('map_label'))}"></div>
      <div id="confirm"></div>
      <button class="btn-dash" data-act="gps">${icon('locate', '#00733A')} ${esc(t('use_gps'))}</button>
      <p class="small soft" style="margin:8px 0 4px">${esc(t('gps_why'))}</p>
      <p id="gps-msg" class="small" role="status"></p>
      <h3 class="sub">${esc(t('places_title'))}</h3>
      ${list}
      ${mainButton(t('next'), 'to-what', !state.pilot)}`;
  }

  function what() {
    const p = pilot();
    const keys = p.crops.map(c => c.key);
    const years = [0, 1, 2].map(y => `<h3 class="sub">${esc(t('year_' + y))}</h3>
      <label class="pick"><select data-year="${y}" aria-label="${esc(t('year_' + y))}">
        <option value=""${state.history[y] ? '' : ' selected'}>${esc(t('select_placeholder'))}</option>
        <option value="">${esc(t('dont_know'))}</option>
        ${keys.map(k => `<option value="${k}"${state.history[y] === k ? ' selected' : ''}>${esc(cap(cropName(k)))}</option>`).join('')}
      </select>${icon('chevron', '#00733A', 22)}</label>`).join('');
    return `${back('to-where')}${dots(2)}
      <h2>${esc(t('q_what'))}</h2>
      <p class="soft">${esc(t('what_help'))}</p>
      ${years}
      ${mainButton(t('next'), 'to-care')}`;
  }

  function care() {
    const opts = [['water', 'drop', '#1E8F6A', '#D7EEE6'], ['soil', 'sprout', '#21A159', '#E3F2DA'], ['safe', 'shield', '#5E6B12', '#F1F4C2']].map(([k, ico, color, bg]) => `
      <button class="option" data-care="${k}" aria-pressed="${state.care === k}">
        <span class="sq" style="background:${bg}">${icon(ico, color, 26)}</span>
        <span class="txt"><strong>${esc(t('care_' + k))}</strong><span>${esc(t('care_' + k + '_sub'))}</span></span>
        ${state.care === k ? `<span class="ok">${icon('check', '#00733A', 22)}</span>` : ''}
      </button>`).join('');
    return `${back('to-what')}${dots(3)}
      <h2>${esc(t('q_care'))}</h2>
      ${opts}
      ${mainButton(t('see_routes'), 'to-routes', !state.care)}`;
  }

  // La rotación que el agricultor ya siembra: sus cultivos del paso 2, del más antiguo al de este año,
  // puntuada con las mismas reglas del motor (src/rotation_scores.py: rotation, soil_score, families_ok).
  function myCrops() {
    const seq = [state.history[2], state.history[1], state.history[0]].filter(Boolean);
    return seq.filter((k, i) => seq.indexOf(k) === i);
  }
  function soilScore(p, seq) {          // = soil_score: leguminosa 40, 20 por cambio de familia, cobertura 20; tope 100
    const cs = seq.map(k => crop(p, k));
    let score = cs.some(c => c.legume) ? 40 : 0;
    for (let i = 1; i < cs.length; i++) if (cs[i].family !== cs[i - 1].family) score += 20;
    if (cs.some(c => c.cover)) score += 20;
    return Math.min(100, score);
  }
  function familiesOk(fams) {            // = families_ok: sin familia repetida seguida, contando la vuelta
    const cropped = fams.filter(f => f != null);
    if (cropped.length < 2) return true;
    const ring = fams.concat(fams.slice(0, 1)), pairs = [];
    for (let i = 0; i < ring.length - 1; i++) if (ring[i] != null && ring[i + 1] != null) pairs.push([ring[i], ring[i + 1]]);
    if (fams.includes(null)) pairs.push(cropped);
    return pairs.every(([a, b]) => a !== b);
  }
  function myRotation(p) {
    const keys = myCrops();
    if (!keys.length) return null;
    const cs = keys.map(k => crop(p, k));
    const seq = keys.length === 1 ? [keys[0], keys[0], keys[0]] : keys;   // un solo cultivo = el mismo tres campañas
    const mean = vals => vals.some(v => v == null) ? null : vals.reduce((a, b) => a + b, 0) / vals.length;
    const same = [];
    for (let i = 0; i < seq.length; i++) {
      const a = seq[i], b = seq[(i + 1) % seq.length];
      if (a !== b && crop(p, a).family === crop(p, b).family && !same.some(x => x.includes(a) && x.includes(b))) same.push([a, b]);
    }
    return { keys, seq, water: mean(cs.map(c => c.water)), risk: mean(cs.map(c => c.risk)), soil: soilScore(p, seq),
      ok: familiesOk(seq.map(k => crop(p, k).family)), same, repeated: keys.length === 1,
      noFrost: cs.filter(c => !c.frost_evaluable), excluded: cs.filter(c => c.state === 'excluded') };
  }
  function shared(r) { const mine = myCrops(); return r.sequence.filter(k => mine.includes(k)); }
  function myCard(p, m) {
    const notes = [];
    if (m.repeated) notes.push(['cycle', t('mine_repeat', { crop: cropName(m.keys[0]), Crop: cap(cropName(m.keys[0])) })]);
    m.same.forEach(([a, b]) => notes.push(['cycle', t('mine_family', { a: cap(cropName(a)), b: cropName(b) })]));
    m.excluded.forEach(c => notes.push(['alert', t('mine_excluded', { crop: cap(cropName(c.key)), why: listJoin((c.failed || []).map(f => t('fail_' + f))) })]));
    if (m.noFrost.length) notes.push(['unknown', t('mine_no_frost', { crops: listJoin(m.noFrost.map(c => cropName(c.key))) })]);
    if (!notes.length) notes.push(['check', t('mine_ok')]);
    return `<article class="card tint route mine"><h3>${esc(t('mine_title'))}</h3>
      ${m.keys.length === 1 ? `<div class="seq one">${cropTile(m.keys[0], true)}</div>` : strip(m.keys)}
      ${axisBars(m)}
      <ul class="notes">${notes.map(([i, s]) => `<li>${icon(i, i === 'unknown' ? '#8A9A8F' : '#3F5A48', 20)}<span>${esc(s)}</span></li>`).join('')}</ul></article>`;
  }
  // Las tres barras de una ruta: Agua, Tierra, Cosecha segura (ícono escudo en oliva).
  function axisBars(r) {
    return AXES.map(([a, l, ico, color]) => hbar(t(l), r[a], color, { icon: ico, iconColor: ico === 'shield' ? '#5E6B12' : color, small: true })).join('');
  }

  function routes() {
    const p = pilot();
    const mine = forYou(p), m = myRotation(p);
    let body;
    if (!p.routes.length) body = `<div class="warn" role="note">${icon('alert', '#10301C')} ${esc(t('routes_none'))}</div>`;
    else {
      // Primero las rutas que llevan cultivos que ya siembra; el número de cada ruta no cambia.
      const order = p.routes.map((r, i) => i).sort((a, b) => shared(p.routes[b]).length - shared(p.routes[a]).length || a - b);
      body = order.map(i => {
        const r = p.routes[i], common = shared(r);
        const seq = orderedSequence(p, r);
        const irrigation = r.water != null && r.water < 40 ? `<div class="needs">${icon('drop', '#10301C', 18)} ${esc(t('needs_irrigation'))}</div>` : '';
        return `<article class="card route${i === mine ? ' best' : ''}" data-route="${i}" tabindex="0" role="button">
          ${i === mine ? `<span class="tag">★ ${esc(t('for_you'))}</span>` : ''}
          <h3>${esc(t('route_n', { n: i + 1 }))}</h3>
          ${common.length ? `<div class="common">${icon('check', '#00733A', 18)} ${esc(t('route_has', { crops: listJoin(common.map(cropName)) }))}</div>` : ''}
          <div class="kind">${esc(t(r.kind === 'con_descanso' ? 'kind_rest' : 'kind_three'))}</div>
          ${strip(seq)}
          ${axisBars(r)}${irrigation}
          <div class="see">${esc(t('why_link'))} <span class="flip">→</span></div>
        </article>`;
      }).join('');
      if (p.routes.length < 3) body = `<p class="soft small">${esc(t(p.routes.length === 1 ? 'routes_few_1' : 'routes_few', { n: p.routes.length }))}</p>` + body;
    }
    const intro = m && p.routes.length ? `<h3 class="section">${esc(t('recommended_title'))}</h3>
      ${p.routes.some(r => shared(r).length) ? '' : `<p class="small soft">${esc(t('recommended_none_common'))}</p>`}` : '';
    const top = bigGap(p);
    return `${back('to-care')}
      <h2>${esc(t('routes_title', { place: p.label }))}</h2>
      ${top ? mountain(p) : ''}${m ? myCard(p, m) : ''}${intro}${body}
      ${top ? '' : mountain(p)}
      ${p.routes.length ? compare(p) : ''}
      <button class="btn-line" data-act="restart" style="margin-top:8px">${esc(t('restart'))}</button>`;
  }

  // Barras horizontales agrupadas: Agua, Tierra, Cosecha segura; una barra por ruta y una gris para hoy.
  function compare(p) {
    const todayVals = myRotation(p);
    const groups = AXES.map(([a, l, ico, color]) => `<div class="group"><h4>${icon(ico, ico === 'shield' ? '#5E6B12' : color)} ${esc(t(l))}</h4>
      ${p.routes.map((r, i) => hbar(t('route_n', { n: i + 1 }), r[a], color)).join('')}
      ${todayVals ? hbar(t('today_bar'), todayVals[a], TODAY_GRAY) : ''}</div>`).join('');
    return `<section class="card"><h3>${esc(t('compare_title'))}</h3>
      <p class="small soft">${esc(t('compare_help'))}</p>${groups}
      ${todayVals ? '' : `<p class="small soft">${esc(t('compare_no_today'))}</p>`}</section>`;
  }

  // ---------- ¿Por qué esta ruta? ----------
  function reasons(p, r) {
    const crops = r.sequence.filter(k => k !== FALLOW).map(k => crop(p, k));
    const out = [];
    const legume = crops.find(c => c.legume);
    if (legume) out.push(['sprout', t('r_legume', { crop: cropName(legume.key) })]);
    else if (r.sequence.includes(FALLOW)) out.push(['rest', t('r_rest')]);
    else out.push(['cycle', t('r_family')]);
    const known = crops.filter(c => c.demand_mm != null && c.rain_mm != null);
    if (known.length) {
      const worst = known.reduce((a, b) => ((b.deficit_mm || 0) > (a.deficit_mm || 0) ? b : a));
      if ((worst.deficit_mm || 0) > 0.1 * worst.demand_mm)
        out.push(['drop', t('r_water_gap', { crop: cropName(worst.key), mm: Math.round(worst.deficit_mm) })]);
      else out.push(['drop', t(known.some(c => (c.deficit_mm || 0) > 0) ? 'r_water_near' : 'r_water_ok', { crop: listJoin(known.map(c => cropName(c.key))) })]);
    }
    const evaluable = crops.filter(c => c.frost_evaluable && c.frost_days != null);
    if (evaluable.length === crops.length && evaluable.every(c => c.frost_days < 0.5)) out.push(['snow', t('r_frost_none')]);
    else {
      const frosty = evaluable.filter(c => c.frost_days >= 0.5).sort((a, b) => b.frost_days - a.frost_days)[0];
      if (frosty) out.push(['snow', t('r_frost_some', { crop: cap(cropName(frosty.key)), d: Math.round(frosty.frost_days) })]);
    }
    const dry = crops.filter(c => c.drought_share != null).sort((a, b) => b.drought_share - a.drought_share)[0];
    if (out.length < 3 && dry && dry.drought_share > 0) out.push(['sun', t('r_dry', { pct: Math.round(dry.drought_share * 100) })]);
    return out.slice(0, 3);
  }

  function frostChart(p) {
    const vals = p.monthly.map(m => m.frost_days);
    if (vals.every(v => v == null || v < 0.05)) return `<p>${esc(t('frost_none'))}</p>`;
    const max = Math.max(...vals.map(v => v || 0), 1);
    const scale = ['var(--frost-0)', 'var(--frost-1)', 'var(--frost-2)', 'var(--frost-3)', 'var(--frost-4)'];
    const W = 336, H = 170, bw = 22, gap = 6, base = 140;
    const bars = vals.map((v, i) => {
      const h = v == null ? 0 : Math.max(2, (v / max) * 110);
      const color = scale[Math.min(4, Math.ceil(((v || 0) / max) * 4))];
      const x = 6 + i * (bw + gap);
      return `<rect x="${x}" y="${base - h}" width="${bw}" height="${h}" rx="4" fill="${color}"/>
        <text x="${x + bw / 2}" y="${base - h - 4}" text-anchor="middle" font-size="12" fill="#10301C">${v == null ? '—' : Math.round(v)}</text>
        <text x="${x + bw / 2}" y="${base + 16}" text-anchor="middle" font-size="12" fill="#3F5A48">${esc(t('months_short')[i])}</text>`;
    }).join('');
    return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(t('frost_chart'))}">${bars}</svg>`;
  }

  function waterChart(p, r) {
    const crops = r.sequence.filter(k => k !== FALLOW).map(k => crop(p, k));
    const max = Math.max(1, ...crops.map(c => Math.max(c.rain_mm || 0, c.demand_mm || 0)));
    const rows = crops.map(c => `<div class="water-crop"><strong>${cropIcon(c.key, 26)} ${esc(cap(cropName(c.key)))}</strong>
        ${hbar(t('rain'), c.rain_mm, 'var(--route-water)', { max, unit: 'mm', small: true })}
        ${hbar(t('demand'), c.demand_mm, 'var(--thirst)', { max, unit: 'mm', small: true })}</div>`).join('');
    return `<div class="legend"><span><i style="background:var(--route-water)"></i>${esc(t('rain'))}</span><span><i style="background:var(--thirst)"></i>${esc(t('demand'))}</span></div>${rows}`;
  }

  function why() {
    const p = pilot(), r = p.routes[state.route];
    const bt = p.backtest && p.backtest.routes ? p.backtest.routes.find(b => b.sequence.slice().sort().join() === r.sequence.slice().sort().join()) : null;
    const btLine = bt && bt.route_deficit_mm != null && bt.typical_deficit_mm != null
      ? `<p class="small fact">${icon('chart', '#3F5A48', 18)} ${esc(t('r_backtest', { n: p.backtest.test_years[1] - p.backtest.test_years[0] + 1, r: Math.round(bt.route_deficit_mm), crop: cropName(p.backtest.typical), m: Math.round(bt.typical_deficit_mm) }))}</p>` : '';
    return `${back('to-routes')}
      <h2>${esc(t('why_title'))}</h2>
      ${strip(orderedSequence(p, r))}
      <section class="card"><ul class="reasons">${reasons(p, r).map(([i, s]) => `<li><span class="ico">${icon(i, '#00733A', 26)}</span><span>${esc(s)}</span></li>`).join('')}</ul></section>
      <h3 class="section">${esc(t('evidence'))}</h3>
      <section class="card"><h3>${icon('snow', '#2F6F95')} ${esc(t('frost_chart'))}</h3>${frostChart(p)}</section>
      <section class="card"><h3>${icon('drop', '#1E8F6A')} ${esc(t('water_chart'))}</h3>${waterChart(p, r)}${btLine}</section>
      ${askTech()}
      ${mainButton(t('when'), 'to-calendar')}`;
  }

  // ---------- Calendario ----------
  function calendar() {
    const p = pilot(), r = p.routes[state.route];
    const seq = orderedSequence(p, r);
    const k = seq[state.campaign] || seq[0];
    const tabs = `<div class="chips" role="group">${seq.map((s, i) => `<button class="chip" data-campaign="${i}" aria-pressed="${state.campaign === i}">
      ${cropIcon(s, 26)} ${esc(t('campaign_n', { n: i + 1 }))}: ${esc(cropName(s))}</button>`).join('')}</div>`;
    let main, grid = '';
    const frostMonths = new Set(p.monthly.filter(m => (m.frost_days || 0) >= 0.5).map(m => m.month));
    if (k === FALLOW) main = `<div class="plant-card"><h2>${esc(t('rest_season'))}</h2></div>`;
    else {
      const c = crop(p, k), months = c.months || [];
      main = `<div class="plant-card"><h2>${esc(t('sow', { crop: cropName(k), month: monthName(months[0]) }))}</h2>
        <p>${esc(t('harvest', { crop: cropName(k), month: monthName(months[months.length - 1]) }))}</p></div>`;
      grid = `<div class="cal" role="img" aria-label="${esc(t('cal_title'))}">${t('months').map((m, i) => {
        const mo = i + 1, grow = months.includes(mo), sow = mo === months[0];
        return `<div class="${grow ? 'grow' : ''} ${sow ? 'sow' : ''}">${esc(cap(m))}${sow ? `<small>${esc(cap(cropName(k)))}</small>` : ''}${frostMonths.has(mo) ? `<small class="fr">${icon('snow', '#2F6F95', 14)} ${esc(t('frost_word'))}</small>` : ''}</div>`;
      }).join('')}</div>`;
    }
    return `${back('to-why')}
      <h3 class="sub" style="margin-top:6px">${esc(t('cal_title'))}</h3>${tabs}
      ${main}${grid}
      <ul class="facts"><li>${icon('snow', '#2F6F95')}<span>${esc(firstFrostText(p))}</span></li>
</ul>
      ${mountain(p)}
      <button class="btn-line" data-act="choose-route">${icon('check', '#00733A')} ${esc(t('choose_route'))}</button>
      <p id="remind-msg" class="small" role="status"></p>
      ${k === FALLOW ? '' : mainButton(t('remind'), 'remind')}`;
  }
  function firstFrostText(p) {
    const ff = p.first_frost;
    return ff && ff.month ? t('first_frost', { day: ff.day, month: monthName(ff.month), n: ff.years_with_frost, t: ff.seasons }) : t('no_first_frost');
  }
  function remind() {
    const p = pilot(), seq = orderedSequence(p, p.routes[state.route]);
    const k = seq[state.campaign] || seq[0];
    const c = crop(p, k);
    if (!c || !c.months) return;
    const now = today();
    let year = now.getFullYear();
    if (c.months[0] - 1 < now.getMonth()) year += 1;
    const d = `${year}${String(c.months[0]).padStart(2, '0')}01`;
    const ics = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Terrapath//ES', 'BEGIN:VEVENT',
      `UID:${p.id}-${k}-${d}@terrapath`, `DTSTAMP:${new Date().toISOString().replace(/[-:]/g, '').slice(0, 15)}Z`,
      `DTSTART;VALUE=DATE:${d}`, `SUMMARY:${t('sow', { crop: cropName(k), month: monthName(c.months[0]) })}`,
      `DESCRIPTION:${t('ask_tech')}`, 'BEGIN:VALARM', 'TRIGGER:-P7D', 'ACTION:DISPLAY', `DESCRIPTION:${cap(cropName(k))}`,
      'END:VALARM', 'END:VEVENT', 'END:VCALENDAR'].join('\r\n');
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([ics], { type: 'text/calendar' }));
    a.download = `plant-${k}.ics`;
    document.body.appendChild(a); a.click(); a.remove();
    document.getElementById('remind-msg').textContent = t('remind_done');
  }

  // ---------- Mi chacra ----------
  // Las campañas se encadenan desde el mes en que eligió la rotación: cada cultivo en sus meses
  // (los del motor), el descanso dura una campaña de 12 meses.
  function schedule(p, farm) {
    const start = parseDay(farm.start) || today();
    let cursor = new Date(start.getFullYear(), start.getMonth(), 1);
    return farm.seq.map(k => {
      const c = crop(p, k), months = k === FALLOW || !c ? null : c.months;
      let s, e;
      if (!months) { s = cursor; e = addMonths(cursor, 12); }
      else {
        s = new Date(cursor.getFullYear(), months[0] - 1, 1);
        if (s < cursor) s = new Date(s.getFullYear() + 1, s.getMonth(), 1);
        e = addMonths(s, months.length);
      }
      cursor = e;
      return { key: k, crop: c, s, e, fallow: !months };
    });
  }
  function status(c, now) {
    if (now < c.s) return 'wait';
    if (now >= c.e) return 'done';
    if (c.fallow) return 'rest';
    return now.getFullYear() === c.s.getFullYear() && now.getMonth() === c.s.getMonth() ? 'sown' : 'grow';
  }
  function sameMonth(a, b) { return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth(); }
  function lastMonth(c) { return addMonths(c.e, -1); }
  function normals(p, days) {
    const d = p.daily || {}, idx = days.map(dayIndex);
    const pick = arr => idx.map(i => (arr || [])[i]);
    const sum = vals => vals.some(v => v == null) ? null : vals.reduce((a, b) => a + b, 0);
    const rain = pick(d.rain_mm), tmin = pick(d.t_min_c), et0 = pick(d.et0_mm), frost = pick(d.frost_share);
    return { rain: sum(rain), et0: sum(et0), tmin: tmin.some(v => v == null) ? null : Math.min(...tmin),
      frost: frost.some(v => v == null) ? null : Math.max(...frost),
      days: idx.map((i, n) => ({ rain: rain[n], frost: frost[n], tmin: tmin[n] })) };
  }

  function farm() {
    const p = pilot(), f = state.farm;
    const plan = schedule(p, f), now = today();
    const start = parseDay(f.start) || now;
    const tabs = `<div class="seg three" role="tablist">${TABS.map(k => `<button role="tab" data-tab="${k}" aria-selected="${state.tab === k}">${esc(t('tab_' + k))}</button>`).join('')}</div>`;
    const body = state.tab === 'month' ? farmMonth(p, plan, now) : state.tab === 'year' ? farmYear(p, plan, now) : farmWeek(p, plan, now);
    return `<h2>${esc(t('farm_title'))}</h2>
      <p class="place-line">${icon('pin', '#00733A', 18)} ${esc(p.label)} · ${altitudes(p)}<br>${esc(t('farm_since', { month: monthName(start.getMonth() + 1), year: start.getFullYear() }))}</p>
      ${strip(f.seq)}
      ${tabs}<div class="tab-body swap">${body}</div>
      ${askTech()}`;
  }

  function weekTasks(p, plan, now) {
    const n = normals(p, [0, 1, 2, 3, 4, 5, 6].map(i => addDays(now, i)));
    const cur = plan.find(c => status(c, now) !== 'wait' && status(c, now) !== 'done');
    const next = plan.find(c => status(c, now) === 'wait');
    const tasks = [];
    if (cur && cur.fallow) tasks.push(['rest', t('task_rest')]);
    else if (cur) {
      const name = cropName(cur.key);
      if (sameMonth(now, cur.s)) tasks.push(['sprout', t('task_sow', { crop: name })]);
      else if (sameMonth(now, lastMonth(cur))) tasks.push(['leaf', t('task_harvest', { crop: name })]);
      else tasks.push(['sprout', t('task_grow', { crop: cap(name) })]);
      const kc = cur.crop && cur.crop.kc_mid;
      if (kc != null && n.et0 != null && n.rain != null) {
        const need = kc * n.et0;
        tasks.push(['drop', n.rain < need ? t('task_water', { crop: name, rain: Math.round(n.rain), need: Math.round(need) }) : t('task_rain_ok', { crop: name })]);
      }
      if (n.frost != null && n.frost >= 0.1) tasks.push(['snow', t('task_frost', { n: Math.round(n.frost * 10) })]);
    } else if (next && !next.fallow) tasks.push(['calendar', t('task_prepare', { crop: cropName(next.key), month: monthName(next.s.getMonth() + 1) })]);
    else if (!next) tasks.push(['check', t('task_done')]);
    return { n, tasks, cur, next };
  }
  function taskList(tasks) {
    return `<ul class="reasons">${tasks.map(([i, s]) => `<li><span class="ico">${icon(i, '#00733A', 26)}</span><span>${esc(s)}</span></li>`).join('')}</ul>`;
  }
  function weekStats(n) {
    return `<div class="stat">${icon('drop', '#1E8F6A', 26)}<span>${esc(t('week_rain'))}</span>${n.rain == null ? unknownMark() : `<b>${esc(round(n.rain, 0))} mm</b>`}</div>
        <div class="stat">${icon('thermo', '#2F6F95', 26)}<span>${esc(t('week_tmin'))}</span>${n.tmin == null ? unknownMark() : `<b>${esc(round(n.tmin, 0))} °C</b>`}</div>`;
  }
  // Siete días desde hoy, cada uno con su lluvia y su mínima de un año normal; copo si heló en 3 de 10 años o más.
  function dayByDay(n, now) {
    const cards = n.days.map((d, i) => {
      const day = addDays(now, i), fr = d.frost != null && d.frost >= 0.3;
      return `<div class="wk-day"><strong>${esc(t('weekday_names')[day.getDay()])} ${day.getDate()}</strong>
        <span>${icon('drop', '#1E8F6A', 16)} ${d.rain == null ? '—' : esc(round(d.rain, 1)) + ' mm'}</span>
        <span>${icon('thermo', '#2F6F95', 16)} ${d.tmin == null ? '—' : esc(round(d.tmin, 0)) + ' °C'}</span>
        ${fr ? `<span class="fz">${icon('snow', '#2F6F95', 16)} ${esc(t('frost_word'))}</span>` : ''}</div>`;
    }).join('');
    return `<section class="card"><h3>${icon('calendar', '#00733A')} ${esc(t('day_by_day'))}</h3>
      <div class="wk-days">${cards}</div></section>`;
  }
  function farmWeek(p, plan, now) {
    const { n, tasks } = weekTasks(p, plan, now);
    return `<section class="card"><h3>${esc(t('todo'))}</h3>
        ${taskList(tasks)}</section>
      <section class="card">${weekStats(n)}
        <p class="small soft">${esc(t('normal_year'))}</p></section>
      ${dayByDay(n, now)}`;
  }

  // Este mes como un calendario: cada día con su lluvia normal (color + número) y un copo si suele helar.
  const RAIN_STEPS = ['#E6F3EE', '#C3E4D5', '#93CDB4', '#56AE8C', '#1E8F6A'];
  function farmMonth(p, plan, now) {
    const first = new Date(now.getFullYear(), now.getMonth(), 1);
    const count = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate();
    const days = Array.from({ length: count }, (_, i) => addDays(first, i));
    const n = normals(p, days);
    const known = n.days.map(d => d.rain).filter(v => v != null);
    const max = Math.max(0.1, ...known);
    const step = v => v == null ? -1 : Math.min(4, Math.floor((v / max) * 4.999));
    const windows = [];
    plan.forEach(c => {
      if (c.fallow) return;
      if (sameMonth(first, c.s)) windows.push(['sprout', t('window_sow', { crop: cropName(c.key) })]);
      if (sameMonth(first, lastMonth(c))) windows.push(['leaf', t('window_harvest', { crop: cropName(c.key) })]);
    });
    const FROST_USUAL = 0.5;   // suele helar = heló en la mitad de los años o más
    const frosty = n.days.filter(d => d.frost != null && d.frost >= FROST_USUAL).length;
    const wet = n.days.map((d, i) => ({ v: d.rain, day: i + 1 })).filter(d => d.v != null).sort((a, b) => b.v - a.v).slice(0, 3).map(d => d.day).sort((a, b) => a - b);
    const lead = (first.getDay() + 6) % 7;      // la semana empieza el lunes
    const cells = Array.from({ length: lead }, () => '<div class="cd empty" aria-hidden="true"></div>').concat(days.map((d, i) => {
      const v = n.days[i], k = step(v.rain), fr = v.frost != null && v.frost >= FROST_USUAL;
      const label = `${d.getDate()}: ${v.rain == null ? t('no_value') : round(v.rain, 1) + ' mm'}${fr ? ', ' + t('frost_n10', { n: Math.round(v.frost * 10) }) : ''}`;
      return `<div class="cd${k >= 3 ? ' dark' : ''}${d.getDate() === now.getDate() ? ' now' : ''}" style="background:${k < 0 ? '#FFFFFF' : RAIN_STEPS[k]}" role="img" aria-label="${esc(label)}">
        <span class="dn">${d.getDate()}</span>${fr ? `<span class="fz">${icon('snow', k >= 3 ? '#FFFFFF' : '#2F6F95', 14)}</span>` : ''}
        <b>${v.rain == null ? '—' : esc(round(v.rain, 1))}</b></div>`;
    })).join('');
    const total = n.days.some(d => d.rain == null) ? null : n.days.reduce((a, d) => a + d.rain, 0);
    return `${windows.map(([i, s]) => `<div class="window">${icon(i, '#00733A')} ${esc(s)}</div>`).join('')}
      <section class="card"><h3>${icon('drop', '#1E8F6A')} ${esc(t('month_rain'))} · ${esc(cap(monthName(now.getMonth() + 1)))}</h3>
        <div class="stat">${icon('drop', '#1E8F6A', 26)}<span>${esc(t('month_total'))}</span>${total == null ? unknownMark() : `<b>${esc(round(total, 0))} mm</b>`}</div>
        <div class="stat">${icon('snow', '#2F6F95', 26)}<span>${esc(t('month_frost_days'))}</span><b>${frosty}</b></div>
        ${wet.length ? `<p class="small">${esc(t('month_wettest', { days: listJoin(wet.map(String)) }))}</p>` : ''}
        <div class="cal-month" aria-label="${esc(t('month_rain'))}">
          ${t('weekdays').map(w => `<div class="wd" aria-hidden="true">${esc(w)}</div>`).join('')}${cells}</div>
        <div class="legend rain-legend"><span>${esc(t('less_rain'))}</span>${RAIN_STEPS.map(c => `<i style="background:${c}"></i>`).join('')}<span>${esc(t('more_rain'))}</span>
          <span class="fr-key">${icon('snow', '#2F6F95', 16)} ${esc(t('may_frost'))}</span></div>
        <p class="small soft">${esc(t('normal_year'))} ${esc(t('mm_per_day'))}</p></section>`;
  }

  function farmYear(p, plan, now) {
    const items = plan.map((c, i) => {
      const st = status(c, now);
      const label = st === 'done' && c.fallow ? 'status_rest' : 'status_' + st;
      const last = lastMonth(c);
      const marks = c.fallow
        ? `<li>${icon('rest', '#3F5A48', 18)} ${esc(cap(monthName(c.s.getMonth() + 1)))} ${c.s.getFullYear()} – ${esc(monthName(last.getMonth() + 1))} ${last.getFullYear()}</li>`
        : `<li>${icon('sprout', '#00733A', 18)} ${esc(t('milestone_sow', { month: cap(monthName(c.s.getMonth() + 1)), year: c.s.getFullYear() }))}</li>
           <li>${icon('leaf', '#5E6E1F', 18)} ${esc(t('milestone_harvest', { month: cap(monthName(last.getMonth() + 1)), year: last.getFullYear() }))}</li>`;
      return `<li class="step ${st}"><span class="node" aria-hidden="true"></span><div>
        <div class="step-head"><strong>${esc(t('campaign_n', { n: i + 1 }))}: ${cropIcon(c.key, 26)} ${esc(cap(cropName(c.key)))}</strong>
        <span class="pill ${st}">${esc(t(label))}</span></div><ul class="marks">${marks}</ul></div></li>`;
    }).join('');
    return `<section class="card"><ol class="timeline">${items}</ol></section>
      <ul class="facts"><li>${icon('snow', '#2F6F95')}<span>${esc(firstFrostText(p))}</span></li></ul>${mountain(p)}`;
  }

  // ---------- Mapa (Leaflet + OpenStreetMap) ----------
  let map = null, marker = null, pending = null;
  function pinIcon() {
    return window.L.divIcon({ className: 'pin-icon', iconSize: [44, 44], iconAnchor: [22, 42],
      html: `<svg width="44" height="44" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 22s-7-6.6-7-12a7 7 0 0 1 14 0c0 5.4-7 12-7 12z" fill="#00733A" stroke="#FFFFFF" stroke-width="1.5"/><circle cx="12" cy="10" r="2.6" fill="#FFFFFF"/></svg>` });
  }
  function initMap() {
    const el = document.getElementById('map');
    if (!el) return;
    if (!window.L) { el.remove(); return; }
    const p = pilot(), c = state.farmPoint || (p ? { latitude: p.latitude, longitude: p.longitude } : DATA.pilots[0]);
    try {
      map = window.L.map(el, { minZoom: 10, maxZoom: 16, zoomControl: true });
      map.attributionControl.setPrefix(false);
      let loaded = false, gone = false;
      const layer = window.L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        minZoom: 10, maxZoom: 16, attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' });
      layer.on('tileload', () => { loaded = true; });
      // Si el mapa no carga (sin señal), queda solo la lista, sin mensaje de error.
      layer.on('tileerror', () => { if (!loaded && !gone) { gone = true; dropMap(); } });
      layer.addTo(map);
      map.setView([c.latitude, c.longitude], 12);
      if (state.farmPoint) marker = window.L.marker([c.latitude, c.longitude], { icon: pinIcon(), keyboard: false }).addTo(map);
      map.on('click', e => place({ latitude: e.latlng.lat, longitude: e.latlng.lng }));
    } catch (e) { dropMap(); }
  }
  function dropMap() {
    if (map) { try { map.remove(); } catch (e) { /* ya no está */ } }
    map = null; marker = null;
    const el = document.getElementById('map'); if (el) el.remove();
  }
  function place(pt) {
    pending = pt;
    if (map) {
      if (marker) marker.setLatLng([pt.latitude, pt.longitude]);
      else marker = window.L.marker([pt.latitude, pt.longitude], { icon: pinIcon(), keyboard: false }).addTo(map);
    }
    const near = nearest(pt), box = document.getElementById('confirm');
    if (!box) return;
    box.innerHTML = near.d <= NEAR_KM
      ? `<div class="card confirm"><h3>${icon('pin', '#00733A')} ${esc(t('confirm_q'))}</h3>
          <p class="small">${esc(t('confirm_near', { place: near.p.label, km: Math.round(near.d) }))}</p>
          <button class="btn-big" data-act="confirm-farm">${esc(t('confirm_yes'))}</button></div>`
      : `<div class="warn">${esc(t('gps_far', { km: Math.round(near.d), place: near.p.label }))}</div>`;
  }
  function confirmFarm() {
    if (!pending) return;
    const near = nearest(pending);
    if (near.d > NEAR_KM) return;
    go('what', { farmPoint: pending, pilot: near.p.id, route: 0, campaign: 0 });
  }

  function gps() {
    const msg = document.getElementById('gps-msg');
    if (!navigator.geolocation) { msg.textContent = t('gps_denied'); return; }
    msg.textContent = t('gps_wait');
    navigator.geolocation.getCurrentPosition(pos => {
      const me = { latitude: pos.coords.latitude, longitude: pos.coords.longitude };
      const near = nearest(me);
      msg.textContent = near.d <= NEAR_KM ? t('gps_found', { place: near.p.label, km: Math.round(near.d) }) : '';
      if (map) { map.setView([me.latitude, me.longitude], 14); place(me); }
      else if (near.d <= NEAR_KM) { pending = me; confirmFarm(); }
      else msg.textContent = t('gps_far', { km: Math.round(near.d), place: near.p.label });
    }, () => { msg.textContent = t('gps_denied'); }, { timeout: 15000, maximumAge: 600000 });
  }

  // ---------- Iniciar sesión / Crear cuenta ----------
  function login() {
    const signup = authTab === 'signup';
    const field = (id, label, type, extra) => `<label class="field" for="${id}"><span>${esc(t(label))}</span>
      <input id="${id}" name="${id}" type="${type}" ${extra || ''}></label>`;
    const pin = id => field(id, id === 'f_pin' ? 'f_pin' : 'f_pin2', 'password', 'inputmode="numeric" pattern="[0-9]{4}" maxlength="4" autocomplete="' + (signup ? 'new-password' : 'current-password') + '"');
    return `${back('to-home')}
      <h2>${esc(t(signup ? 'signup_title' : 'login_title'))}</h2>
      <div class="seg" role="tablist">
        <button role="tab" data-auth="login" aria-selected="${!signup}">${esc(t('login_tab'))}</button>
        <button role="tab" data-auth="signup" aria-selected="${signup}">${esc(t('signup_tab'))}</button></div>
      <form id="auth" class="card" novalidate>
        ${signup ? field('f_name', 'f_name', 'text', 'autocomplete="name" maxlength="40"') : ''}
        ${field('f_phone', 'f_phone', 'tel', 'inputmode="numeric" autocomplete="tel" maxlength="15"')}
        ${pin('f_pin')}${signup ? pin('f_pin2') : ''}
        <p id="auth-msg" class="small auth-msg" role="alert">${esc(authMsg)}</p>
        <button class="btn-big" type="submit">${esc(t(signup ? 'signup_btn' : 'login_btn'))}</button>
      </form>`;
  }
  function digits(s) { return String(s || '').replace(/\D/g, ''); }
  async function submitAuth(form) {
    const val = id => (form.querySelector('#' + id) || {}).value || '';
    const phone = digits(val('f_phone')), pin = val('f_pin');
    const fail = key => { authMsg = t(key); const m = document.getElementById('auth-msg'); if (m) m.textContent = authMsg; };
    if (phone.length < 6) return fail('err_phone');
    if (!/^\d{4}$/.test(pin)) return fail('err_pin');
    if (authTab === 'signup') {
      const name = val('f_name').trim();
      if (!name) return fail('err_name');
      if (pin !== val('f_pin2')) return fail('err_pin2');
      if (accounts[phone]) return fail('err_exists');
      const salt = Array.from({ length: 16 }, () => Math.floor(Math.random() * 16).toString(16)).join('');
      accounts[phone] = { name, salt, pin: sha256(salt + pin), created: isoDay(new Date()), state: Object.assign(fresh(), { lang: state.lang }) };
    } else {
      const a = accounts[phone];
      if (!a || a.pin !== sha256(a.salt + pin)) return fail('err_login');
    }
    session = phone; authMsg = '';
    writeLS('terrapath_accounts', accounts); writeLS('terrapath_session', session);
    Object.keys(state).forEach(k => delete state[k]);
    Object.assign(state, fresh(), accounts[phone].state);
    afterLogin();
  }
  function afterLogin() {
    if (state.farm && DATA.pilots.some(p => p.id === state.farm.pilot)) return go('inicio');
    return go(state.pilot && state.care ? 'routes' : 'where');
  }
  function logout() {
    session = null; demoSession = false; writeLS('terrapath_session', null);
    const lang = state.lang;
    Object.keys(state).forEach(k => delete state[k]);
    Object.assign(state, fresh(), { lang });
    authTab = 'login';
    go('home');
  }

  // ---------- Inicio: resumen de la chacra ----------
  function inicio() {
    const u = user(), p = pilot();
    const hello = `<h2>${esc(t('hello', { name: u ? u.name : '' }))}</h2>`;
    if (!state.farm || !p) {
      return `${hello}<section class="card"><p>${esc(t('no_rotation'))}</p>
        <button class="btn-big" data-act="${p && state.care ? 'to-routes' : 'to-where'}">${esc(t('pick_rotation'))}</button></section>`;
    }
    const plan = schedule(p, state.farm), now = today();
    const { n, tasks, cur, next } = weekTasks(p, plan, now);
    const r = p.routes[state.farm.route];
    const shown = cur || next;
    let nowCard;
    if (shown) {
      const st = status(shown, now), last = lastMonth(shown);
      const when = shown.fallow ? ''
        : `<ul class="marks"><li>${icon('sprout', '#00733A', 18)} ${esc(t('milestone_sow', { month: cap(monthName(shown.s.getMonth() + 1)), year: shown.s.getFullYear() }))}</li>
           <li>${icon('leaf', '#5E6B12', 18)} ${esc(t('milestone_harvest', { month: cap(monthName(last.getMonth() + 1)), year: last.getFullYear() }))}</li></ul>`;
      nowCard = `<div class="now-crop"><span class="em" aria-hidden="true">${cropIcon(shown.key, 52)}</span><div>
          <strong>${esc(cap(cropName(shown.key)))}</strong> <span class="pill ${st}">${esc(t('status_' + st))}</span>
          <div class="small soft">${esc(t('campaign_n', { n: plan.indexOf(shown) + 1 }))}</div></div></div>${when}`;
    } else nowCard = `<p>${esc(t('task_done'))}</p>`;
    return `${hello}
      <section class="card"><h3>${icon('pin', '#00733A')} ${esc(t('home_farm'))}</h3>
        <p style="margin:0"><strong style="font-size:18px">${esc(p.label)}</strong><br><span class="small soft">${altitudes(p)}</span></p></section>
      <section class="card green"><h3>${icon('sprout', '#00733A')} ${esc(t(cur ? 'now_growing' : 'coming_next'))}</h3>${nowCard}</section>
      <section class="card"><h3>${icon('calendar', '#00733A')} ${esc(t('this_week'))}</h3>${taskList(tasks)}${weekStats(n)}
        <p class="small soft" style="margin:0">${esc(t('normal_year'))}</p></section>
      ${r ? `<section class="card route" data-nav="farm" role="button" tabindex="0"><h3>${icon('cycle', '#00733A')} ${esc(t('your_rotation'))} · ${esc(t('route_n', { n: state.farm.route + 1 }))}</h3>
        ${strip(state.farm.seq)}${axisBars(r)}</section>` : ''}
      ${mountain(p)}
      ${askTech()}`;
  }

  // ---------- Cuenta ----------
  function account() {
    const u = user();
    return `<h2>${esc(t('account_title'))}</h2>
      <section class="card"><div class="now-crop">${icon('user', '#00733A', 40)}<div><strong>${esc(u ? u.name : '')}</strong></div></div>
        ${session && session !== 'demo' ? `<p class="small" style="margin:6px 0 0;color:var(--ink-2)">${esc(session)}</p>` : ''}
        <p class="small soft" style="margin:4px 0 0">${esc(t('account_local'))}</p></section>
      <h3>${esc(t('choose_language'))}</h3>
      <div class="lang-row"><button class="on" data-act="lang-sheet" lang="${esc(state.lang)}">${esc(langName())}</button>
        <button data-act="lang-sheet">${esc(t('see_more'))}</button></div>
      ${langNote()}
      <button class="btn-list" data-act="to-where">${icon('pin', '#00733A')} ${esc(t('change_farm'))}</button>
      <button class="btn-list" data-act="logout">${icon('logout', '#00733A')} ${esc(t('logout'))}</button>`;
  }

  function nav() {
    return `<nav class="tabbar" aria-label="${esc(t('app_name'))}">${NAV.map(([v, l, ico]) => {
      const on = state.view === v || (v === 'routes' && ['why', 'calendar'].includes(state.view));
      return `<button data-nav="${v}" aria-current="${on ? 'page' : 'false'}">${icon(ico, on ? '#00733A' : '#4A6354', 24)}<span>${esc(t(l))}</span></button>`;
    }).join('')}</nav>`;
  }

  // SHA-256 (para no guardar la clave tal cual; funciona también sin HTTPS, donde crypto.subtle no existe).
  function sha256(ascii) {
    const K = [], H = [], isP = n => { for (let f = 2; f * f <= n; f++) if (n % f === 0) return false; return true; };
    for (let c = 2, i = 0; i < 64; c++) if (isP(c)) { if (i < 8) H[i] = (c ** .5 * 2 ** 32) | 0; K[i++] = (c ** (1 / 3) * 2 ** 32) | 0; }
    const bytes = unescape(encodeURIComponent(ascii)).split('').map(ch => ch.charCodeAt(0));
    const len = bytes.length * 8; bytes.push(0x80);
    while (bytes.length % 64 !== 56) bytes.push(0);
    for (let i = 7; i >= 0; i--) bytes.push(i > 3 ? 0 : (len >>> (i * 8)) & 255);
    const rot = (v, n) => (v >>> n) | (v << (32 - n));
    for (let o = 0; o < bytes.length; o += 64) {
      const w = [];
      for (let i = 0; i < 64; i++) {
        if (i < 16) w[i] = (bytes[o + 4 * i] << 24) | (bytes[o + 4 * i + 1] << 16) | (bytes[o + 4 * i + 2] << 8) | bytes[o + 4 * i + 3];
        else { const a = w[i - 15], b = w[i - 2]; w[i] = (w[i - 16] + (rot(a, 7) ^ rot(a, 18) ^ (a >>> 3)) + w[i - 7] + (rot(b, 17) ^ rot(b, 19) ^ (b >>> 10))) | 0; }
      }
      let [a, b, c, d, e, f, g, h] = H;
      for (let i = 0; i < 64; i++) {
        const t1 = (h + (rot(e, 6) ^ rot(e, 11) ^ rot(e, 25)) + ((e & f) ^ (~e & g)) + K[i] + w[i]) | 0;
        const t2 = ((rot(a, 2) ^ rot(a, 13) ^ rot(a, 22)) + ((a & b) ^ (a & c) ^ (b & c))) | 0;
        h = g; g = f; f = e; e = (d + t1) | 0; d = c; c = b; b = a; a = (t1 + t2) | 0;
      }
      [a, b, c, d, e, f, g, h].forEach((v, i) => { H[i] = (H[i] + v) | 0; });
    }
    return H.map(v => (v >>> 0).toString(16).padStart(8, '0')).join('');
  }

  // ---------- render y eventos ----------
  const VIEWS = { home, login, inicio, account, where, what, care, routes, why, calendar, farm };
  function render() {
    if (map) { try { map.remove(); } catch (e) { /* nada */ } map = null; marker = null; }
    if (!VIEWS[state.view]) state.view = 'home';
    if (!user() && !OPEN_VIEWS.includes(state.view)) state.view = 'login';
    if (user() && state.view === 'login') state.view = 'inicio';
    if ((state.view === 'farm' || state.view === 'inicio') && state.farm) state.pilot = state.farm.pilot;
    if (state.view === 'farm' && !state.farm) state.view = 'inicio';
    if (!pilot() && !['home', 'login', 'where', 'inicio', 'account'].includes(state.view)) state.view = 'where';
    if (state.view === 'routes' && !state.care) state.view = pilot() ? 'care' : 'where';
    if (['why', 'calendar'].includes(state.view) && !pilot().routes[state.route]) state.view = 'routes';
    document.documentElement.lang = translated() ? state.lang : 'en';
    document.documentElement.dir = translated() && state.lang === 'ar' ? 'rtl' : 'ltr';
    const withNav = !!user() && !['home', 'login', 'where', 'what', 'care'].includes(state.view);
    const withAi = withNav && AI_VIEWS.includes(state.view);
    if (!withAi) aiOpen = false;
    if (state.view !== 'home') langOpen = false;
    if (state.view !== 'account') langSheetOpen = false;
    // Transición: la pantalla nueva entra deslizándose (hacia atrás desde la izquierda); un cambio
    // dentro de la misma pantalla (elegir una opción) no la repite.
    const enter = state.view !== lastView ? ` enter${navBack ? ' back' : ''}` : '';
    lastView = state.view; navBack = false;
    app.innerHTML = `<div class="view${enter}">${VIEWS[state.view]()}</div>` + (withAi ? aiButton() : '') + (withNav ? nav() : '')
      + (aiOpen ? aiSheet() : '') + (langSheetOpen ? langSheet() : '');
    document.body.classList.toggle('has-main', !!app.querySelector('.btn-main'));
    document.body.classList.toggle('has-nav', withNav);
    if (state.view === 'where') initMap();
  }

  function onClick(e) {
    const b = e.target.closest('[data-act],[data-lang],[data-pilot],[data-year],[data-care],[data-route],[data-campaign],[data-tab],[data-nav],[data-auth]');
    // Tocar fuera del menú de idiomas lo cierra.
    if (langOpen && (!b || (!b.dataset.lang && b.dataset.act !== 'lang-toggle'))) { langOpen = false; if (!b) return render(); }
    if (!b || b.tagName === 'SELECT') return;
    const d = b.dataset;
    if (d.dir === 'back') navBack = true;
    if (d.lang) { state.lang = d.lang; langOpen = false; save(); return render(); }
    if (d.pilot) { state.pilot = d.pilot; state.farmPoint = null; state.route = 0; state.campaign = 0; save(); return render(); }
    if (d.year !== undefined) { state.history[+d.year] = d.crop || null; save(); return render(); }
    if (d.care) { state.care = d.care; save(); return render(); }
    if (d.route !== undefined) return go('why', { route: +d.route, campaign: 0 });
    if (d.campaign !== undefined) { state.campaign = +d.campaign; save(); return render(); }
    if (d.tab) { state.tab = d.tab; save(); return render(); }
    if (d.nav) return go(d.nav);
    if (d.auth) { authTab = d.auth; authMsg = ''; return render(); }
    const act = d.act;
    if (act === 'ai' || act === 'ai-close') { aiOpen = act === 'ai'; return render(); }
    if (act === 'lang-toggle') { langOpen = !langOpen; return render(); }
    if (act === 'lang-sheet' || act === 'lang-close') { langSheetOpen = act === 'lang-sheet'; return render(); }
    if (act === 'gps') return gps();
    if (act === 'remind') return remind();
    if (act === 'confirm-farm') return confirmFarm();
    if (act === 'start') return user() ? afterLogin() : go('login');
    if (act === 'logout') return logout();
    if (act === 'choose-route') {
      const p = pilot();
      return go('inicio', { tab: 'week', farm: { pilot: p.id, route: state.route, seq: orderedSequence(p, p.routes[state.route]), start: isoDay(today()) } });
    }
    if (act === 'restart') return go('where', Object.assign(fresh(), { lang: state.lang, farm: state.farm }));
    if (act && act.startsWith('to-')) return go(act.slice(3));
  }
  document.addEventListener('click', onClick);
  document.addEventListener('change', e => {
    if (e.target.matches('select[data-year]')) { state.history[+e.target.dataset.year] = e.target.value || null; save(); render(); }
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && (langOpen || langSheetOpen || aiOpen)) { langOpen = langSheetOpen = aiOpen = false; render(); }
  });
  document.addEventListener('submit', e => { if (e.target.id === 'auth') { e.preventDefault(); submitAuth(e.target); } });
  app.addEventListener('keydown', e => {
    if ((e.key === 'Enter' || e.key === ' ') && e.target.matches('[data-route]')) { e.preventDefault(); e.target.click(); }
  });

  render();
  if ('serviceWorker' in navigator && location.protocol.startsWith('http')) {
    navigator.serviceWorker.register('sw.js').catch(() => { /* sin caché: la app sigue funcionando */ });
  }
})();
