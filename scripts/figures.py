"""Figures for the demo, from the real outputs only. Exports PNG to reports/figures/.

    python scripts/figures.py

- radar_rutas.png: the 3 routes per pilot on water, soil and risk (0-100), from routes_<pilot>.json.
- calendario_riesgo.png: frost days and climatic deficit by month, from climate_profile_<pilot>.csv.
- lluvia_vs_demanda.png: monthly rain vs Kc_mid x ET0 for the crops that have FAO-56 Kc.

Every figure carries its source in a footnote. Nothing is interpolated or filled: a month with no
ET0 or rain stays blank.
"""
import json, sys, time
from pathlib import Path
import pandas as pd
import plotly
import plotly.graph_objects as go
import plotly.io as pio
from plotly.subplots import make_subplots
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.climate_profile import pilots
from src.crop_library import build_library
from src.pipeline import ROOT

# Load plotly.js from the installed package, not the CDN: offline-safe and avoids kaleido's flaky page load.
pio.defaults.plotlyjs = str(Path(plotly.__file__).parent / 'package_data/plotly.min.js')
pio.defaults.mathjax = None

# Reference categorical slots 1-3 (validated all-pairs, light mode), sequential blue, diverging blue/orange.
SERIES = {'ruta_agua': '#2a78d6', 'ruta_suelo': '#eb6834', 'ruta_riesgo': '#1baf7a'}
ROUTE_LABEL = {'ruta_agua': 'Ruta agua', 'ruta_suelo': 'Ruta suelo', 'ruta_riesgo': 'Ruta riesgo'}
SURFACE, INK, INK2, GRID = '#fcfcfb', '#0b0b0b', '#52514e', '#e4e3df'
SEQ_BLUE = [[0, '#f4f8fd'], [0.25, '#b7d3f6'], [0.5, '#6da7ec'], [0.75, '#2a78d6'], [1, '#104281']]
DIVERGING = [[0, '#1c5cab'], [0.25, '#86b6ef'], [0.5, '#e9e8e4'], [0.75, '#f5a37f'], [1, '#b93f12']]
MONTHS = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic']
FONT = dict(family='Inter, Helvetica, Arial, sans-serif', color=INK, size=13)


def layout(fig, title, note, height):
    fig.update_layout(title=dict(text=title, x=0.01, font=dict(size=19)), font=FONT, paper_bgcolor=SURFACE,
                      plot_bgcolor=SURFACE, height=height, width=1400, margin=dict(l=70, r=40, t=110, b=130))
    fig.add_annotation(text=note, xref='paper', yref='paper', x=0, y=-0.02, yshift=-60, showarrow=False,
                       xanchor='left', yanchor='top', align='left', font=dict(size=11, color=INK2))
    return fig


def save(fig, path, attempts=4):
    """PNG export with retries: kaleido's headless browser sometimes starts before its page is ready."""
    for i in range(attempts):
        try:
            fig.write_image(path, scale=2);return
        except Exception:
            if i == attempts - 1:raise
            time.sleep(1 + i)


def load_routes(root):
    return {p['name']: (p, json.loads((Path(root) / f"data/processed/routes_{p['name']}.json").read_text())) for p in pilots(root)}


def radar(root, out):
    routes = load_routes(root)
    names = list(routes)
    fig = make_subplots(rows=2, cols=3, specs=[[{'type': 'polar'}] * 3] * 2,
                        subplot_titles=[f"{routes[n][0]['label']} · {routes[n][1].get('window', '')}" for n in names],
                        vertical_spacing=0.2, horizontal_spacing=0.08)
    axes = ['Agua', 'Suelo', 'Riesgo', 'Agua']
    for i, name in enumerate(names):
        data = routes[name][1]
        if not data.get('routes'):
            domain = fig.layout[f"polar{'' if i == 0 else i + 1}"].domain
            fallow = [r for r in (data.get('routes_with_fallow') or {}).values() if r]
            text = 'Sin ruta de tres cultivos<br>con agua conocida' + (
                '<br><br>Con barbecho:<br>' + '<br>'.join(' → '.join(r['sequence']) + f" (agua {r['water']:g})" for r in fallow) if fallow else '')
            fig.add_annotation(text=text, xref='paper', yref='paper', xanchor='center', align='center',
                               x=domain.x[0] + 0.6 * (domain.x[1] - domain.x[0]), y=sum(domain.y) / 2,
                               showarrow=False, font=dict(size=12, color=INK2))
        for key, route in (data.get('routes') or {}).items():
            if route is None:continue
            values = [route['water'], route['soil'], route['risk'], route['water']]
            dominated = not route['from_pareto_front']
            fig.add_trace(go.Scatterpolar(
                r=values, theta=axes, name=ROUTE_LABEL[key], legendgroup=key, showlegend=i == 0,
                line=dict(color=SERIES[key], width=2, dash='dash' if dominated else 'solid'),
                marker=dict(size=8, line=dict(color=SURFACE, width=2)), mode='lines+markers',
                hovertemplate=f"{ROUTE_LABEL[key]}: {' → '.join(route['sequence'])}<br>%{{theta}} %{{r}}<extra></extra>"),
                row=i // 3 + 1, col=i % 3 + 1)
        fig.layout[f"polar{'' if i == 0 else i + 1}"].update(
            bgcolor=SURFACE, radialaxis=dict(range=[0, 100], tickvals=[25, 50, 75, 100], gridcolor=GRID,
                                             tickfont=dict(size=10, color=INK2), linecolor=GRID),
            angularaxis=dict(gridcolor=GRID, linecolor=GRID, tickfont=dict(size=12)))
    fig.update_annotations(font=dict(size=14, color=INK))
    fig.update_layout(legend=dict(orientation='h', x=1, xanchor='right', y=1.12, yanchor='bottom', font=dict(size=13)))
    note = ('Fuente: data/processed/routes_<piloto>.json (src/rotation_scores.py; NASA POWER 1981-2024, EcoCrop, FAO-56). Escala 0-100. '
            'Línea discontinua = ruta dominada. Donde se ve una sola línea, las rutas tienen puntajes idénticos y se superponen.<br>'
            'Limitaciones: suelo saturado en 100 (3 criterios); agua solo con Kc FAO-56 (girasol, trébol y tarwi no tienen); trigo, cebada y papa comparten Kc 1,15 y temperatura letal 0 °C.<br>'
            'La regla de familias incluye el paso de la última campaña a la primera (la rotación se repite): por eso hay 1 o 2 rutas por piloto, no siempre 3. '
            'Riesgo = heladas + variabilidad + sequía (años bajo 50 % de la lluvia media de campaña). Altitud del filtro: SRTM en el punto.')
    save(layout(fig, 'Rutas de rotación por piloto: agua, suelo y riesgo', note, 900), out / 'radar_rutas.png')


def profiles(root):
    return {p['name']: (p, pd.read_csv(Path(root) / f"data/processed/climate_profile_{p['name']}.csv")) for p in pilots(root)}


def risk_calendar(root, out):
    data = profiles(root)
    labels = [p['label'] for p, _ in data.values()]
    frost = [d.frost_days_mean.tolist() for _, d in data.values()]
    deficit = [[None if pd.isna(e) or pd.isna(r) else round(e - r) for e, r in zip(d.et0_mean_mm, d.rain_mean_mm)]
               for _, d in data.values()]
    fig = make_subplots(rows=2, cols=1, vertical_spacing=0.2, subplot_titles=[
        'Días de helada por mes (T2M_MIN < 0 °C, media 1981-2024)',
        'Balance climático por mes: ET0 − lluvia (mm; naranja = déficit, azul = excedente; ET0 1984-2024)'])
    top = max(max(r) for r in frost) or 1
    fig.add_trace(go.Heatmap(z=frost, x=MONTHS, y=labels, colorscale=SEQ_BLUE, zmin=0, zmax=top, xgap=2, ygap=2,
                             text=[[f'{v:.1f}' if v else '0' for v in r] for r in frost], texttemplate='%{text}',
                             textfont=dict(size=11), colorbar=dict(title='días', y=0.8, len=0.4),
                             hovertemplate='%{y} · %{x}: %{z} días<extra></extra>'), row=1, col=1)
    span = max(abs(v) for r in deficit for v in r if v is not None)
    fig.add_trace(go.Heatmap(z=deficit, x=MONTHS, y=labels, colorscale=DIVERGING, zmin=-span, zmax=span, xgap=2, ygap=2,
                             text=[['' if v is None else f'{v:+d}' for v in r] for r in deficit], texttemplate='%{text}',
                             textfont=dict(size=11), colorbar=dict(title='mm', y=0.2, len=0.4),
                             hovertemplate='%{y} · %{x}: %{z} mm<extra></extra>'), row=2, col=1)
    fig.update_yaxes(autorange='reversed', tickfont=dict(size=12))
    fig.update_xaxes(side='bottom', tickfont=dict(size=12))
    note = ('Fuente: data/processed/climate_profile_<piloto>.csv (src/climate_profile.py; NASA POWER diario, SHA-256 en climate_profiles.parquet). '
            'ET0 FAO-56 Penman-Monteith; desde 1984 porque la radiación de POWER empieza ese año.<br>'
            'El balance usa la ET0 de referencia (Kc = 1), no la demanda de un cultivo. Lluvia total, sin lluvia efectiva. '
            'Huancabamba: 0 heladas en 44 años en POWER; MERRA-2 (~50 km) suaviza la montaña y esto no prueba que no hiele.')
    save(layout(fig, 'Calendario de riesgo: heladas y déficit de agua, 12 meses', note, 900), out / 'calendario_riesgo.png')


def rain_vs_demand(root, out):
    data = profiles(root)
    routes = load_routes(root)
    library = build_library(root)
    with_kc = library[library.kc_mid.notna()][['crop_key', 'kc_mid']]
    without = ', '.join(library[library.kc_mid.isna()].crop_key)
    kc_low, kc_high = float(with_kc.kc_mid.min()), float(with_kc.kc_mid.max())
    names = list(data)
    fig = make_subplots(rows=2, cols=3, shared_yaxes=True, vertical_spacing=0.16, horizontal_spacing=0.04,
                        subplot_titles=[f"{data[n][0]['label']}" for n in names])
    for i, name in enumerate(names):
        row, col = i // 3 + 1, i % 3 + 1
        d = data[name][1]
        months = routes[name][1].get('window_months') or []
        fig.add_trace(go.Bar(x=d.month, y=d.rain_mean_mm, name='Lluvia media', marker=dict(color='#2a78d6', cornerradius=4),
                             showlegend=i == 0, legendgroup='rain', hovertemplate='%{x}: %{y:.0f} mm<extra>lluvia</extra>'), row=row, col=col)
        fig.add_trace(go.Scatter(x=d.month, y=d.et0_mean_mm * kc_high, mode='lines', line=dict(color='#eb6834', width=0),
                                 showlegend=False, legendgroup='band', hoverinfo='skip'), row=row, col=col)
        fig.add_trace(go.Scatter(x=d.month, y=d.et0_mean_mm * kc_low, mode='lines', fill='tonexty', line=dict(color='#eb6834', width=0),
                                 fillcolor='rgba(235,104,52,0.22)', name=f'Kc_medio × ET0 (Kc {kc_low:g}–{kc_high:g})',
                                 showlegend=i == 0, legendgroup='band', hoverinfo='skip'), row=row, col=col)
        fig.add_trace(go.Scatter(x=d.month, y=d.et0_mean_mm * kc_high, mode='lines', name='',
                                 line=dict(color='#eb6834', width=2),
                                 showlegend=False, legendgroup='band',
                                 hovertemplate='%{x}: %{y:.0f} mm<extra>Kc ' + f'{kc_high:g}' + ' × ET0</extra>'), row=row, col=col)
        for k, m in enumerate(months):  # after the traces: plotly skips shapes on subplots that are still empty
            fig.add_vrect(x0=m - 0.5, x1=m + 0.5, fillcolor='#dcdad3', opacity=0.6, line_width=0, layer='below', row=row, col=col,
                          **(dict(annotation_text='campañas', annotation_position='top left',
                                  annotation_font=dict(size=11, color=INK2)) if k == 0 else {}))
    fig.update_xaxes(tickvals=list(range(1, 13)), ticktext=MONTHS, tickfont=dict(size=10), showgrid=False, linecolor=GRID)
    fig.update_yaxes(gridcolor=GRID, zeroline=False, tickfont=dict(size=10, color=INK2))
    fig.update_yaxes(title_text='mm por mes', row=1, col=1);fig.update_yaxes(title_text='mm por mes', row=2, col=1)
    fig.update_annotations(font=dict(size=14, color=INK))
    fig.update_layout(legend=dict(orientation='h', x=1, xanchor='right', y=1.12, yanchor='bottom', font=dict(size=13)), bargap=0.25)
    crops = ', '.join(f'{r.crop_key} {r.kc_mid:g}' for r in with_kc.itertuples())
    note = (f'Fuente: climate_profile_<piloto>.csv (NASA POWER; lluvia 1981-2024, ET0 1984-2024) y crop_library.csv (Kc_medio FAO-56 Tabla 12: {crops}).<br>'
            'Gris = meses que ocupan las campañas de los cultivos elegibles (inicio elegido + ciclo mínimo EcoCrop), de routes_<piloto>.json. '
            f'La banda cubre los {len(with_kc)} cultivos con Kc FAO-56 verificado; sin Kc (no se dibujan): {without}.<br>'
            'Kc_medio × ET0 sobreestima la demanda fuera de mitad de ciclo (no es ETc por etapas). Lluvia total, no efectiva.')
    save(layout(fig, 'Lluvia mensual frente a la demanda de agua del cultivo', note, 900), out / 'lluvia_vs_demanda.png')


def mann_kendall(values):
    """Two-sided Mann-Kendall test, normal approximation with tie correction. Returns (S, p)."""
    import math
    x = list(values);n = len(x)
    s = sum((x[j] > x[i]) - (x[j] < x[i]) for i in range(n - 1) for j in range(i + 1, n))
    ties = pd.Series(x).value_counts()
    var = (n * (n - 1) * (2 * n + 5) - sum(t * (t - 1) * (2 * t + 5) for t in ties if t > 1)) / 18
    if var <= 0:return s, None
    z = (s - 1) / math.sqrt(var) if s > 0 else ((s + 1) / math.sqrt(var) if s < 0 else 0.0)
    return s, 2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2))))


def ols_slope(years, values):
    """Least-squares slope per year."""
    x = pd.Series(years, dtype=float);y = pd.Series(values, dtype=float)
    return float(((x - x.mean()) * (y - y.mean())).sum() / ((x - x.mean()) ** 2).sum())


def annual(root):
    """Complete years only; a year with missing days never enters a trend."""
    out = {}
    for p in pilots(root):
        a = pd.read_csv(Path(root) / f"data/processed/climate_annual_{p['name']}.csv")
        out[p['name']] = (p, a[a.complete_year.astype(bool)])
    return out


def trend_label(years, values, unit):
    slope = ols_slope(years, values) * 10
    _, pval = mann_kendall(values)
    shown = 'p < 0.001' if pval is not None and pval < 0.001 else f'p = {pval:.3f}'
    return f"{slope:+.0f} {unit}/década · Mann-Kendall {shown}" + (' (no significativa)' if pval is None or pval >= 0.05 else '')


def trends(root, out):
    data = annual(root)
    names = list(data)
    fig = make_subplots(rows=2, cols=3, vertical_spacing=0.2, horizontal_spacing=0.05,
                        subplot_titles=[data[n][0]['label'] for n in names])
    for i, name in enumerate(names):
        row, col = i // 3 + 1, i % 3 + 1
        a = data[name][1].dropna(subset=['rain_mm'])
        fig.update_yaxes(range=[0, float(a.rain_mm.max()) * 1.18], row=row, col=col)
        fig.add_trace(go.Scatter(x=a.year, y=a.rain_mm, mode='lines+markers', name='Lluvia anual', showlegend=i == 0,
                                 line=dict(color='#2a78d6', width=2), marker=dict(size=6),
                                 hovertemplate='%{x}: %{y:.0f} mm<extra></extra>'), row=row, col=col)
        slope = ols_slope(a.year, a.rain_mm)
        fit = a.rain_mm.mean() + slope * (a.year - a.year.mean())
        fig.add_trace(go.Scatter(x=a.year, y=fit, mode='lines', name='Tendencia lineal (MCO)', showlegend=i == 0,
                                 line=dict(color='#eb6834', width=2, dash='dash'), hoverinfo='skip'), row=row, col=col)
        fig.add_annotation(text=trend_label(a.year, a.rain_mm, 'mm'), xref=f"x{'' if i == 0 else i + 1} domain",
                           yref=f"y{'' if i == 0 else i + 1} domain", x=0.02, y=0.98, showarrow=False, xanchor='left',
                           yanchor='top', font=dict(size=11, color=INK2), bgcolor='rgba(252,252,251,0.85)')
    fig.update_xaxes(showgrid=False, linecolor=GRID, tickfont=dict(size=10))
    fig.update_yaxes(gridcolor=GRID, zeroline=False, tickfont=dict(size=10, color=INK2))
    fig.update_yaxes(title_text='mm por año', row=1, col=1);fig.update_yaxes(title_text='mm por año', row=2, col=1)
    fig.update_annotations(font_color=INK)
    fig.update_layout(legend=dict(orientation='h', x=1, xanchor='right', y=1.12, yanchor='bottom', font=dict(size=13)))
    note = ('Fuente: data/processed/climate_annual_<piloto>.csv (NASA POWER PRECTOTCORR diario, 1981-2024, solo años completos; '
            'SHA-256 del archivo POWER en routes_<piloto>.json).<br>'
            'Pendiente por mínimos cuadrados; significancia con Mann-Kendall bilateral (aproximación normal, corrección por empates). '
            'p ≥ 0,05 = no hay evidencia de tendencia.<br>'
            'POWER es un producto de reanálisis (MERRA-2 corregido con lluvia satelital), no una estación; en montaña (Huancabamba) suaviza el relieve. '
            'En Piura los picos de 1983 y 1998 (años El Niño) caen en la primera mitad y empujan la pendiente hacia abajo: no extrapolar.')
    save(layout(fig, 'Tendencia de la lluvia anual, 1981-2024', note, 900), out / 'tendencia_lluvia.png')

    with_frost = [n for n in names if data[n][1].frost_days.fillna(0).sum() > 0]
    zero = [data[n][0]['label'] for n in names if n not in with_frost]
    fig = make_subplots(rows=1, cols=max(1, len(with_frost)), horizontal_spacing=0.08,
                        subplot_titles=[data[n][0]['label'] for n in with_frost])
    for i, name in enumerate(with_frost):
        a = data[name][1].dropna(subset=['frost_days'])
        fig.update_yaxes(range=[0, float(a.frost_days.max()) * 1.18], row=1, col=i + 1)
        fig.add_trace(go.Bar(x=a.year, y=a.frost_days, name='Días de helada', showlegend=i == 0,
                             marker=dict(color='#2a78d6', cornerradius=3), hovertemplate='%{x}: %{y} días<extra></extra>'), row=1, col=i + 1)
        slope = ols_slope(a.year, a.frost_days)
        fit = a.frost_days.mean() + slope * (a.year - a.year.mean())
        fig.add_trace(go.Scatter(x=a.year, y=fit, mode='lines', name='Tendencia lineal (MCO)', showlegend=i == 0,
                                 line=dict(color='#eb6834', width=2, dash='dash'), hoverinfo='skip'), row=1, col=i + 1)
        fig.add_annotation(text=trend_label(a.year, a.frost_days, 'días'), xref=f"x{'' if i == 0 else i + 1} domain",
                           yref=f"y{'' if i == 0 else i + 1} domain", x=0.02, y=0.98, showarrow=False, xanchor='left',
                           yanchor='top', font=dict(size=11, color=INK2), bgcolor='rgba(252,252,251,0.85)')
    fig.update_xaxes(showgrid=False, linecolor=GRID)
    fig.update_yaxes(gridcolor=GRID, zeroline=False, tickfont=dict(color=INK2), title_text='días con T2M_MIN < 0 °C')
    fig.update_annotations(font_color=INK)
    fig.update_layout(legend=dict(orientation='h', x=1, xanchor='right', y=1.12, yanchor='bottom', font=dict(size=13)), bargap=0.15)
    note = ('Fuente: climate_annual_<piloto>.csv (NASA POWER T2M_MIN diario, 1981-2024, años completos). Umbral 0 °C, no la temperatura letal de cada cultivo.<br>'
            f"Sin heladas en 44 años según POWER: {', '.join(zero)}. MERRA-2 tiene celdas de ~50 km y suaviza la montaña; "
            'en Huancabamba esto no prueba que no hiele.')
    save(layout(fig, 'Tendencia de los días de helada por año, 1981-2024', note, 620), out / 'tendencia_heladas.png')


def main(root=ROOT):
    out = Path(root) / 'reports/figures'
    out.mkdir(parents=True, exist_ok=True)
    radar(root, out);risk_calendar(root, out);rain_vs_demand(root, out);trends(root, out)
    for f in sorted(out.glob('*.png')):print(f.relative_to(Path(root)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
