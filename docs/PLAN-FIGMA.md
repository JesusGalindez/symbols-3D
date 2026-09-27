# Plan: lo mejor de Figma en el editor de símbolos

Versión 1 (2026-09-27). Punto de partida: el editor tras F6 (`docs/PLAN-EDITOR.md`):
capas con curvas Bézier, unir/restar, mover/escalar/girar, rectángulo, elipse, pluma,
cuchilla con sugerencias, nodos y tiradores, imán, simetría en vivo, selección múltiple
con alinear y distribuir, deshacer, guardado automático, importar y exportar SVG, ⇧1/⇧0
y panel de atajos.

La pregunta de este plan no es «qué tiene Figma», sino **qué de Figma hace mejor un
símbolo 3D**. Figma es una herramienta de interfaces; muchas de sus funciones estrella
(auto layout, prototipos, variables) no significan nada para una pieza de laca. Lo que sí
importa: la edición vectorial, las operaciones booleanas, los trazos, la precisión y el
flujo de trabajo del día a día (portapapeles, atajos, medir).

## Reglas del plan

Las cinco de `PLAN-EDITOR.md` siguen vigentes: nada toca un símbolo aprobado; shapely
manda (el navegador solo previsualiza); cada fase se cierra con un criterio automático y
una tarea de usuario; presupuesto de rendimiento (arrastrar la capa mayor de
`shou-circular` ≤ 16 ms por fotograma, mediana); un commit por fase. Y además:

6. **Atajos idénticos a Figma**, salvo los conflictos de la tabla de abajo, que se
   deciden una vez y se documentan en el panel «?». Quien viene de Figma no tiene que
   aprender nada nuevo.
7. **Toda geometría nueva pasa por el servidor.** Trazos, radios de esquina, booleanas,
   texto: el navegador enseña una aproximación rotulada como provisional y el servidor
   da la exacta, la misma que va al GLB. Nada nuevo se calcula solo en JavaScript.
8. **Cada fase se prueba sobre tres símbolos reales:** `xi-doble` (simple, simetría
   izq.↔der.), `shou-cruz` (uniones en T, cuchilla) y `shou-circular` (el más pesado,
   5159 nodos densos). Una función que solo funciona con rectángulos no está hecha.
9. **El formato del documento solo cambia una vez** (versión 3, en G4), con migración
   desde la 1 y la 2 comprobada: la planta de un documento migrado es idéntica (IoU = 1
   con diferencia simétrica de área < 1e-12) a la de antes.

## Inventario: Figma frente al editor

Uso: frecuencia en el trabajo diario de Figma (según su documentación, los atajos que
más se citan y los tutoriales de iconografía). Valor: cuánto ayuda a hacer un símbolo.

| Función de Figma | Atajo en Figma | ¿La tenemos? | Uso | Valor aquí | Fase |
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
| Medir distancias | ⌥ con selección | no | muy alto | alto | G2 |
| Reglas y guías arrastrables | ⇧R | no | medio | medio | G2 |
| Operaciones en los campos (`0,2*3`, `+0,01`) | — | no | medio | medio | G2 |
| Unir / restar | ⌥⇧U ⌥⇧S | sí, por orden de capas | muy alto | — | — |
| Intersecar / excluir | ⌥⇧I ⌥⇧E | no | alto | alto | G3 |
| Aplanar | ⌘E | no | alto | alto | G3 |
| Grupos | ⌘G ⇧⌘G | no | muy alto | alto | G4 |
| Grupos booleanos no destructivos | menú booleano | no (la pila entera es una booleana) | alto | alto | G4 |
| Selección profunda / entrar en el grupo | ⌘ + clic, doble clic | no | alto | alto | G4 |
| Trazo: grosor, extremos, uniones | — | no | muy alto | **muy alto** | G5 |
| Contornear trazo | ⇧⌘O | no | alto | **muy alto** | G5 |
| Radio de esquina (por capa y por nodo) | — | no | muy alto | alto | G6 |
| Herramienta curvar (⌘ + arrastrar un tramo) | ⌘ | no | alto | alto | G6 |
| Lazo para nodos | Q | no | medio | medio | G6 |
| Varios nodos a la vez (mover, escalar, borrar) | ⇧ + clic | no (un nodo) | alto | alto | G6 |
| Unir extremos / fusionar nodos | ⌘J ⇧⌘M | no | medio | medio | G6 |
| Lápiz (a mano alzada) | ⇧P | no | medio | medio | G6 |
| Polígono y estrella | — | no | medio | medio | G7 |
| Arco de elipse (inicio, barrido, radio interior) | — | no | medio | alto (anillos, sellos) | G7 |
| Texto a contornos | T, luego aplanar | no (solo `letras.py` por línea de órdenes) | alto | alto | G7 |
| Historial de versiones con nombre | ⌥⌘S | copias en `editor/.historial`, sin interfaz | medio | medio | G8 |
| Exportar la selección / PNG | ⇧⌘E | SVG del diseño entero | alto | medio | G8 |
| Componentes e instancias | ⌥⌘K | no | muy alto | medio | G9 (opcional) |

**Fuera, a propósito:** auto layout, restricciones, prototipos, modo desarrollo,
variables y estilos de color (el GLB tiene un material), efectos y degradados,
multijugador y comentarios, páginas y marcos (un documento = un símbolo), redes
vectoriales (un nodo con tres tramos no tiene relleno bien definido y el modelo de
anillos cerrados es lo que garantiza una malla estanca) y el cubo de pintura.

## Conflictos de atajos

| Atajo | En Figma | Aquí | Decisión |
|---|---|---|---|
| K | escalar con todo (herramienta) | cuchilla (desde F1) | se queda la cuchilla; escalar proporcional ya es ⇧ + esquina |
| ⇧1 | ajustar todo | ajustar lo visible **o la selección** (F6) | como Figma: ⇧1 todo, ⇧2 selección |
| ⌘R | renombrar | el navegador recarga | se intercepta (`preventDefault`) solo con el foco en el editor |
| ⌘+ ⌘− | zoom del lienzo | zoom de la página | se interceptan igual |
| ⇧⌘H | ocultar | ocultar (sin conflicto en el navegador) | como Figma |
| Enter | entrar en el grupo / nodos | nodos | Enter entra en el grupo; en una capa, nodos (igual que Figma) |

---

## Orden y por qué

```
G1 Portapapeles y atajos ─► G2 Medir ─► G3 Booleanas ─► G4 Grupos (v3) ─► G5 Trazos ─► G6 Vectores ─► G7 Formas y texto ─► G8 Versiones
   (lo diario, sin riesgo)              (sin cambiar     (el cambio de      (lo más útil   (edición fina)                       └► G9 Componentes
                                          el formato)      formato)          para trazos)                                          (opcional)
```

Primero lo que se usa cada minuto y no toca el formato del documento (G1–G3): se entrega
pronto y sin riesgo. G4 concentra el riesgo (el documento pasa de lista a árbol) y va
antes de G5 porque un trazo contorneado y una booleana no destructiva son, por dentro,
grupos. Los trazos (G5) son lo más valioso para caracteres chinos, que están hechos de
trazos: van justo detrás.

---

## G1 · Portapapeles y atajos de Figma  (1 sesión)

- **⌘C / ⌘X / ⌘V** de capas, con el evento `copy`/`paste` del navegador (no una
  variable interna): así se puede copiar entre dos pestañas del editor. En el
  portapapeles van dos tipos: `text/plain` con un SVG de las capas (lo que Figma lee al
  pegar) y `web application/x-simbolos` con el JSON de las capas (lo que lee el editor,
  sin perder nada). Pegar pone las capas encima de la selección, desplazadas 0,02 si
  caerían justo encima de las originales; **⇧⌘V** las pega en su sitio.
- **Pegar un SVG** (de Figma con «Copy as SVG», de Illustrator o de un archivo abierto
  en un editor de texto): si el `text/plain` empieza por `<svg`, va a `/api/importar` y
  las capas se añaden al documento. Escala: la de la importación de F6 (diámetro 1) si
  el documento está vacío; si no, a un diámetro de 0,5, centradas en el centro de la
  vista y seleccionadas, listas para ajustar (ver «Decisiones»).
- **⌥ + arrastrar** duplica y mueve la copia (con imán). **⌘D** repite el último
  desplazamiento: duplicar, mover, ⌘D, ⌘D… hace una fila equiespaciada, como en Figma.
- **⇧H / ⇧V** voltean la selección respecto al centro de su caja (con varias capas, las
  posiciones también se reflejan). Se hornea como la escala de F3: `sx`, `sy` negativos
  dejarían los anillos al revés y la cuchilla trabaja en el mundo.
- **Zoom**: ⇧1 todo lo visible, ⇧2 la selección (corrige F6), ⇧0 100 %, ⌘+/⌘− por
  pasos de ×2 centrados en el centro de la vista.
- **Capas**: ⇧⌘L bloquea (no se elige desde el lienzo ni con el recuadro; candado en
  la lista), ⇧⌘H oculta, ⌘R renombra, Tab / ⇧Tab eligen la capa de encima / debajo.
  `bloqueada` es un campo nuevo y opcional de la capa: no cambia la versión del formato.

**Criterio automático** (`tests/editor-ui.mjs`): copiar tres capas de `xi-doble` y
pegarlas en otra pestaña del editor da el mismo JSON de capas salvo ids y nombres;
⇧⌘V deja `t` idéntico; pegar el SVG que exporta F6 de `shou-cruz` en un documento
vacío da una planta con IoU ≥ 0,999 contra la original; ⌥ + arrastrar crea exactamente
una capa; ⇧H dos veces deja el JSON idéntico (comparación de texto); una capa bloqueada
no se elige ni con clic ni con recuadro.

**Tarea de usuario (3 min):** copiar un icono en Figma («Copy as SVG»), pegarlo en el
editor y colocarlo en el centro de `xi-doble`.

---

## G2 · Medir, reglas y campos con operaciones  (1 sesión)

- **⌥ con una capa elegida**: al pasar el ratón por otra, líneas rojas con la distancia
  entre las cajas (arriba, abajo, izquierda, derecha; como Figma). Sin nada debajo del
  ratón, la distancia al círculo de diámetro 1 y a los ejes, que aquí son el «marco».
  Con la capa en modo nodos, del nodo elegido al borde de la otra capa más cercano.
- **Unidades**: diámetro = 1 como hasta ahora. Opcional en el panel: milímetros para un
  diámetro físico que se escribe una vez por documento (`ajustes.diametro_mm`, solo de
  presentación; el GLB no cambia).
- **Reglas** (⇧R) arriba y a la izquierda del lienzo 2D; **guías** que se sacan
  arrastrando desde la regla, se guardan en el documento (`guias: {x: [...], y: [...]}`)
  y son objetivos del imán (al mover capas, nodos y en la cuchilla).
- **Campos con operaciones**: `0,2*3`, `+0,01`, `/2`, `50%` en X, Y, ancho, alto y giro,
  con un evaluador propio (números, + − * / y paréntesis), nunca `eval`.

**Criterio automático:** con ⌥, la distancia que se enseña entre dos rectángulos
conocidos coincide con la calculada a 1e-9; una guía en x = 0,137 atrae un borde a 3 px
y lo deja en 0,137 exacto; «+0,01» en X suma exactamente 0,01; el evaluador rechaza
`alert(1)` y cualquier letra.

**Tarea de usuario (3 min):** en `shou-cruz`, comprobar con ⌥ que los cuatro ganchos
están a la misma distancia del centro y corregir el que no.

---

## G3 · Booleanas completas y aplanar  (1–2 sesiones, empieza por un sondeo)

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
  capas separadas cambiaría lo que hay entre ellas, y se dice. El resultado es siempre
  «unir» encima de lo que quede debajo de la más baja.
- **Botones booleanos como en Figma** (⌥⇧U, ⌥⇧S, ⌥⇧I, ⌥⇧E) con varias capas elegidas:
  hasta G4 no hay grupos, así que aplican la operación a las capas elegidas **y las
  aplanan** en una (destructivo; se puede deshacer). En G4 pasan a crear un grupo
  booleano no destructivo, como en Figma.

**Criterio automático:** para cada operación, la planta del servidor coincide con la
de shapely sobre las mismas formas (diferencia simétrica < 1e-9); aplanar las piezas
de `shou-cruz` cortadas con las 40 sugerencias y generarlo sigue **APROBADO** con el
verificador; aplanar reduce los nodos (≤ 1,2 × los del símbolo abierto sin cortar);
presupuesto de 16 ms con una capa que interseca en `shou-circular`.

**Tarea de usuario (3 min):** hacer un sello redondo: un círculo, «intersecar» con
`fu-trazo` para quedarse con lo que cae dentro, aplanar y generar.

---

## G4 · Grupos y árbol de capas: documento versión 3  (2 sesiones, empieza por un sondeo)

La fase con riesgo: el documento pasa de una lista a un árbol. Todo lo que recorre
`doc.capas` (dibujar, imán, cuchilla, sugerencias, simetría, exportar SVG, el parche de
`pagehide`, deshacer) tiene que recorrerlo.

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
- `t` del grupo compone con la de sus hijos (matrices, como `matCapa` × `matCapa`).
- La versión 2 migra a un grupo raíz con las capas como hijos, sin tocar nada más.

**Sondeo (primera media sesión):** `planta()` recursiva y la migración v2 → v3 sobre los
8 símbolos de la galería abiertos como curvas y sobre los documentos de `tests/`:
planta idéntica (regla 9) y tiempo de `/api/combinar` en `shou-circular` sin empeorar más
de un 10 %. Si el recorrido de árbol rompe el presupuesto de 16 ms en el navegador, el
dibujo se hace sobre una lista aplanada que se recalcula solo al cambiar la estructura.

**Interfaz:**
- ⌘G agrupa (el grupo queda en el lugar de la capa más alta), ⇧⌘G desagrupa (hornea la
  `t` del grupo en los hijos), los botones booleanos crean grupos booleanos.
- Lista de capas con sangría, triángulo para plegar, arrastrar dentro y fuera de grupos
  (extiende el arrastre de F6), el icono de la booleana en el grupo.
- Clic elige el grupo de más arriba; doble clic o Enter entran; ⌘ + clic elige la capa
  más profunda; Esc sale al padre. Caja, asas, alinear y distribuir tratan un grupo
  como una capa.
- La cuchilla corta capas dentro de grupos (las piezas quedan en el mismo grupo); en un
  grupo booleano, corta sus hijos, no el resultado.

**Criterio automático:** migración de los 8 símbolos y de los documentos de prueba con
planta idéntica; agrupar y desagrupar tres capas giradas deja cada nodo en el mismo
punto del mundo (< 1e-12); un grupo booleano «restar» da la misma planta que las capas
sueltas con «restar»; deshacer tras agrupar vuelve al JSON idéntico; el parche de
`pagehide` completa capas dentro de grupos (la prueba de 64 KB de F5, con el disco
dentro de un grupo); `test:ui` y pytest enteros en verde; presupuesto de 16 ms.

**Tarea de usuario (5 min):** en `shou-cruz` cortado en trazos, agrupar los cuatro
ganchos, girar el grupo 90° y entrar para mover un gancho suelto.

---

## G5 · Trazos y contornear trazo  (2 sesiones)

Los caracteres chinos son trazos. Hoy un trazo se dibuja como su contorno, nodo a nodo;
con esta fase se dibuja **su esqueleto** y el grosor lo pone el servidor.

- **Capa de trazo**: un camino **abierto o cerrado** hecho con la pluma (Esc o Enter sin
  cerrar deja el camino abierto) con `trazo: {"ancho": 0,03, "extremos": "redondo" |
  "plano" | "cuadrado", "uniones": "redonda" | "inglete" | "bisel", "inglete": 4}`.
  El servidor lo convierte en forma con `LineString(...).buffer(ancho / 2,
  cap_style=..., join_style=..., mitre_limit=...)` sobre el camino aplanado, y a partir
  de ahí es una capa más (unir, restar, intersecar, excluir, grupos).
- **Posición del trazo** como en Figma (centro, dentro, fuera) solo en caminos cerrados:
  dentro = `forma.buffer(-ancho)` unido con el contorno, fuera = lo mismo hacia fuera.
- **Contornear trazo (⇧⌘O)**: el trazo pasa a capa rellena, con curvas
  (`ajustar_anillo`), para editar sus nodos a mano (p. ej. afinar un extremo como un
  pincel).
- **Desplazar contorno** (engrosar / adelgazar una capa ± d): `buffer(±d)` y reajuste a
  curvas. Enlaza con F5: cuando «Generar» rechaza por **trazo fino**, el panel ofrece
  «Engrosar lo necesario», que calcula la d mínima que aprueba (búsqueda binaria sobre
  `simbolo.area_perdida`) y la aplica a las capas culpables.
- Vista provisional: el trazo se pinta con `stroke-width` del SVG (exacto salvo las
  uniones en inglete muy agudas); la exacta llega del servidor como siempre.

**Criterio automático:** un trazo recto de ancho 0,03 y extremos planos tiene exactamente
el área L × 0,03 (< 1e-9); con extremos redondos, L × 0,03 + π · 0,015² (< 1e-5, por el
aplanado); contornear un trazo curvo y volver a combinar da IoU ≥ 0,999 con el trazo;
redibujar con trazos los 4 trazos horizontales de `xi-doble` y generar da **APROBADO**;
«Engrosar lo necesario» convierte en APROBADO el caso de 0,01 de
`test_generar_rechaza_un_trazo_fino` con el menor d que aprueba (± 1e-4).

**Tarea de usuario (8 min):** escribir 十 con dos trazos de pluma (ancho 0,08, extremos
redondos), contornear el horizontal y afinar su extremo derecho a mano; generar.

---

## G6 · Edición vectorial fina  (2 sesiones)

- **Radio de esquina**: por capa (panel «Radio») y por nodo (en modo nodos). Se guarda
  en el nodo (`radio`, opcional) y el servidor lo aplica antes de combinar: cada esquina
  viva con radio r se sustituye por su arco tangente (dos nodos y una cúbica de arco),
  limitado a la mitad del tramo más corto, como Figma. La vista provisional hace lo
  mismo en JavaScript con la misma fórmula (prueba de paridad como la de `aplanar`).
- **Curvar** (⌘ + arrastrar sobre un tramo): el tramo pasa a cúbica y se deforma para
  pasar por el ratón (tiradores a 1/3 y 2/3, resolviendo la cúbica por el punto
  arrastrado en su t más cercano).
- **Varios nodos**: ⇧ + clic y **lazo (Q)** los eligen; se mueven, se empujan con las
  flechas, se escalan y giran con una caja propia y se borran juntos.
- **Tipos de nodo en el panel** (sin simetría / ángulo / ángulo y largo, que son vivo,
  suave y espejo): hoy solo se cambian con doble clic y ⌥.
- **Unir extremos (⌘J)** de un camino abierto y **fusionar nodos** (⇧⌘M) elegidos que
  estén a menos de 1e-3.
- **Pluma con ⇧**: ángulos de 45°; imán a los nodos de otras capas (como la cuchilla).
- **Lápiz (⇧P)**: a mano alzada; al soltar, la polilínea se ajusta con
  `curvas.ajustar_anillo` (tol 0,002) en el servidor y llega como curvas.

**Criterio automático:** radio 0,05 en las cuatro esquinas de un cuadrado de lado 0,4
da el área exacta 0,16 − (4 − π) · 0,05² (< 1e-6) y la vista provisional coincide con el
servidor (paridad < 1e-12); curvar un tramo recto deja la curva pasando por el punto
soltado (< 1e-9); mover 12 nodos elegidos con lazo los desplaza a todos lo mismo
(< 1e-15); un trazo de lápiz de 300 puntos llega con ≤ 30 nodos y a menos de 0,002 del
dibujo; presupuesto de 16 ms moviendo 50 nodos a la vez en `shou-circular`.

**Tarea de usuario (5 min):** en `fu-trazo` abierto como curvas, redondear las esquinas
exteriores del trazo de la izquierda y curvar un tramo con ⌘.

---

## G7 · Formas y texto  (1 sesión)

- **Polígono** (lados 3–60) y **estrella** (puntas, radio interior), paramétricos
  mientras no se editen sus nodos (como Figma: al tocar un nodo pasan a vector).
- **Arco de elipse** en el panel: inicio, barrido y radio interior (0–99 %), para
  anillos y sellos. Paramétrico igual; el servidor recibe la forma exacta con cúbicas de
  ≤ 90°.
- **Línea y flecha** como capas de trazo (G5).
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
restar el texto del disco y generar.

---

## G8 · Historial de versiones y exportar  (1 sesión)

- **Panel de historial**: las copias de `editor/.historial/<nombre>/` con fecha y una
  miniatura (el SVG de F6 del documento, en pequeño), comparar con la actual (las dos
  superpuestas) y restaurar (restaurar es una edición más: se puede deshacer).
- **Guardar versión con nombre (⌥⌘S)**: copia que el recorte de 20 no borra nunca.
- **Exportar** (⇧⌘E): SVG de la selección o del diseño, y PNG de la vista 2D a 1×, 2× o
  4× (para presentaciones), además del GLB de siempre.

**Criterio automático:** restaurar una copia deja el documento idéntico a ella
(comparación de texto) y ⌘Z vuelve al de antes; una versión con nombre sobrevive a 30
guardados; el PNG a 2× mide el doble que a 1×.

**Tarea de usuario (3 min):** estropear un documento, encontrar en el historial la
versión de hace 10 minutos y restaurarla.

---

## G9 · Componentes e instancias  (2 sesiones, opcional)

Útil sobre todo para trazos que se repiten (los ganchos de `shou-cruz`, los dos 喜 de
`囍`): se edita el maestro y cambian todas las copias. Con simetría en vivo (F2) ya se
cubre el caso más común, por eso es opcional.

- ⌥⌘K crea un componente de la selección (un grupo, G4); arrastrar desde el panel
  «Componentes» o ⌘D sobre una instancia crea otra.
- Una instancia guarda solo el id del maestro y su `t`; se puede voltear y girar, no
  editar sus nodos (como Figma sin «overrides»). «Separar instancia» la convierte en un
  grupo normal.
- El servidor expande las instancias antes de combinar.

**Criterio automático:** mover un nodo del maestro mueve el mismo nodo del mundo en
cada instancia según su `t` (< 1e-12); separar una instancia no cambia la planta; un
documento con instancias exporta SVG y genera GLB igual que su versión expandida.

**Tarea de usuario (5 min):** en `shou-cruz`, convertir un gancho en componente,
sustituir los otros tres por instancias giradas y cambiar la forma del maestro.

---

## Riesgos y cómo se contienen

| Riesgo | Dónde | Contención |
|---|---|---|
| El árbol de capas rompe algo de lo que recorre `doc.capas` | G4 | sondeo primero; lista aplanada para dibujar; migración con planta idéntica en los 8 símbolos |
| La vista provisional de intersecar/excluir no cabe en 16 ms | G3 | sondeo con dos técnicas; si no, contorno rotulado hasta la exacta |
| `buffer()` de shapely con uniones en inglete muy agudas | G5 | `mitre_limit` como Figma (4 por defecto); prueba con un zigzag de 10° |
| El portapapeles del navegador exige permisos o no admite tipos propios | G1 | se usan los eventos `copy`/`paste` (no la API asíncrona), que no piden permiso; el tipo propio con prefijo `web ` |
| Radios de esquina que se solapan en tramos cortos | G6 | límite a la mitad del tramo más corto, igual que Figma; prueba con un triángulo muy agudo |
| Crecer el documento pasa de los 64 KB del parche de `pagehide` | G4–G7 | el parche por capa de F5 sigue valiendo (por id, recorriendo el árbol); prueba con un documento de 200 KB |

## Decisiones que son tuyas (con mi recomendación)

1. **Escala al pegar un SVG en un documento con capas.** Recomiendo diámetro 0,5 y
   centrado en la vista (se ve entero y es fácil de ajustar). Alternativa: conservar el
   tamaño en píxeles con 1 px = 1/1000 del diámetro, que respeta proporciones entre
   pegados sucesivos pero suele dejar el pegado enorme o diminuto.
2. **⇧1 como en Figma** (todo) y la selección en ⇧2: recomiendo cambiarlo ya en G1,
   aunque F6 acaba de publicar ⇧1 con selección. Es lo que espera quien viene de Figma.
3. **K**: recomiendo que siga siendo la cuchilla (es la herramienta propia del editor
   más usada) y no la escala de Figma.
4. **G9 (componentes)**: recomiendo decidir después de G5; con trazos y simetría puede
   que no haga falta.
5. **Unidades en milímetros** (G2): solo de presentación. Recomiendo hacerlo si piensas
   imprimir o fabricar piezas; si no, sobra.

## Coste

G1 1 · G2 1 · G3 1–2 · G4 2 · G5 2 · G6 2 · G7 1 · G8 1 · G9 2 (opcional): **11–12
sesiones sin G9**. G1–G3 (3–4 sesiones) ya dan lo que más se nota en el día a día sin
tocar el formato; G5 es lo que más cambia cómo se dibuja un carácter.

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
