# Plan: editor de símbolos profesional

Versión 2 (2026-09-26). Estado de partida: `editor.html` + `tools/editor.py` +
`editor.command`. Capas en polígonos, transformación por capa (x, y, r, sx, sy),
unir/restar, nodos, rectángulo/elipse, vista 3D aproximada, «Generar» con
`simbolo.exportar()`.

## Reglas del plan

1. **Nada toca un símbolo aprobado.** Toda comparación se hace con copias en un
   directorio temporal; `glb/` y `svg/` solo reciben lo que el usuario genera con un
   nombre nuevo. Un GLB que no salió del editor no se sobrescribe nunca (ya es así).
2. **Shapely manda.** La geometría que cuenta (la del GLB) la calcula siempre el
   servidor. Lo que calcula el navegador es una vista provisional y se rotula como tal
   hasta que llega la del servidor. Así no hay dos originales de la misma geometría:
   hay uno y una vista previa.
3. **Cada fase se cierra con dos criterios:** uno automático (en `tests/`) y una
   **tarea de usuario** con tiempo, hecha por ti en el editor. Si no pasan los dos, la
   fase no está hecha.
4. **Presupuesto de rendimiento** (lo mide `tests/rendimiento.mjs`): arrastrar la capa
   mayor de `shou-circular` a ≤ 16 ms por fotograma, mediana, sin contar el 3D. Se
   mide al final de cada fase; una fase que lo rompe no se cierra.
5. **Un commit por fase**, al pasar sus criterios; push solo a pedido.

## Medidas de partida (2026-09-26, Chrome headless con SwiftShader)

| Qué | xi-doble | shou-cruz | shou-circular |
|---|---|---|---|
| Arrastre: combinar + dibujar 2D, mediana | 42 ms | 74 ms | 86 ms |
| Arrastre, p90 | 75 ms | 188 ms | 115 ms |
| Combinar capas en el servidor (shapely) | — | — | 1,3 s |
| `exportar()` detallada / ligera | — | — | 3,9 s / 3,1 s |

SwiftShader comparte CPU con el renderizado y empeora las cifras, pero **hoy el
arrastre va a 12–24 fps**: el presupuesto de la regla 4 se incumple ya, y por eso F0
lo arregla antes de añadir nada.

## Orden y por qué

```
F0 Cimientos ─► F1 Cuchilla ─► F2 Precisión ─► F3 Selección múltiple ─► F4 Curvas ─► F5 Salida ─► F6 Pulido
                (valor pronto)  (imán, simetría)                          (lo arriesgado, con sondeo)
```

Lo que más cambia la experiencia (cortar en trazos, imán, simetría) va primero y
sobre polígonos, que ya funcionan. Las curvas van después: son la fase más arriesgada
y, si se atascan, lo anterior ya está entregado. Coste asumido: la cuchilla se adapta
en F4 para cortar curvas (partir un segmento Bézier en un parámetro t es De Casteljau,
un cálculo cerrado).

## Modelo y effort por etapa

Regla de siempre: Opus donde se define, se revisa contra una especificación o se
congela; Sonnet donde se implementa contra algo ya fijo. En trabajo web, donde se
puede medir, `medium` basta.

| Etapa | Modelo | Effort | Por qué |
|---|---|---|---|
| F0 implementación | Sonnet | medium | tareas acotadas y medibles |
| F1 corte exacto (geometría) | Opus | high | si deja grietas, la malla sale abierta sin avisar |
| F1 interfaz de la cuchilla | Sonnet | medium | |
| F2 simetría en vivo | Opus | high | fácil equivocarse con los huecos (ver F2) |
| F2 imán y guías | Sonnet | medium | |
| F3 | Sonnet | medium | |
| F4 sondeo y ajuste de curvas | Opus | high | decide el formato de datos de todo lo que viene |
| F4 interfaz (tiradores, pluma) | Sonnet | medium | |
| F5 | Sonnet | medium | reutiliza el verificador existente |
| F6 | Sonnet | medium | |
| Cierre de cada fase (revisión contra este plan) | Opus | high | las revisiones son donde aparecen los fallos |

Una sesión por etapa: el cambio de modelo cae en la frontera del commit.

---

## F0 · Cimientos  (1–2 sesiones)

| # | Cambio | Dónde |
|---|---|---|
| 0.1 | **Rendimiento del arrastre.** Durante un arrastre solo cambia una capa: se mueve su `<path>` con un atributo `transform` de SVG (sin recalcular su trazado) y el resultado combinado se recalcula como mucho una vez por `requestAnimationFrame`, y durante el arrastre sin las capas que no se tocan (se combinan una vez al empezar y se cachean). Trazados por capa cacheados por versión. | `editor.html` |
| 0.2 | **Sin internet:** three.js 0.170 y polygon-clipping 0.15.7 copiados a `vendor/`; el importmap apunta ahí. | `vendor/`, `editor.html` |
| 0.3 | **Parámetros en vez de globales:** `exportar(geo, nombre, fondo=FONDO, bisel=BISEL, color=COLOR, pasos=PASOS, esquina=ESQUINA, carpeta=RAIZ)`. `redibujar.py` y `letras.py` no cambian (usan los valores por defecto). El editor deja de tocar variables del módulo, así que dos «Generar» a la vez ya no se mezclan. `carpeta` permite exportar a un temporal (regla 1). | `tools/simbolo.py`, `tools/editor.py` |
| 0.4 | **Shapely manda (regla 2):** `POST /api/combinar` devuelve la geometría exacta en 2D; el cliente la pide tras 400 ms sin editar y descarta respuestas viejas (número de petición). Rótulo en el lienzo: «vista provisional» o «exacta». Si polygon-clipping lanza un error, el lienzo muestra la última geometría válida con el rótulo «sin actualizar» y la del servidor la sustituye. | `tools/editor.py`, `editor.html` |
| 0.5 | **Documentos a salvo:** guardado automático cada 30 s si hay cambios; cada guardado deja una copia en `editor/.historial/<nombre>/<fecha>.json` (se conservan las 20 últimas). `version: 1` en el documento y `migrar(doc)` en el cliente, para que F4 pueda cambiar el formato. | `tools/editor.py`, `editor.html` |
| 0.6 | **Pruebas en el repo:** `tests/test_editor.py` (pytest: ida y vuelta, nombres protegidos → 409, `exportar` con parámetros), `tests/editor-ui.mjs` (el guion de Chrome del 2026-09-26), `tests/rendimiento.mjs` (regla 4) y casos degenerados para polygon-clipping (anillo que se cruza a sí mismo, nodo arrastrado encima de otro, capa de área cero). `package.json` con `puppeteer-core` en `devDependencies`. | `tests/`, `package.json` |

**Hecho el 2026-09-26, con cuatro cambios sobre lo previsto:**
- **polygon-clipping eliminado** (0.2 y 0.4). El lienzo pinta las capas de abajo arriba
  («unir» en laca, «restar» del color del fondo): un píxel queda rojo si la última capa
  que lo cubre es «unir», que es exactamente unir y restar en orden. Las booleanas quedan
  solo en shapely; el navegador no tiene una segunda implementación. El 3D se construye
  con la geometría exacta del servidor (0,24–0,97 s tras 400 ms de pausa).
- **`make_valid` en vez de `buffer(0)`** para los anillos de cada capa: con un contorno que
  se cruza (pajarita), `buffer(0)` tiraba media forma sin avisar. Lo encontró la prueba
  de geometrías degeneradas.
- **El doble clic se decide al soltar:** con el editor rápido, clic + arrastre rápido
  contaba como doble clic y abría los nodos en vez de mover.
- **El 3D se dibuja solo cuando cambia algo** (cámara, modelo, tamaño), no en cada
  fotograma.

Medido: arrastre de `shou-circular` de 86 ms a 1,1 ms por fotograma (mediana).
Los 8 símbolos exportados con el `exportar` viejo y el nuevo dan mallas idénticas
vértice a vértice, detallada y ligera. Pruebas: `.venv/bin/pytest tests/` (16),
`npm run test:ui` (24 pasos, sin internet), `npm run test:rendimiento`.
**Corrección tras la primera prueba del usuario** («antes iba más fluido el 3D»).
Medido con la GPU real (Intel HD Graphics 6000; Chrome headless sin SwiftShader la usa):
girar el 3D iba a 60 fps, pero al arrastrar en 2D el 3D no cambiaba hasta 1,3 s después
de soltar (esperaba a la geometría exacta), y el arrastre 2D iba a 30 fps porque
repintaba la pieza entera en cada fotograma. Arreglos:
- **3D en directo por capas:** mientras se edita, cada capa que une es su propio sólido,
  extruido una vez y movido con su matriz; al llegar la exacta, la sustituye. Las
  restas no se ven en el 3D hasta entonces (rotulado).
- **La capa arrastrada viaja en su propio svg** (`#flotante`), movido con un transform
  CSS que aplica la tarjeta gráfica sin repintar; asas y contorno en otro (`#sobre`).
- **Sólidos provisionales preparados en tiempo libre** al llegar la exacta: si no, el
  primer fotograma del arrastre tardaba 50–70 ms (un tirón al empezar).
- Resultado: arrastre 2D con el 3D siguiéndolo a 16,7 ms por fotograma (p95), 60 fps.
  Prueba nueva: `npm run test:fluidez` (usa la GPU real, no SwiftShader).
- **Zoom y desplazamiento de la vista 2D** (segunda prueba del usuario: «el zoom se queda
  pegado»): el pellizco del trackpad llega como varios eventos de rueda por fotograma y
  cada uno redibujaba el lienzo (33–67 ms, 15–30 fps). Ahora, durante el gesto, lienzo y
  asas se escalan con un transform CSS una vez por fotograma y se redibujan nítidos
  150 ms después del último evento: 16,7 ms (p95). `will-change` solo durante el gesto:
  un A/B alternando mostró tirones de 133–350 ms al terminar el zoom con él permanente
  (2 de 3 pasadas) y ninguno así (3 de 3). `tam()` y `deEvento()` miden `#dos`,
  no el lienzo transformado. La prueba de interfaz comprueba que la vista durante el
  gesto coincide al píxel con la redibujada y que el punto bajo el cursor no se mueve.
- **Zoom del 3D suavizado** (tercera prueba del usuario: «el zoom del 3D aún no es 100 %
  fluido»). Iba a 60 fps, pero OrbitControls aplica cada evento de rueda de golpe y el
  trackpad los manda a ráfagas irregulares: la cámara avanzaba a saltos. Los fps no lo
  ven; se mide la variación del paso de cámara por fotograma con ráfagas irregulares
  (prueba (e) de `test:fluidez`): 1,49 con OrbitControls, 0,37 con zoom propio que
  persigue una distancia objetivo (constante 60 ms, misma sensibilidad).
- **El guardado automático ya no tapa «Generando GLB…»** (carrera que encontró la prueba).
- Lección de método: supuse una causa (fotogramas saltados en OrbitControls) y la medida
  la desmintió; se descartó sin aplicar. Medir antes de arreglar.

Pendiente para cerrar la fase: la tarea de usuario y la revisión de cierre (Opus).

**Criterio automático:**
- los 7 símbolos aprobados, reexportados con el `exportar` nuevo **a un temporal**,
  dan el mismo número de triángulos y las mismas métricas de `verificar.py` que los
  de `glb/` (ninguno se sobrescribe);
- `pytest tests/` y las dos pruebas de Chrome en verde; `rendimiento.mjs` ≤ 16 ms;
- con la red cortada, el editor abre y genera.

**Tarea de usuario (2 min):** abrir `shou-circular`, arrastrar la pieza mayor en
círculos 10 segundos; tiene que sentirse fluido. Cerrar la pestaña sin guardar,
reabrir: el guardado automático recupera la edición.

---

## F1 · Cuchilla: cortar en trazos  (2 sesiones)

Hoy `shou-cruz` y casi todos los caracteres son una sola capa: no se puede mover un
trazo. Esta fase lo resuelve sobre polígonos.

**Herramienta (K).** Se dibuja una polilínea (clic por punto, doble clic o Enter
termina, Esc cancela); corta las capas seleccionadas, o la que cruza si no hay
selección.

**Corte exacto, sin rendija** (en el servidor, regla 2). Restar una línea engordada
dejaría una rendija de ancho ε y al volver a unir las piezas quedaría una grieta en la
malla. En su lugar: la polilínea se prolonga hasta salir de la caja de la capa y se
cierra por fuera, formando una región R. Pieza A = capa ∩ R, pieza B = capa − R. Las
dos comparten el borde exacto y su unión devuelve la forma original. Cada componente
conexa pasa a ser una capa, con la operación de la original y el nombre «Pieza 1 · a»,
«Pieza 1 · b»… Las nuevas capas llevan su origen local en el centro de su caja.

**Separar automáticamente: sondeo de 1 h, luego se decide.** `redibujar()` ya
construye la retícula de rectas y arcos (`caras`); guardarla junto al SVG permitiría
proponer cortes por las uniones entre trazos. Pero `corregir` y los espejos cambian la
forma después de la retícula. Pregunta del sondeo: en `shou-cruz`, ¿qué fracción de
los cortes propuestos cae dentro de una unión real? Si es la mayoría, se añade
«Separar en trazos»; si no, solo cuchilla y se anota por qué.

**Criterio automático:** `shou-cruz` cortado en ≥ 6 capas y generado **sin mover
nada** → `verificar.py` lo APRUEBA contra `fuentes/shou-cruz.png` (prueba de que el
corte no deja grietas); mover una de esas capas cambia solo su zona (diferencia con el
original limitada a la caja de esa capa).

**Tarea de usuario (5 min):** hacer una variante de `shou-cruz` con el brazo derecho
más largo y generarla.

**Hecho el 2026-09-26** (falta la tarea de usuario):
- Cuchilla con `shapely.ops.split`, sin prolongar la línea: corta solo donde se dibuja de
  lado a lado (prolongarla cortaría trazos lejanos). Clic por punto; doble clic o Enter
  termina; Esc cancela. Cada pieza, una capa `Nombre · a`, `· b`…
- **Fallo encontrado por el criterio:** `shou-cruz` cortado en 27 piezas y generado sin
  mover nada salía RECHAZADO (IoU 0,9738). Las piezas vuelven del navegador con el
  borde común desplazado ~1e-17 (coordenadas locales); la unión dejaba una grieta de
  ancho cero y el redondeo en planta se comía 5e-3 de área junto a ella. Arreglo:
  `set_precision(1e-9)` por capa antes de combinar. Ahora APROBADO.
- **Fallo de F0 encontrado aquí:** el guardado al cerrar la pestaña nunca funcionó con
  símbolos grandes: `sendBeacon` admite 64 KB y `shou-cruz` ocupa 72, `shou-circular` 105.
  Ahora se guarda 1,5 s después de cada cambio (el historial copia como mucho cada 30 s)
  y al cerrar se manda un parche: las capas sin cambios en nodos van sin ellos.
- Pruebas: corte + generar → APROBADO; mover una pieza cortada solo cambia su zona (fuera,
  franjas de ~3e-6, 300 veces más finas que un píxel del verificador); en la interfaz,
  cortar con Enter y con doble clic sin cambiar el área; cierre con documento > 64 KB.

**Corrección tras la prueba del usuario** («no funciona la función corta»). Su documento
guardado mostraba una sola capa y la pieza movida: el corte nunca se aplicó. Tres causas:
- **Cortar arrastrando no existía:** solo clic por punto; un arrastre dejaba un punto.
  Ahora arrastrar corta a mano alzada al soltar; el clic por punto sigue.
- **Un corte solo no suelta un trazo en símbolos entrelazados:** en `shou-cruz` casi todo
  forma anillos, y el editor decía «no cruza ninguna forma», lo cual era falso. Ahora el
  corte que atraviesa sin separar queda como **costura** (línea roja discontinua, en
  coordenadas de la capa, se deshace con ⌘Z y se quita desde el panel) y se suma a los
  siguientes; las caras salen de `polygonize` del contorno y todas las líneas. Prueba: el
  anillo de `shou-cruz`, cortado arriba (costura) y abajo, se parte en dos mitades que
  generadas siguen APROBADAS.
- **La cuchilla solo cortaba la capa seleccionada**, y tras cada corte quedaba una
  seleccionada: el segundo corte en otro sitio no hacía nada. Ahora corta todo lo visible
  que cruza, como la de Illustrator.
- Además: un extremo que acaba encima del trazo se prolonga hasta salir de él (≤ 0,15); el
  guardado automático ya no tapa el mensaje de un corte.

**Sondeo «separar automáticamente» (hecho).** En vez de la retícula de `redibujar.py`,
se prolongan los bordes rectos del contorno final (≥ 0,03) por dentro del material hasta
que salen (≤ 0,12): una unión en T es justo donde el borde de un trazo atraviesa otro.
- `shou-cruz`: 40 cortes propuestos, los 40 en uniones reales (revisados uno a uno).
- `xi-doble`: 56, todos en cruces o uniones; 3 pares casi paralelos a ~0,015 (3/37,
  16/40, 27/31) que dejarían una astilla entre ellos.
- Aplicarlos todos a la vez da ~100 fragmentos (cada cruce, un cuadrado suelto): para
  mover un trazo habría que seleccionar varios (F3) y no hay «combinar capas».
- **Decidido (usuario, opción A): sugerencias en la cuchilla**, no «separar todo».

**Sugerencias de corte (hecho 2026-09-26).** `/api/sugerencias` (0,04–0,13 s) al entrar
en la cuchilla y tras cada cambio; líneas azules, clic = ese corte; la cuchilla sigue
activa entre cortes (Esc vuelve a Mover). Pares casi paralelos fundidos: en `xi-doble`
eran 4, no 3 (el sondeo contó 27/31 como uno y eran 27/6 y 31/14): 56 → 52.
- **Astillas:** cortar una unión por sus dos lados deja un cuadradito en el redondeo de la
  esquina (0,006 × 0,006); un trozo de < 1e-4 se funde con su vecina.
- **Piezas del corte sin redondear:** un corte tangente al redondeo de una esquina deja un
  canal casi sin anchura y redondear a 6 (o 9) decimales lo cruzaba consigo mismo (pieza
  inválida, pegada al resto por un punto). Ahora se envían con precisión completa.
- Criterios: aplicar las 40 sugerencias de `shou-cruz` → piezas válidas y APROBADO sin
  mover nada; la barra superior derecha se suelta con 3 clics (también en la interfaz).

**Cortes precisos (hecho 2026-09-26, pedido del usuario: «esta manera de cortar no es precisa»).**
- Arrastrar traza una **recta** (de donde se pulsa a donde se suelta), no a mano alzada.
- **Imán** con guías rosas: extremos de los bordes rectos (8 px) > cruce de dos rectas
  (8 px) > una recta (6 px); rectas = bordes rectos (`bordes_rectos`, junto con las
  sugerencias), sus prolongaciones y los ejes. ⌘ lo apaga. Cada borde guía solo hasta
  0,15 más allá de sus extremos: prolongados sin límite, cruces de bordes lejanos salían
  por todo el lienzo y ganaban al eje (medido: un punto junto al eje enganchaba al cruce
  de dos diagonales de la otra punta del símbolo).
- **Mayús**: ángulo en múltiplos de 15° desde el punto anterior; `cos(90°)` da 6e-17, se
  redondea a 0 para que la vertical sea exacta.
- Clic en una sugerencia la aplica; arrastrar empezando encima traza una línea propia.
  Esc cancela la línea sin salir de la cuchilla.
- Parte de F2 queda adelantada aquí (imán y guías para la cuchilla); F2 lo extenderá a
  mover capas y nodos reutilizando `iman()`.

---

## F2 · Precisión: imán, guías y simetría en vivo  (2 sesiones)

**Imán.** Al mover una capa, un nodo o un punto de la cuchilla. Candidatos: ejes
(x = 0, y = 0), centros y bordes de las cajas de las otras capas, nodos de las otras
capas y el círculo de diámetro 1. Umbral: 6 px de pantalla; gana el más cercano por
eje. Guías rosas mientras actúa; ⌘ mantenido lo desactiva; ⇧ al mover restringe a un
eje. Para no romper el presupuesto de rendimiento, los candidatos se calculan una vez
al empezar el arrastre y se buscan en una rejilla espacial.

**Simetría en vivo.** `doc.simetria`: `ninguna | lr | ab | doble`, y `doc.mitad`
(qué lado manda). Resultado = mitad que manda ∪ su reflejo, recortando por el eje,
igual que `espejo_ab` y `espejo_lr` de `redibujar.py`. **No vale** `resultado ∪
reflejo(resultado)`: un hueco hecho en un lado quedaría tapado por el lado macizo del
otro. La mitad que no manda se ve atenuada. La regla la aplica el servidor en
`geometria()` (regla 2); el navegador la imita solo para la vista provisional.

**Criterio automático:** con `simetria=lr` se resta una elipse en la mitad que manda →
el GLB tiene el hueco en los dos lados y el IoU de su silueta con su reflejo es
≥ 0,999; arrastrar una capa a menos de 6 px del eje la deja en x = 0 exacto;
`rendimiento.mjs` sigue ≤ 16 ms con el imán activo.

**Tarea de usuario (5 min):** en `xi-doble` con simetría `lr`, abrir un hueco
redondo en el centro de la mitad izquierda y comprobar que sale igual en la derecha.

---

## F3 · Selección múltiple y alineación  (1 sesión)

- Selección = conjunto de ids. ⇧ + clic suma o quita; arrastrar en vacío = recuadro
  (selecciona lo que toca, como Figma); ⌘A todo.
- Una caja común en ejes del mundo; mover y rotar se aplican a cada `t`. **Escalar sin
  proporción una selección con capas giradas no cabe en (x, y, r, sx, sy)** (sale
  cizalla): en ese caso se hornea la transformación en los nodos de esas capas y su
  `t` vuelve a identidad. Con ⇧ (proporcional) no hace falta hornear.
- Panel: alinear izquierda, centro, derecha, arriba, medio y abajo; distribuir en
  horizontal y en vertical; X, Y, W, H de la selección entera.
- Sin grupos: combinados con unir/restar abren preguntas de orden que todavía no
  compensan. Se reconsidera en F6 si la tarea de usuario lo pide.

**Criterio automático:** seleccionar 3 capas con recuadro, rotar 30°, escalar con ⇧ y
deshacer vuelve al JSON anterior idéntico (comparación de texto); alinear al centro
deja los tres centros en el mismo X con error < 1e-9.

**Tarea de usuario (3 min):** cortar `shou-cruz` en trazos (F1), seleccionar los
cuatro ganchos y alinearlos simétricamente con la ayuda del imán.

---

## F4 · Curvas Bézier  (3 sesiones, empieza por un sondeo)

Hoy un arco son cientos de nodos. Es la fase más arriesgada: cambia el formato de los
datos.

**4.0 Sondeo (1 sesión, Opus): medir antes de prometer.** Script en Python
(`tools/curvas.py`, junto a `ajustar_circulo` y numpy, y comprobable contra el
verificador). Para cada uno de los 7 símbolos: partir los anillos en esquinas (giro
> 30°); ajustar cada tramo con recta, luego arco (mínimos cuadrados), luego Bézier
cúbica (Schneider); tolerancia 0,0005 (0,05 % del diámetro, por debajo del contorno
p95 del verificador). Se miden: nodos antes y después, error máximo, tiempo. **Con esos
números se fija el criterio de 4.2**; hasta entonces no hay objetivo de nodos.

**4.1 Modelo.** Cada anillo pasa a ser una lista de nodos
`{p:[x,y], ent:[dx,dy]|null, sal:[dx,dy]|null, tipo:"vivo"|"suave"|"espejo"}`
(tiradores relativos, en coordenadas locales). Una sola función `aplanar(anillo, tol)`
convierte a polígono para la vista; el servidor recibe los nodos y aplana él mismo
(regla 2). `migrar()` convierte documentos `version: 1` (cada punto = nodo vivo).

**4.2 Importar.** Al abrir un SVG denso, el servidor aplica el ajuste de 4.0. Si un
tramo no ajusta dentro de la tolerancia, se queda en polilínea: peor caso = como hoy.

**4.3 Interfaz.** Nodos cuadrados y tiradores redondos; ⌥ + arrastrar rompe la
simetría del nodo; doble clic en un nodo alterna vivo/suave; **pluma (P)**: clic =
nodo vivo, clic y arrastrar = nodo suave, clic en el primero cierra. La cuchilla
corta curvas partiéndolas por De Casteljau. «Simplificar nodos» desaparece.

**Criterio automático:** los 7 símbolos, importados a curvas y generados sin tocar,
siguen APROBADOS por `verificar.py` (exportados a un temporal, regla 1); nodos por
debajo del objetivo fijado en 4.0; un documento `version: 1` se abre y genera igual;
`rendimiento.mjs` ≤ 16 ms.

**Tarea de usuario (5 min):** dibujar con la pluma una forma con curvas (un pétalo,
una hoja), unirla a `fu-circular` y generarla.

---

## F5 · Salida y verificación de lo editado  (1 sesión)

- **Tres versiones en un clic:** detallada, ligera (`pasos=3, esquina=4`, como
  `--ligera`) y web (`npx -y @gltf-transform/cli@4 optimize … --compress meshopt
  --simplify false`).
- **Verificación propia, sin copiar código:** `revisar_malla()` de `verificar.py`
  (malla cerrada, canto en todas las piezas, normales, material) y el aviso de trazo
  fino de `letras.py` (el redondeo se come > 3 % del área), movido a `simbolo.py` para
  que lo usen los dos. Resultado en el editor como lista PASA/FALLA.
- Si algo FALLA: se escribe solo la detallada, para poder mirarla, y el estado dice
  RECHAZADO; ni ligera ni web (regla de la skill: nada se entrega rechazado).
- **3D exacto en segundo plano:** tras 1 s sin editar, `/api/previa` exporta a un
  temporal (unos 5 s en el peor símbolo medido) y el visor 3D lo muestra; si hay otra
  edición en medio, la respuesta vieja se descarta. Rótulo «3D provisional» o «exacto».

**Criterio automático:** un trazo de 0,01 de ancho → RECHAZADO por trazo fino, sin
versión web; un símbolo correcto → tres archivos, y `visor.html?s=web/<nombre>-ligera`
lo carga; el rótulo pasa solo a «exacto» tras dejar de editar.

**Tarea de usuario (3 min):** generar la variante de F1 en las tres versiones y abrir
la web en el visor.

---

## F6 · Pulido  (1 sesión)

- Importar un SVG externo (M/L/H/V/C/S/Q/T/A/Z al modelo de F4) y exportar SVG con
  curvas.
- Reordenar capas arrastrando; deshacer también la selección; zoom «ajustar» (⇧1) y
  «100 %» (⇧0); panel de atajos (?).
- README: sección «Editor», en inglés como el resto. La skill `simbolos-3d`: una fila
  en su tabla de archivos que apunta a este documento, sin copiar la guía.

**Criterio automático:** un SVG con arcos y cúbicas importado → IoU ≥ 0,999 contra su
renderizado; todas las pruebas en verde.

**Tarea de usuario (5 min):** importar un logotipo exportado de Figma y generarlo.

---

## Decisiones que son tuyas (con mi recomendación)

1. **`package.json` con `puppeteer-core` en el repo** (F0). Recomiendo sí, en
   `devDependencies`: sin eso las pruebas de interfaz viven fuera del repo y se
   pierden.
2. **Resultado RECHAZADO** (F5): recomiendo escribir la detallada marcada y nada más,
   no bloquear del todo: hay que verla para arreglarla.
3. **Separar automáticamente** (F1): decidir con el número del sondeo, no antes.

## Estimación

11–13 sesiones: F0 1–2 · F1 2 · F2 2 · F3 1 · F4 3 · F5 1 · F6 1. F0–F2 (5–6
sesiones) ya entregan lo que más se nota; F4 concentra el riesgo y va detrás a
propósito.
