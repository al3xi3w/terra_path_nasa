# Rutas de Cultivo — funcionalidad y apariencia de la app

Especificación para diseño y pitch, derivada del prototipo de 6 pantallas y del motor ya
implementado en este repositorio. Paleta tomada del prototipo, muestreada pixel a pixel.

## 1. A quién le hablamos

Un agricultor que quizá nunca usó una app, que puede estar sin señal en su chacra y cuya
primera lengua puede no ser el español. Tres consecuencias de diseño, no negociables:

- **Una sola pregunta por pantalla**, en sus palabras: "¿Dónde está tu chacra?",
  "¿Qué siembras ahora?", "¿Qué te importa más?".
- **Nada de jerga**: "Cuidar el agua", no "optimización hídrica". "Descanso", no "barbecho".
  "Lo que pide el cultivo", no "evapotranspiración".
- **Todo ícono lleva su palabra al lado.** Nunca un ícono solo.

## 2. Principios de interfaz

| Principio | Cómo se ve |
|---|---|
| Un camino, no un menú | 3 pasos con puntos de progreso arriba; una sola acción principal por pantalla |
| Botón grande que cierra la pantalla | Píldora de ancho completo, verde, con flecha: "Empezar", "Ver mis rutas", "¿Cuándo sembrar?" |
| Se puede escuchar | Botón de audio circular fijo arriba a la derecha: lee la pantalla en voz alta |
| Funciona sin internet | Distintivo visible en el inicio; guarda el último resultado y los perfiles ya descargados |
| Se puede volver | Flecha atrás a la izquierda, siempre en el mismo lugar |
| Dos idiomas desde el inicio | Español y Quechua, elegibles antes de empezar |
| Tarjetas, no formularios | Bloques blancos redondeados sobre fondo verde pálido; mucho aire entre ellos |

## 3. Las pantallas

### 0 · Inicio
Logo de brote, nombre y una frase que explica todo: "Te ayudamos a elegir qué sembrar después,
con datos del satélite". Selector de idioma y botón "Empezar". Arriba, el distintivo
"Funciona sin internet" tranquiliza antes de que el usuario pregunte.

### 1 · ¿Dónde está tu chacra?
Dos maneras de responder, en pestañas: **Lista** (distritos cercanos con su región, para quien
no sabe leer un mapa) y **Mapa** (tocar la parcela directamente). Arriba de todo, "Usar dónde
estoy" con el GPS, que es la vía más rápida. Al elegir, una tarjeta confirma el lugar y su
altura: "Huancabamba · 2 950 m de altura", con el botón "Sí, es mi chacra".

Esto es lo único obligatorio de toda la app.

### 2 · ¿Qué siembras ahora? y ¿Qué te importa más?
Tres círculos con los cultivos de los últimos años (Año 1, Año 2, Año 3) e instrucción directa:
"Toca un cultivo para cambiarlo". Si no lo sabe, se puede saltar.

Debajo, la prioridad en tres tarjetas con ícono, título y una línea de explicación:
- **Cuidar el agua** — "Cultivos que piden poca lluvia"
- **Mejorar la tierra** — "Que el suelo no se canse"
- **Cosechar más** — "Más kilos para vender"

La elegida se marca con borde verde y check. Es la única decisión que se le pide.

### 3 · Tus 3 rutas
Arriba, "Lo que siembras hoy" como referencia. Luego tres tarjetas, una por ruta, cada una con
ícono, nombre, una línea de para qué sirve y los tres cultivos con su dibujo y su nombre. La
que corresponde a su prioridad lleva la insignia "★ Para ti" y borde verde.

Debajo de cada ruta, tres barras de puntos (agua, suelo, cosecha): se entienden de un vistazo,
sin leer números.

Al final, el radar "Comparar con lo de hoy": cuatro ejes (Agua, Suelo, Cosecha, Helada), la
rotación actual en línea punteada y las tres rutas en color. Es el gráfico del pitch.

### 4 · ¿Por qué esta ruta?
La pantalla que da confianza. Tres razones en lenguaje llano, cada una con su ícono:
- "El tarwi **abona la tierra** para la cebada"
- "Aguanta la **helada de junio**"
- "La lluvia **alcanza**, casi sin riego"

Luego la evidencia, en dos gráficos simples:
- **Días con helada** por mes, barras de 12 meses, más oscuras cuanto más riesgo.
- **Lluvia y lo que pide cada cultivo**: dos barras por cultivo, verde la lluvia y ocre la
  demanda, con el veredicto "✓ Alcanza" o "Falta riego".

Cierra con el aviso honesto sobre fondo amarillo: "Antes de sembrar, consulta con tu técnico
agrario", y la nota de origen de los datos.

### 5 · ¿Cuándo sembrar?
Tarjeta verde oscuro con la respuesta concreta y grande: "Siembra el tarwi — 10 abr a 5 may",
y debajo el porqué en una frase. Luego un calendario de 12 columnas con cuatro filas (Lluvia,
Helada, y un renglón por cultivo), con la ventana de siembra recuadrada en amarillo.

Dos datos sueltos que importan: "Saca la papa hasta 5 abr" y "Primera helada ~20 may".
Botón "Avísame" para recordatorio, y vuelta al inicio.

## 4. Paleta (muestreada del prototipo)

| Uso | Color |
|---|---|
| Fondo de pantalla | `#F3F8EF` |
| Tarjetas | `#FFFFFF` |
| Verde de marca, botones, títulos | `#00733A` |
| Verde oscuro: tarjeta destacada, botón presionado | `#005C2E` |
| Verdes claros: chips, pestañas, fondo de íconos | `#E3F2DA`, `#DCEBD2`, `#D5E6CC` |
| Texto principal | `#10301C` |
| **Ruta Agua** | `#1E8F6A` |
| **Ruta Suelo** | `#21A159` sobre `#00733A` |
| **Ruta Cosecha** | `#C5DD73`, `#A0CF64` |
| Aviso "consulta con tu técnico" | fondo `#F3F5C8` |
| Cultivos, fondo de ícono | `#F6EBD3` |
| "Lo que pide" en las barras | `#B9A46A` |
| Helada, de mayor a menor | `#2F6F95`, `#7FB6D9`, `#B9D5E6`, `#E1EEF5` |
| Leguminosas, tarwi | `#5B6BC4`, `#8E9BDE`, `#E4E7F6` |

Regla de color: **el verde es la app, el azul es la helada, el ocre es la sed y el amarillo es
una advertencia.** Nunca se usa el rojo: asusta y no aporta.

Tipografía grande (título ~28 px, cuerpo ~16 px, mínimo 14 px), esquinas redondeadas de 16 a
20 px, y zonas tocables de 48 px o más, porque se usa con las manos sucias y al sol.

## 5. Qué calcula de verdad la app

Cada pantalla se apoya en un módulo existente:

| Pantalla | Fuente real |
|---|---|
| Altura de la chacra | Elevación MERRA-2 del encabezado de NASA POWER (`src/climate_profile.py`) |
| Días con helada por mes | Serie diaria POWER 1981-2024, contra la temperatura letal de cada cultivo |
| Lluvia por mes y su variabilidad | POWER y GPM IMERG mensual |
| Lo que pide cada cultivo | ET0 Penman-Monteith y Kc de FAO-56 (`src/water_requirement.py`) |
| Qué cultivos caben | Biblioteca EcoCrop: ciclo, temperaturas, lluvia anual, altitud (`src/crop_library.py`) |
| Las 3 rutas | Puntajes de agua, suelo y riesgo con frente de Pareto (`src/rotation_scores.py`) |
| Ventana de siembra | Calendario FAO de siembra y cosecha, donde existe para el país |

## 6. Límites que la app debe decir, no esconder

- **No reemplaza al agrónomo.** El aviso amarillo aparece en cada ruta, no en letra chica.
- **Cuando falta un dato, se dice.** El motor se abstiene antes que inventar: si no hay
  temperatura letal para un cultivo, la app muestra "No podemos evaluar la helada para este
  cultivo" en vez de un puntaje verde.
- **La resolución tiene un límite.** Las celdas de MERRA-2 miden unos 50 km y suavizan la
  montaña: en Huancabamba no registran heladas en 44 años, y eso no prueba que no hiele. En
  zonas de montaña la app debe mostrar esa advertencia junto al gráfico de heladas.
- **El calendario FAO no cubre Estados Unidos**, así que ahí la ventana de siembra se muestra
  vacía con su explicación, no estimada.
