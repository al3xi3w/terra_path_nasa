# Terrapath — app del agricultor

Qué sembrar en tus próximas campañas. App web sin servidores de terceros salvo las teselas del mapa
(OpenStreetMap, con Leaflet 1.9.4 guardado en `vendor/leaflet/`, licencia BSD-2). Después de la primera
visita la app y las teselas ya vistas quedan en el teléfono (service worker). Sin APIs de Google.

## Cómo abrirla

```bash
.venv/bin/python scripts/build_app.py        # exporta los datos del motor a app/data/app_data.js
.venv/bin/python -m http.server 8000 -d app  # luego abre http://localhost:8000 en el teléfono o el navegador
```

También abre directo con doble clic en `app/index.html`, pero así no se activa el guardado sin internet.
Para instalarla en un teléfono: servir la carpeta por HTTPS (o desde la misma red con `http.server`) y usar
"Agregar a pantalla de inicio".

Enlaces directos a pantallas (demo): `index.html#view=routes&pilot=piura_1&care=water&now=potato`
(`view` = home, where, what, care, routes, why, calendar, farm; `care` = water, soil, safe; `now` = cultivo de este año;
`farm=AAAA-MM-DD` fija el inicio de la rotación, `today=AAAA-MM-DD` la fecha de hoy, `tab` = week, month, year; `user=Nombre` abre una sesión de prueba que no se guarda; `auth=signup`).
Vistas: home (bienvenida), login, inicio, farm, routes, account, y los pasos where, what, care, why, calendar.

Pruebas de la lógica de pantallas: `node tests/js/app_smoke.js` (también corre dentro de pytest).

## De dónde sale cada cosa

| En pantalla | Fuente |
|---|---|
| Rutas y barras de Agua / Tierra / Cosecha segura (0-100, con su número) | `src/rotation_scores.py` (`routes_<piloto>.json`) |
| "★ Para ti" | la mejor ruta de tres cultivos en la prioridad elegida |
| "Compara tus rutas", barra gris "Hoy" | el cultivo de este año repetido tres campañas, con las mismas funciones del motor |
| Altitudes | `routes_<piloto>.json` → `point`: chacra = SRTM (`elevation_for_suitability`), dato del clima = encabezado NASA POWER (`elevation_m`) |
| Mi chacra (semana, mes) | normales diarias 1981-2024 de NASA POWER (lluvia, mínima, proporción de años con helada) y ET0 FAO-56; rotulado "en un año normal, no es un pronóstico" |
| Mi chacra (año) | meses de campaña del motor encadenados desde la fecha en que eligió la rotación |
| Inicio (resumen) | lugar, altitudes, cultivo de la campaña actual y su estado, tareas y clima normal de la semana, rotación elegida |
| Cuenta | local, en el teléfono: nombre, celular y clave de 4 números guardada como SHA-256 con sal (sin servidor) |
| Razones | `soil_detail`, déficit Kc×ET0, días de helada a la temperatura letal, años secos |
| Días con helada por mes | `climate_profile_<piloto>.csv` (NASA POWER, T2M_MIN < 0 °C, 1981-2024) |
| Lluvia y lo que pide el cultivo | lluvia media de los meses de la campaña y Kc_medio FAO-56 × ET0 |
| "Entre 2016 y 2024…" | `backtest_<piloto>.json` contra el monocultivo típico declarado (maíz, FAOSTAT) |
| Primera helada | primer día bajo 0 °C de la temporada fría, mediana de 1981-2024 (POWER diario) |
| Zona de montaña | SRTM (`terreno.csv`): pendiente media > 5° o diferencia > 300 m con MERRA-2 |

## Lo que la app no inventa

- Un dato que el motor no tiene se muestra como "—" con un ícono gris (sin texto de disculpa); nunca como 0.
- Menos de 3 rutas: lo dice. Ninguna: lo dice.
- Montaña: advierte que la grilla de ~50 km suaviza el relieve (Huancabamba, Piura sur, Piura norte).
- Fechas: meses, no días exactos.

## Pendiente

- **Quechua**: el selector existe; `i18n.js` → `qu` está vacío a propósito. Debe llenarlo un hablante nativo
  de la variante de la zona. Mientras tanto se muestra el español con un aviso.
- **Mapa**: Leaflet + OpenStreetMap, zoom 10-16, un marcador. Si no carga, queda solo la lista, sin error.
  Si el punto más cercano con datos está a más de 30 km, la app dice que aún no tiene datos para esa zona.
- **Solo 6 lugares**: los que tienen serie NASA POWER local. Agregar uno = descargar su serie y volver a correr el pipeline.
- **"Cosecha"**: no hay rendimientos por punto; la prioridad se muestra como "Cosecha segura" (menos helada y años secos).
- **Avísame**: descarga un recordatorio de calendario (.ics) para el mes de siembra; no hay notificaciones push.
