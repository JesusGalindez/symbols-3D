# Plan: lo mejor de Figma en el editor de símbolos

Versión 2 (2026-09-27). Punto de partida: el editor tras F6 (`docs/PLAN-EDITOR.md`):
capas con curvas Bézier, unir/restar, mover/escalar/girar, rectángulo, elipse, pluma,
cuchilla con sugerencias, nodos y tiradores, imán, simetría en vivo, selección múltiple
con alinear y distribuir, deshacer, guardado automático, importar y exportar SVG, ⇧1/⇧0
y panel de atajos.

La pregunta de este plan no es «qué tiene Figma», sino **qué de Figma hace mejor un
símbolo 3D**. Figma es una herramienta de interfaces; muchas de sus funciones estrella
(auto layout, prototipos, variables) no significan nada para una pieza de laca. Lo que sí
importa: los trazos, la edición vectorial, las operaciones booleanas, la precisión y el
flujo del día a día (portapapeles, atajos, medir).

**Cambios de la versión 2** (revisión crítica de la 1):
- **Trazos antes que grupos.** La versión 1 ponía los grupos primero con un argumento
  falso («un trazo contorneado es, por dentro, un grupo»): contornear da una capa
  rellena normal y una capa de trazo es una capa con un campo más. Los trazos, lo más
  útil para caracteres chinos, pasan de la quinta fase a la segunda.
- **Caminos abiertos** como requisito explícito, con sus pruebas, en la fase de trazos:
  hoy todo el editor supone anillos cerrados.
- **Importar los trazos de un SVG**, que hoy se ignoran (la principal limitación de F6).
- **Regla 9 corregida:** los campos opcionales no cambian la versión del formato; solo
  la cambia el paso de lista a árbol.
- **G0 nueva:** arreglar lo que ya está roto y cerrar F6 antes de construir encima.
- **Estimaciones con rango**; la edición vectorial fina se parte en dos fases.
- Decisiones nuevas (navegadores, escalar el grosor), memoria del deshacer medida,
  tareas de usuario con un resultado comprobable.
- **Simetría rotacional** como fase opcional: no es de Figma, pero la piden los sellos
  circulares.

## Reglas del plan

Las cinco de `PLAN-EDITOR.md` siguen vigentes: nada toca un símbolo aprobado; shapely
manda (el navegador solo previsualiza); cada fase se cierra con un criterio automático y
una tarea de usuario; presupuesto de rendimiento (arrastrar la capa mayor de
`shou-circular` ≤ 16 ms por fotograma, mediana); un commit por fase. Y además:

6. **Atajos idénticos a Figma**, salvo los conflictos de la tabla de abajo, que se
   deciden una vez y se documentan en el panel «?».
7. **Toda geometría nueva pasa por el servidor.** Trazos, radios de esquina, booleanas,
   texto: el navegador enseña una aproximación rotulada como provisional y el servidor
   da la exacta, la misma que va al GLB. Nada nuevo se calcula solo en JavaScript.
8. **Cada fase se prueba sobre tres símbolos reales:** `xi-doble` (simple, simetría
   izq.↔der.), `shou-cruz` (uniones en T, cuchilla) y `shou-circular` (el más pesado,
   5159 nodos densos). Una función que solo funciona con rectángulos no está hecha.
9. **Los campos nuevos son opcionales y no cambian la versión del formato** (`bloqueada`,
   `trazo`, `radio`, `guias`…): un documento sin ellos se abre igual que hoy y uno con
   ellos no se abre en un editor anterior sin avisar (el servidor rechaza campos que no
   conoce en vez de ignorarlos). **Solo el paso de lista a árbol (G5) sube la versión, a
   la 3**, con migración desde la 1 y la 2 comprobada: la planta de un documento migrado
   es idéntica a la de antes (diferencia simétrica de área < 1e-12).
10. **Navegador de referencia: Chrome** (con él se prueba todo). Safari y Firefox, lo
    mejor posible: nada puede depender de algo que solo tenga Chrome sin una alternativa
    que funcione en los tres (p. ej. el portapapeles, G1).
11. **Una tarea de usuario se cumple con un resultado comprobable**, casi siempre
    «generado y APROBADO», además del tiempo.

## De dónde sale la prioridad

La columna «Uso» es **una estimación**, no un dato: Figma no publica estadísticas de uso
por función. Sale de los atajos que más repiten su documentación y las guías de atajos, y
de los tutoriales de iconografía. Al preparar esta versión el proxy de red no dejó abrir
las páginas de ayuda de Figma: se trabajó con los extractos de búsqueda y lo conocido.

**Antes de G1, un ejercicio de 15 minutos (parte de G0):** editar un símbolo real en el
editor (p. ej. rehacer un gancho de `shou-cruz`) y apuntar cada «aquí me falta X». Lo
apuntado **manda sobre esta tabla**: una función que aparezca ahí sube de prioridad, y
una fase entera sin ninguna candidata se reconsidera.

## Inventario: Figma frente al editor

Valor: cuánto ayuda a hacer un símbolo 3D.

| Función de Figma | Atajo en Figma | ¿La tenemos? | Uso (estimado) | Valor aquí | Fase |
|---|---|---|---|---|---|
| Copiar, cortar, pegar | ⌘C ⌘X ⌘V | no | muy alto | alto | G1 |
| Pegar en su sitio / sobre la selección | ⇧⌘V | no | alto | alto | G1 |
| Pegar un SVG copiado de Figma («Copy as SVG») | ⌘V | no (solo importar archivo) | alto | muy alto | G1 |
| Duplicar arrastrando con ⌥ | ⌥ + arrastrar | no | muy alto | alto | G1 |
| Duplicar repitiendo el último desplazamiento | ⌘D | a medias (desplazamiento fijo) | alto | medio | G1 |
| Voltear horizontal / vertical | ⇧H ⇧V | no | alto | alto | G1 |
| Zoom: todo / selección / 100 % / acercar / alejar | ⇧1 ⇧2 ⇧0 ⌘+ ⌘− | ⇧1 y ⇧0 (⇧1 hace lo de ⇧2 con selección) | muy alto | medio | G1 |
| Bloquear / ocultar / renombrar capa | ⇧⌘L ⇧⌘H ⌘R | ocultar (clic en el ojo), renombrar (doble clic) | alto | medio | G1 |
| Seleccionar hermana siguiente / anterior | Tab ⇧Tab | no | medio | medio | G1 |
| Trazo: grosor, extremos, uniones | — | no | muy alto | **muy alto** | G2 |
| Contornear trazo | ⇧⌘O | no | alto | **muy alto** | G2 |
| Caminos abiertos (pluma sin cerrar) | Esc / Enter | no | alto | muy alto | G2 |
| Importar trazos de un SVG | — | no (se ignoran) | alto | muy alto | G2 |
| Medir distancias | ⌥ con selección | no | muy alto | alto | G3 |
| Reglas y guías arrastrables | ⇧R | no | medio | medio | G3 |
| Operaciones en los campos (`0,2*3`, `+0,01`) | — | no | medio | medio | G3 |
| Unir / restar | ⌥⇧U ⌥⇧S | sí, por orden de capas | muy alto | — | — |
| Intersecar / excluir | ⌥⇧I ⌥⇧E | no | alto | alto | G4 |
| Aplanar | ⌘E | no | alto | alto | G4 |
| Grupos | ⌘G ⇧⌘G | no | muy alto | alto | G5 |
| Grupos booleanos no destructivos | menú booleano | no (la pila entera es una booleana) | alto | alto | G5 |
| Selección profunda / entrar en el grupo | ⌘ + clic, doble clic | no | alto | alto | G5 |
| Radio de esquina (por capa y por nodo) | — | no | muy alto | alto | G6 |
| Herramienta curvar (⌘ + arrastrar un tramo) | ⌘ | no | alto | alto | G6 |
| Tipos de nodo en el panel | — | solo con doble clic y ⌥ | medio | medio | G6 |
| Varios nodos a la vez (mover, escalar, borrar) | ⇧ + clic | no (un nodo) | alto | alto | G7 |
| Lazo para nodos | Q | no | medio | medio | G7 |
| Unir extremos / fusionar nodos | ⌘J ⇧⌘M | no | medio | medio | G7 |
| Lápiz (a mano alzada) | ⇧P | no | medio | medio | G7 |
| Polígono y estrella | — | no | medio | medio | G8 |
| Arco de elipse (inicio, barrido, radio interior) | — | no | medio | alto (anillos, sellos) | G8 |
| Línea y flecha | L ⇧L | no | alto | medio | G8 |
| Texto a contornos | T, luego aplanar | no (solo `letras.py` por línea de órdenes) | alto | alto | G8 |
| Historial de versiones con nombre | ⌥⌘S | copias en `editor/.historial`, sin interfaz | medio | medio | G9 |
| Exportar la selección / PNG | ⇧⌘E | SVG del diseño entero | alto | medio | G9 |
| Componentes e instancias | ⌥⌘K | no | muy alto | medio | G10 (opcional) |
| *(no es de Figma)* Simetría rotacional y repetición radial | — | solo izq.↔der. y arriba↔abajo | — | alto (sellos) | G11 (opcional) |

**Fuera, a propósito:** auto layout, restricciones, prototipos, modo desarrollo,
variables y estilos de color (el GLB tiene un material), efectos y degradados,
multijugador y comentarios, páginas y marcos (un documento = un símbolo), redes
vectoriales (un nodo con tres tramos no tiene relleno bien definido; los anillos
cerrados son lo que garantiza una malla estanca) y el cubo de pintura.

## Conflictos de atajos

| Atajo | En Figma | Aquí | Decisión |
|---|---|---|---|
| K | escalar con todo (herramienta) | cuchilla (desde F1) | se queda la cuchilla; escalar el grosor con la forma es una opción (ver «Decisiones») |
| ⇧1 | ajustar todo | ajustar lo visible **o la selección** (F6) | como Figma: ⇧1 todo, ⇧2 selección |
| ⌘R | renombrar | el navegador recarga | se intercepta (`preventDefault`) solo con el foco en el editor |
| ⌘+ ⌘− | zoom del lienzo | zoom de la página | se interceptan igual |
| Enter | entrar en el grupo / nodos | nodos | Enter entra en el grupo; en una capa, nodos (igual que Figma) |
| Esc (pluma) | termina el camino abierto | cancela el dibujo | como Figma: con ≥ 2 nodos deja un camino abierto; con 1, cancela |

---

## Orden y por qué

```
G0 Cimientos ─► G1 Portapapeles ─► G2 Trazos ─► G3 Medir ─► G4 Booleanas ─► G5 Grupos (v3) ─► G6 Esquinas ─► G7 Nodos ─► G8 Formas ─► G9 Versiones
(tests, F6)     y atajos           (caminos                                 (el cambio de      y curvar       varios,      y texto
                                    abiertos)                                formato)                          lápiz
                                                                                        opcionales: G10 Componentes · G11 Simetría rotacional
```

G0 deja las pruebas fiables: sin eso, cada fase siguiente arrastra fallos que no son
suyos. G1 es lo que se usa cada minuto y no tiene riesgo. G2 es lo que más cambia cómo se
dibuja un carácter, y no necesita grupos. G3 y G4 no tocan el formato. G5 concentra el
riesgo (lista → árbol) y va cuando lo demás ya está entregado, como las curvas en F4.

---

## G0 · Cimientos  (0,5–1 sesión)

- **Pruebas que fallan por el entorno, no por el código:**
  `test_simetria_no_degrada_un_simbolo_simetrico` se omite si falta
  `fuentes/xi-doble.png` (como ya hace `test_ida_y_vuelta_sigue_aprobado`); el visor usa
  `vendor/` como el editor (hoy carga three.js de jsdelivr y la prueba del visor falla sin
  internet), añadiendo a `vendor/` el `meshopt_decoder.module.js` que le falta.
- **Integración continua** (GitHub Actions): pytest y `test:ui` en cada push, con Chrome
  sin ventana. El README ya documenta los dos comandos.
- **Medir la memoria del deshacer:** hoy guarda hasta 200 copias completas del documento
  en texto. Medir en `shou-circular` (el documento abierto como curvas y tras cortarlo con
  las 40 sugerencias). Si 200 pasos pasan de 100 MB, se pasa a guardar diferencias entre
  pasos antes de G5, que agranda los documentos.
- **Campos desconocidos** (regla 9): hoy el servidor ignora lo que no conoce. Pasa a
  rechazar al guardar y generar un documento con campos de capa que no conoce, diciendo
  cuáles, para que un editor viejo no borre en silencio un `trazo` al guardar.
- **Cerrar F6:** su tarea de usuario (importar un logotipo de Figma y generarlo).
- **El ejercicio de 15 minutos** de «De dónde sale la prioridad», con lo apuntado en este
  documento.

**Criterio automático:** pytest entero en verde (sin fallos, solo omitidas las que
necesitan imágenes no publicadas); `test:ui` entero en verde **sin internet**; la
integración continua en verde en `main`; la memoria del deshacer medida y apuntada aquí.

**Tarea de usuario (20 min):** la de F6 (hecho si: el logotipo sale APROBADO) y el
ejercicio de 15 minutos (hecho si: hay una lista de «me falta X» en este documento).

---

## G1 · Portapapeles y atajos de Figma  (1–1,5 sesiones)

- **⌘C / ⌘X / ⌘V** de capas, con los eventos `copy`/`paste` del navegador (no una
  variable interna): así se puede copiar entre dos pestañas del editor. En el
  portapapeles van dos tipos: `text/plain` con un SVG de las capas (lo que Figma lee al
  pegar, y lo que funciona en cualquier navegador) y `web application/x-simbolos` con el
  JSON de las capas (lo que lee el editor, sin perder nada; si el navegador no lo admite,
  se pega el SVG y se pierden solo los nombres). Pegar pone las capas encima de la
  selección, desplazadas 0,02 si caerían justo encima de las originales; **⇧⌘V** las
  pega en su sitio.
- **Pegar un SVG** (de Figma con «Copy as SVG», de Illustrator o de un editor de texto):
  si el `text/plain` empieza por `<svg`, va a `/api/importar` y las capas se añaden.
  Escala: la de la importación de F6 (diámetro 1) si el documento está vacío; si no,
  según la decisión 1.
- **⌥ + arrastrar** duplica y mueve la copia (con imán). **⌘D** repite el último
  desplazamiento: duplicar, mover, ⌘D, ⌘D… hace una fila equiespaciada, como en Figma.
- **⇧H / ⇧V** voltean la selección respecto al centro de su caja (con varias capas, las
  posiciones también se reflejan). Se hornea como la escala de F3: `sx`, `sy` negativos
  dejarían los anillos al revés y la cuchilla trabaja en el mundo.
- **Zoom**: ⇧1 todo lo visible, ⇧2 la selección (corrige F6), ⇧0 100 %, ⌘+/⌘− por
  pasos de ×2 centrados en el centro de la vista.
- **Capas**: ⇧⌘L bloquea (no se elige desde el lienzo ni con el recuadro; candado en
  la lista), ⇧⌘H oculta, ⌘R renombra, Tab / ⇧Tab eligen la capa de encima / debajo.

**Criterio automático** (`tests/editor-ui.mjs`): copiar tres capas de `xi-doble` y
pegarlas en otra pestaña da el mismo JSON de capas salvo ids y nombres; con solo el
`text/plain` (simulando un navegador sin el tipo propio), la misma planta (IoU ≥ 0,999);
⇧⌘V deja `t` idéntico; pegar el SVG que exporta F6 de `shou-cruz` en un documento vacío
da una planta con IoU ≥ 0,999 contra la original; ⌥ + arrastrar crea exactamente una
capa; ⇧H dos veces deja el JSON idéntico (comparación de texto); una capa bloqueada no se
elige ni con clic ni con recuadro; presupuesto de 16 ms.

**Tarea de usuario (3 min):** copiar un icono en Figma («Copy as SVG»), pegarlo en el
editor y colocarlo en el centro de `xi-doble`. Hecho si: generado y APROBADO.

---

## G2 · Caminos abiertos y trazos  (2–3 sesiones, empieza por un sondeo)

Los caracteres chinos son trazos. Hoy un trazo se dibuja como su contorno, nodo a nodo;
con esta fase se dibuja **su esqueleto** y el grosor lo pone el servidor.

### Caminos abiertos (lo que la fase necesita antes que nada)

Hoy todo supone anillos cerrados. Un camino abierto es una capa con `abierto: true`
(todos sus anillos son caminos: el último nodo no se une con el primero). **Solo puede
existir con `trazo`**: sin grosor no rellena nada, y el servidor rechaza una capa abierta
sin trazo. Lo que cambia, uno por uno, con su prueba:

| Qué | Cambio | Prueba |
|---|---|---|
| `aplanar` (Python y JS) | sin el tramo del último nodo al primero | paridad Python ↔ JS como la de F4, con un camino abierto |
| Pluma | Esc o Enter con ≥ 2 nodos dejan un camino abierto con el trazo por defecto | 3 clics + Esc → capa abierta de 3 nodos |
| Dibujo 2D y caja | trazado sin `Z`; la caja incluye el grosor | la caja de un segmento horizontal de ancho 0,03 mide 0,03 de alto |
| Nodos | sin tramo de cierre; los extremos se pueden alargar con la pluma (clic en un extremo y seguir) | alargar un camino de 2 nodos a 4 |
| Cuchilla | **sobre una capa de trazo, corta el esqueleto** (De Casteljau en el cruce, como F4.3) y deja dos capas de trazo con el mismo grosor; la línea que no cruza el esqueleto pero sí el grosor no corta, y lo dice | un trazo recto cortado por la mitad da dos de área L/2 · a cada uno (extremos planos) |
| Imán | los extremos de los caminos son objetivos | un extremo soltado a 3 px de otro queda encima exacto |
| Vista 3D provisional | no se extruye un camino: se usa el contorno aproximado del SVG hasta que llega la malla exacta, rotulado | la etiqueta dice «provisional» hasta la exacta |
| Parche de `pagehide`, exportar, deshacer | sin cambios de lógica; pruebas con capas abiertas | los de F5 y F6 con una capa de trazo |

**Sondeo (primera media sesión):** `LineString(...).buffer()` de shapely sobre los
caminos aplanados de los 4 trazos horizontales de `xi-doble` redibujados a mano como
esqueletos: tiempo en `/api/combinar` (< 50 ms por trazo) y validez de la forma con
uniones en inglete a 10° (zigzag). Si el inglete sale inválido, se limita como Figma
(`mitre_limit` = 4) y se prueba otra vez.

### Trazos

- **Capa de trazo**: `trazo: {"ancho": 0.03, "extremos": "redondo" | "plano" |
  "cuadrado", "uniones": "redonda" | "inglete" | "bisel", "inglete": 4, "posicion":
  "centro" | "dentro" | "fuera"}`. El servidor la convierte en forma con `buffer(ancho /
  2, cap_style, join_style, mitre_limit)` sobre el camino aplanado, y a partir de ahí es
  una capa más (unir, restar, más adelante intersecar, excluir, grupos). «Dentro» y
  «fuera» solo en caminos cerrados, como en Figma.
- **Panel «Trazo»**: grosor, extremos, uniones, posición; con varias capas, a todas.
- **Contornear trazo (⇧⌘O)**: el trazo pasa a capa rellena, con curvas
  (`curvas.ajustar_anillo`), para editar sus nodos a mano (p. ej. afinar un extremo como
  un pincel).
- **Desplazar contorno** (engrosar / adelgazar una capa ± d): `buffer(±d)` y reajuste a
  curvas. Enlaza con F5: cuando «Generar» rechaza por **trazo fino**, el panel ofrece
  «Engrosar lo necesario», que calcula la d mínima que aprueba (búsqueda binaria sobre
  `simbolo.area_perdida`) y la aplica a las capas culpables.
- Vista provisional: el trazo se pinta con `stroke-width` del SVG (exacto salvo las
  uniones en inglete muy agudas); la exacta llega del servidor como siempre.

### Importar y exportar trazos

- **Importar** (`tools/leer_svg.py`): un elemento con `stroke` y `fill="none"` pasa a
  capa de trazo, con `stroke-width`, `stroke-linecap` y `stroke-linejoin` traducidos;
  con relleno y trazo, dos capas (el relleno y encima el trazo, «unir»). El grosor se
  escala con la transformación (raíz del determinante); con una escala no uniforme el
  grosor sería variable, y se contornea en el importador con la forma exacta en vez de
  aproximarlo. `<line>` entra como camino abierto.
- **Exportar**: en el modo por capas de F6, una capa de trazo sale como `<path
  fill="none" stroke-width="…">` (editable en Figma); con restas o simetría, dentro de
  la forma combinada, como hasta ahora.

**Criterio automático:** un trazo recto de ancho 0,03 y extremos planos tiene exactamente
el área L × 0,03 (< 1e-9); con extremos redondos, L × 0,03 + π · 0,015² (< 1e-5, por el
aplanado); contornear un trazo curvo y volver a combinar da IoU ≥ 0,999 con el trazo;
redibujar con trazos los 4 trazos horizontales de `xi-doble` y generar da **APROBADO**;
«Engrosar lo necesario» convierte en APROBADO el caso de 0,01 de
`test_generar_rechaza_un_trazo_fino` con el menor d que aprueba (± 1e-4); un SVG con un
logotipo de trazos (línea, polilínea y arco con `stroke-linecap="round"`) importado da
IoU ≥ 0,999 con su dibujo exacto (fórmulas, como el criterio de F6), y exportado e
importado otra vez, las mismas capas de trazo; todas las pruebas de la tabla de caminos
abiertos; presupuesto de 16 ms arrastrando una capa de trazo en `shou-circular`.

**Tarea de usuario (8 min):** escribir 十 con dos trazos de pluma (ancho 0,08, extremos
redondos), contornear el horizontal y afinar su extremo derecho a mano. Hecho si:
generado y APROBADO.

---

## G3 · Medir, reglas y campos con operaciones  (1 sesión)

- **⌥ con una capa elegida**: al pasar el ratón por otra, líneas rojas con la distancia
  entre las cajas (arriba, abajo, izquierda, derecha; como Figma). Sin nada debajo del
  ratón, la distancia al círculo de diámetro 1 y a los ejes, que aquí son el «marco».
  Con la capa en modo nodos, del nodo elegido al borde de la otra capa más cercano. Las
  capas de trazo se miden por su forma con el grosor (Figma mide sin él, y lo que importa
  aquí es la pieza).
- **Unidades**: diámetro = 1 como hasta ahora; milímetros según la decisión 5.
- **Reglas** (⇧R) arriba y a la izquierda del lienzo 2D; **guías** que se sacan
  arrastrando desde la regla, se guardan en el documento (`guias: {x: [...], y: [...]}`)
  y son objetivos del imán (al mover capas, nodos y en la cuchilla).
- **Campos con operaciones**: `0,2*3`, `+0,01`, `/2`, `50%` en X, Y, ancho, alto, giro y
  grosor, con un evaluador propio (números, + − * / y paréntesis), nunca `eval`.

**Criterio automático:** con ⌥, la distancia que se enseña entre dos rectángulos
conocidos coincide con la calculada a 1e-9; una guía en x = 0,137 atrae un borde a 3 px
y lo deja en 0,137 exacto; «+0,01» en X suma exactamente 0,01; el evaluador rechaza
`alert(1)` y cualquier letra; presupuesto de 16 ms con ⌥ pulsada en `shou-circular`.

**Tarea de usuario (3 min):** en `shou-cruz`, comprobar con ⌥ que los cuatro ganchos
están a la misma distancia del centro y corregir el que no. Hecho si: las cuatro
distancias coinciden a 0,001 y generado APROBADO.

---

## G4 · Booleanas completas y aplanar  (1–2 sesiones, empieza por un sondeo)

Hoy cada capa es «unir» o «restar» lo de debajo. Se añaden **«intersecar»** (quedarse
solo con lo de debajo que cae dentro) y **«excluir»** (lo que está en una sola de las dos
cosas), con el mismo modelo: en el servidor son `intersection` y `symmetric_difference`
dentro de `planta()`, dos líneas. En la lista de capas, cuatro símbolos (＋ − ∩ ⊕).

- **Sondeo (primera media sesión): la vista provisional.** Hoy el lienzo pinta las
  capas en orden (unir en rojo, restar en color de fondo): eso da unir y restar exactos,
  pero no intersecar ni excluir. Opciones a medir en `shou-circular`: (a) máscaras SVG
  anidadas (cada «intersecar» recorta todo lo anterior con un `clipPath`); (b) pintar la
  vista provisional en un `<canvas>` con `globalCompositeOperation` (`destination-in`
  para intersecar, `xor` para excluir). Se elige la que cumpla el presupuesto de 16 ms;
  si ninguna lo cumple, las capas que intersecan o excluyen se ven solo con su contorno
  hasta que llega la geometría exacta, rotulado.
- **Aplanar (⌘E)**: las capas elegidas se convierten en una sola, con la geometría
  exacta del servidor reajustada a curvas (`curvas.ajustar_anillo`, como al abrir un
  símbolo y al exportar SVG en F6). Solo con capas **contiguas** en la pila: aplanar
  capas separadas cambiaría lo que hay entre ellas, y se dice. Las capas de trazo se
  contornean antes. El resultado es siempre «unir» encima de lo que quede debajo de la
  más baja.
- **Botones booleanos como en Figma** (⌥⇧U, ⌥⇧S, ⌥⇧I, ⌥⇧E) con varias capas elegidas:
  hasta G5 no hay grupos, así que aplican la operación a las capas elegidas **y las
  aplanan** en una (destructivo; se puede deshacer). En G5 pasan a crear un grupo
  booleano no destructivo, como en Figma.

**Criterio automático:** para cada operación, la planta del servidor coincide con la
de shapely sobre las mismas formas (diferencia simétrica < 1e-9); aplanar las piezas
de `shou-cruz` cortadas con las 40 sugerencias y generarlo sigue **APROBADO** con el
verificador; aplanar reduce los nodos (≤ 1,2 × los del símbolo abierto sin cortar);
presupuesto de 16 ms con una capa que interseca en `shou-circular`.

**Tarea de usuario (3 min):** hacer un sello redondo: un círculo, «intersecar» con
`fu-trazo` para quedarse con lo que cae dentro, aplanar y generar. Hecho si: APROBADO.

---

## G5 · Grupos y árbol de capas: documento versión 3  (2–3 sesiones, empieza por un sondeo)

La fase con riesgo: el documento pasa de una lista a un árbol. Todo lo que recorre
`doc.capas` (dibujar, imán, cuchilla, sugerencias, simetría, exportar SVG, el parche de
`pagehide`, deshacer, medir, trazos) tiene que recorrerlo.

**Formato (versión 3):**

```json
{"version": 3, "raiz": {"tipo": "grupo", "hijos": [
  {"tipo": "capa", "id": 1, "nombre": "Pieza 1", "op": "unir", "anillos": [...], "t": {...}},
  {"tipo": "grupo", "id": 7, "nombre": "Sello", "op": "unir", "booleana": "intersecar",
   "abierto": true, "t": {"x": 0, "y": 0, "r": 0, "sx": 1, "sy": 1}, "hijos": [...]}]}}
```

- Un **grupo normal** (`booleana` ausente) combina sus hijos de abajo arriba como hoy la
  pila entera, y el resultado entra en la pila de su padre con su `op`.
- Un **grupo booleano** (`booleana`: unir, restar, intersecar, excluir) aplica esa
  operación entre sus hijos, como Figma: restar = el de abajo menos todos los demás.
  Los hijos siguen siendo editables (no destructivo).
- `t` del grupo compone con la de sus hijos (matrices, como `matCapa` × `matCapa`). El
  grosor de un trazo dentro de un grupo escalado sigue la decisión 6.
- La versión 1 y la 2 migran a un grupo raíz con las capas como hijos, sin tocar nada más.

**Sondeo (primera media sesión):** `planta()` recursiva y la migración v2 → v3 sobre los
8 símbolos de la galería abiertos como curvas y sobre los documentos de `tests/`:
planta idéntica (regla 9) y tiempo de `/api/combinar` en `shou-circular` sin empeorar más
de un 10 %; memoria del deshacer frente a la medida en G0. Si el recorrido de árbol rompe
el presupuesto de 16 ms en el navegador, el dibujo se hace sobre una lista aplanada que
se recalcula solo al cambiar la estructura.

**Interfaz:**
- ⌘G agrupa (el grupo queda en el lugar de la capa más alta), ⇧⌘G desagrupa (hornea la
  `t` del grupo en los hijos), los botones booleanos crean grupos booleanos.
- Lista de capas con sangría, triángulo para plegar, arrastrar dentro y fuera de grupos
  (extiende el arrastre de F6), el icono de la booleana en el grupo.
- Clic elige el grupo de más arriba; doble clic o Enter entran; ⌘ + clic elige la capa
  más profunda; Esc sale al padre. Caja, asas, alinear, distribuir y medir tratan un
  grupo como una capa.
- La cuchilla corta capas dentro de grupos (las piezas quedan en el mismo grupo); en un
  grupo booleano, corta sus hijos, no el resultado.

**Criterio automático:** migración de los 8 símbolos y de los documentos de prueba con
planta idéntica; agrupar y desagrupar tres capas giradas deja cada nodo en el mismo
punto del mundo (< 1e-12); un grupo booleano «restar» da la misma planta que las capas
sueltas con «restar»; deshacer tras agrupar vuelve al JSON idéntico; el parche de
`pagehide` completa capas dentro de grupos (la prueba de 64 KB de F5, con el disco
dentro de un grupo, y otra con un documento de 200 KB); `test:ui` y pytest enteros en
verde; presupuesto de 16 ms.

**Tarea de usuario (5 min):** en `shou-cruz` cortado en trazos, agrupar los cuatro
ganchos, girar el grupo 90° y entrar para mover un gancho suelto. Hecho si: generado y
APROBADO, y reabrir el documento lo muestra igual.

---

## G6 · Esquinas y curvar  (1–2 sesiones)

- **Radio de esquina**: por capa (panel «Radio») y por nodo (en modo nodos). Se guarda
  en el nodo (`radio`, opcional) y el servidor lo aplica antes de combinar: cada esquina
  viva con radio r se sustituye por su arco tangente (dos nodos y una cúbica de arco),
  limitado a la mitad del tramo más corto, como Figma. La vista provisional hace lo
  mismo en JavaScript con la misma fórmula (prueba de paridad como la de `aplanar`).
- **Curvar** (⌘ + arrastrar sobre un tramo): el tramo pasa a cúbica y se deforma para
  pasar por el ratón (tiradores a 1/3 y 2/3, resolviendo la cúbica por el punto
  arrastrado en su t más cercano).
- **Tipos de nodo en el panel** (sin simetría / ángulo / ángulo y largo, que son vivo,
  suave y espejo): hoy solo se cambian con doble clic y ⌥.

**Criterio automático:** radio 0,05 en las cuatro esquinas de un cuadrado de lado 0,4
da el área exacta 0,16 − (4 − π) · 0,05² (< 1e-6) y la vista provisional coincide con el
servidor (paridad < 1e-12); en un triángulo muy agudo el radio se limita y la forma
sigue válida; curvar un tramo recto deja la curva pasando por el punto soltado (< 1e-9);
el radio se aplica igual en una capa de trazo cerrada.

**Tarea de usuario (5 min):** en `fu-trazo` abierto como curvas, redondear las esquinas
exteriores del trazo de la izquierda y curvar un tramo con ⌘. Hecho si: generado y
APROBADO.

---

## G7 · Varios nodos, lazo y lápiz  (1–2 sesiones)

- **Varios nodos**: ⇧ + clic y **lazo (Q)** los eligen; se mueven, se empujan con las
  flechas, se escalan y giran con una caja propia y se borran juntos.
- **Unir extremos (⌘J)** de un camino abierto (o de dos: se funden en uno) y **fusionar
  nodos** (⇧⌘M) elegidos que estén a menos de 1e-3.
- **Pluma con ⇧**: ángulos de 45°; imán a los nodos de otras capas (como la cuchilla).
- **Lápiz (⇧P)**: a mano alzada; al soltar, la polilínea se ajusta con
  `curvas.ajustar_anillo` (tol 0,002) en el servidor y llega como curvas: cerrada si el
  final cae a 8 px del principio, si no, camino abierto con el trazo por defecto.

**Criterio automático:** mover 12 nodos elegidos con lazo los desplaza a todos lo mismo
(< 1e-15); ⌘J sobre dos caminos abiertos da uno con la suma de nodos menos los fundidos;
un trazo de lápiz de 300 puntos llega con ≤ 30 nodos y a menos de 0,002 del dibujo;
presupuesto de 16 ms moviendo 50 nodos a la vez en `shou-circular`.

**Tarea de usuario (5 min):** dibujar con el lápiz un trazo curvo de pincel (camino
abierto), darle grosor y generar. Hecho si: APROBADO.

---

## G8 · Formas y texto  (1–2 sesiones)

- **Polígono** (lados 3–60) y **estrella** (puntas, radio interior), paramétricos
  mientras no se editen sus nodos (como Figma: al tocar un nodo pasan a vector).
- **Arco de elipse** en el panel: inicio, barrido y radio interior (0–99 %), para
  anillos y sellos. Paramétrico igual; el servidor recibe la forma exacta con cúbicas de
  ≤ 90°.
- **Línea (L) y flecha (⇧L)**: caminos abiertos con trazo (G2); la flecha, con su punta
  como capa unida.
- **Texto (T)**: se escribe, se elige fuente (las del sistema, vía el servidor), y llega
  **ya como contornos**: los glifos de TrueType son cuadráticas y los de OpenType CFF
  cúbicas, así que pasan a nodos **sin pérdida** (el código de `tools/letras.py`, que ya
  lee glifos con fonttools). No hay capa de texto editable: un símbolo no cambia de
  texto, y así el editor no depende de la fuente para abrir el documento.

**Criterio automático:** estrella de 5 puntas de radios 0,4 y 0,16 con el área exacta
(< 1e-9); arco de 360° con radio interior 50 % = el anillo exacto (< 1e-6 por el paso a
cúbicas); «福» con Hiragino da la misma planta que `letras.py` (IoU ≥ 0,9999), con
tantos nodos como puntos tiene el glifo.

**Tarea de usuario (5 min):** hacer un sello: anillo con arco, «福» en texto dentro,
restar el texto del disco y generar. Hecho si: APROBADO.

---

## G9 · Historial de versiones y exportar  (1 sesión)

- **Panel de historial**: las copias de `editor/.historial/<nombre>/` con fecha y una
  miniatura (el SVG de F6 del documento, en pequeño), comparar con la actual (las dos
  superpuestas) y restaurar (restaurar es una edición más: se puede deshacer).
- **Guardar versión con nombre (⌥⌘S)**: copia que el recorte de 20 no borra nunca.
- **Exportar** (⇧⌘E): SVG de la selección o del diseño, y PNG de la vista 2D a 1×, 2× o
  4× (para presentaciones), además del GLB de siempre.

**Criterio automático:** restaurar una copia deja el documento idéntico a ella
(comparación de texto) y ⌘Z vuelve al de antes; una versión con nombre sobrevive a 30
guardados; el PNG a 2× mide el doble que a 1×; restaurar una copia de la versión 2 en un
documento de la versión 3 pasa por la migración.

**Tarea de usuario (3 min):** estropear un documento, encontrar en el historial la
versión de hace 10 minutos y restaurarla. Hecho si: el documento es idéntico a esa copia.

---

## G10 · Componentes e instancias  (2 sesiones, opcional)

Útil para trazos que se repiten (los ganchos de `shou-cruz`, los dos 喜 de `囍`): se
edita el maestro y cambian todas las copias. Con la simetría en vivo (F2) y la rotacional
(G11) ya se cubren los casos más comunes; por eso es opcional.

- ⌥⌘K crea un componente de la selección (un grupo, G5); arrastrar desde el panel
  «Componentes» o ⌘D sobre una instancia crea otra.
- Una instancia guarda solo el id del maestro y su `t`; se puede voltear y girar, no
  editar sus nodos (como Figma sin «overrides»). «Separar instancia» la convierte en un
  grupo normal.
- El servidor expande las instancias antes de combinar.

**Criterio automático:** mover un nodo del maestro mueve el mismo nodo del mundo en
cada instancia según su `t` (< 1e-12); separar una instancia no cambia la planta; un
documento con instancias exporta SVG y genera GLB igual que su versión expandida.

**Tarea de usuario (5 min):** en `shou-cruz`, convertir un gancho en componente,
sustituir los otros tres por instancias giradas y cambiar la forma del maestro. Hecho
si: los cuatro cambian y generado APROBADO.

---

## G11 · Simetría rotacional y repetición radial  (1–2 sesiones, opcional; no es de Figma)

Los sellos circulares (`shou-circular`, `fu-circular`) se repiten alrededor del centro,
y la simetría de F2 solo refleja izquierda↔derecha y arriba↔abajo.

- **Simetría rotacional de orden N** (2–12) en el panel, con o sin espejo (grupos
  diédricos): manda un sector de 360°/N (o de 180°/N con espejo) y el servidor lo
  recorta y lo repite, como `simetrizar()` hace con las mitades. Mismo cuidado que F2:
  los bordes del sector quedan exactos en sus rectas para que las copias se fundan sin
  rendija.
- **Repetición radial** de una selección: N copias alrededor de un centro (por defecto
  el origen), como capas normales.

**Criterio automático:** con orden 4 sobre `shou-circular` abierto como curvas, la
geometría es invariante a un giro de 90° (diferencia simétrica < 1e-9) y generado sigue
**APROBADO**; con orden N, las N copias se funden sin rendija (una pieza donde debe haber
una); repetición radial de 6 da 6 capas a 60° exactos.

**Tarea de usuario (5 min):** rehacer un cuarto de `shou-circular` y completarlo con
simetría rotacional de orden 4. Hecho si: generado y APROBADO.

---

## Riesgos y cómo se contienen

| Riesgo | Dónde | Contención |
|---|---|---|
| Los caminos abiertos rompen algo que suponía anillos cerrados | G2 | la tabla de cambios con una prueba por fila; sin trazo no puede haber camino abierto |
| `buffer()` de shapely con uniones en inglete muy agudas | G2 | sondeo con un zigzag de 10°; `mitre_limit` como Figma (4) |
| El árbol de capas rompe algo de lo que recorre `doc.capas` | G5 | sondeo primero; lista aplanada para dibujar; migración con planta idéntica en los 8 símbolos |
| La memoria del deshacer crece con árboles y documentos grandes | G0, G5 | medida en G0; diferencias entre pasos si pasa de 100 MB |
| La vista provisional de intersecar/excluir no cabe en 16 ms | G4 | sondeo con dos técnicas; si no, contorno rotulado hasta la exacta |
| El portapapeles no admite el tipo propio en Safari o Firefox | G1 | siempre va también el SVG en `text/plain`; se usan los eventos `copy`/`paste`, que no piden permiso |
| Radios de esquina que se solapan en tramos cortos | G6 | límite a la mitad del tramo más corto, igual que Figma; prueba con un triángulo muy agudo |
| El documento crece más de los 64 KB del parche de `pagehide` | G2–G8 | el parche por capa de F5 sigue valiendo (por id, recorriendo el árbol); prueba con 200 KB |
| Las estimaciones se quedan cortas | todas | cada fase tiene un rango; si una pasa del máximo, se parte en dos antes de seguir, como F4 |

## Decisiones que son tuyas (con mi recomendación)

1. **Escala al pegar un SVG en un documento con capas.** Recomiendo diámetro 0,5 y
   centrado en la vista (se ve entero y es fácil de ajustar). Alternativa: conservar el
   tamaño con 1 px = 1/1000 del diámetro, que respeta proporciones entre pegados
   sucesivos pero suele dejar el pegado enorme o diminuto.
2. **⇧1 como en Figma** (todo) y la selección en ⇧2: recomiendo cambiarlo ya en G1,
   aunque F6 acaba de publicar ⇧1 con selección.
3. **K**: recomiendo que siga siendo la cuchilla (es la herramienta propia del editor
   más usada) y no la escala de Figma.
4. **Navegadores**: recomiendo Chrome como referencia y los demás lo mejor posible
   (regla 10). Si usas Safari a diario, conviene saberlo ahora: entonces las pruebas de
   interfaz deberían correr también en WebKit (Playwright lo trae).
5. **Unidades en milímetros** (G3): solo de presentación. Recomiendo hacerlo si piensas
   imprimir o fabricar piezas; si no, sobra.
6. **¿Escalar una capa escala su grosor?** En Figma no (salvo con la herramienta K).
   Recomiendo lo mismo por defecto (el grosor es una decisión de diseño que no debería
   cambiar al ajustar el tamaño) y una casilla «Escalar también el grosor» en el panel,
   que se recuerda por documento.
7. **G10 y G11**: recomiendo decidir después de G2. Con trazos y simetría rotacional
   puede que los componentes no hagan falta.

## Coste

| G0 | G1 | G2 | G3 | G4 | G5 | G6 | G7 | G8 | G9 | G10 (opc.) | G11 (opc.) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 0,5–1 | 1–1,5 | 2–3 | 1 | 1–2 | 2–3 | 1–2 | 1–2 | 1–2 | 1 | 2 | 1–2 |

**11,5–18,5 sesiones sin las opcionales.** El rango es ancho a propósito: F4 (curvas)
estaba previsto en 3 y G2 y G5 son de ese tamaño. G0–G2 (3,5–5,5 sesiones) ya entregan lo
que más se nota: pruebas fiables, el flujo de Figma en el día a día y dibujar con trazos.

## Fuentes

- Operaciones booleanas (unir, restar, intersecar, excluir; no destructivas):
  https://help.figma.com/hc/en-us/articles/360039957534-Boolean-operations
- Edición vectorial (curvar, lazo Q, radio por punto):
  https://help.figma.com/hc/en-us/articles/360039957634-Edit-vector-layers
- Redes vectoriales: https://help.figma.com/hc/en-us/articles/360040450213-Vector-networks
- Trazos (grosor, extremos, uniones, posición):
  https://help.figma.com/hc/en-us/articles/360049283914-Apply-and-adjust-stroke-properties
- Medir distancias con ⌥:
  https://help.figma.com/hc/en-us/articles/360039956974-Measure-distances-between-layers
- Atajos (⇧2 zoom a la selección, ⌘E aplanar, ⇧⌘O contornear, ⇧⌘V pegar encima):
  https://help.figma.com/hc/en-us/articles/360040328653-Use-Figma-products-with-a-keyboard
- Guías de atajos más usados: https://www.topcoder.com/thrive/articles/top-shortcuts-for-figma
