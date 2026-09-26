# symbols-3D

**Símbolos chinos y textos convertidos en assets 3D `.glb` de laca roja, con geometría exacta y verificación contra la imagen original.**

*Turns Chinese symbols and text into red-lacquer 3D `.glb` assets: exact line-and-arc reconstruction, rounded bevels and a strict image-matching verifier.*

![Galería de modelos](docs/galeria.png)

---

## Qué hace

A partir de una imagen plana de un sello, emblema o carácter chino (o de un texto y una fuente tipográfica), genera un modelo 3D listo para web, motores de juego o render:

- **Reconstrucción, no calco.** El trazo se redibuja con verticales, horizontales, arcos (cada uno con su centro ajustado) y rectas inclinadas. Cada cara de esa retícula se pinta por mayoría con la imagen, y un paso de corrección remienda lo que la retícula no explica. El resultado son bordes limpios, sin la escalera de píxeles de la imagen.
- **Acabado uniforme.** Canto de cuarto de círculo delante y detrás, esquinas redondeadas (las que sobresalen a 1,3× el canto, las que entran a 0,6×), normales exactas en frente y dorso y material PBR de laca roja. Todos los símbolos comparten el mismo aspecto.
- **Verificador estricto.** Cada modelo se compara con la imagen de origen antes de darse por bueno; si no aprueba, no se entrega.
- **Tres versiones por símbolo:** detallada, ligera (galería) y web (comprimida con meshopt).

## Galería

| Modelo | Carácter | Significado | Modo | Parecido (IoU) |
|---|---|---|---|---|
| `shou-circular` | 壽 shòu | Longevidad | simetría doble | 0,9785 |
| `shou-cruz` | 壽 shòu (estilizado) | Longevidad | `--simetria-ab` | 0,9839 |
| `shou-sello` | 壽 shòu (sello de bandas) | Longevidad | `--simetria-lr` | 0,9756 |
| `xi-doble` | 囍 shuāng xǐ | Doble felicidad | `--simetria-lr` | 0,9860 |
| `fu-trazo` | 福 fú | Buena suerte | `--sin-simetria` | 0,9813 |
| `fu-circular` | 福 fú (sello) | Buena suerte | `--sin-simetria` | 0,9749 |
| `fu-hiragino` | 福 fú (fuente Hiragino Sans GB) | Buena suerte | letras | 0,9901 |
| `amor` | AMOR (Avenir Next) | — | letras | 0,9893 |

Todos aprueban el verificador. Tamaños orientativos: detallada 1–2,5 MB, ligera 220–630 KB, web 70–205 KB.

## Instalación

Requiere Python 3.12 y, para la versión web, Node.js (`npx`).

```bash
git clone https://github.com/JesusGalindez/symbols-3D.git
cd symbols-3D
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Uso

### Símbolo desde una imagen

```bash
# 1. Generar el modelo (elegir el modo según la simetría del dibujo)
.venv/bin/python tools/redibujar.py fuentes/X.png X [--simetria-ab | --simetria-lr | --sin-simetria]

# 2. Verificar contra la imagen (código de salida 1 si falla)
.venv/bin/python tools/verificar.py glb/X.glb fuentes/X.png --informe informe.png

# 3. Versión ligera y versión web
.venv/bin/python tools/redibujar.py fuentes/X.png X [modo] --ligera
npx -y @gltf-transform/cli@4 optimize glb/X-ligera.glb glb/web/X-ligera.glb --compress meshopt --simplify false
```

Cómo elegir el modo (IoU de la máscara con su reflejo):

| Izquierda-derecha | Arriba-abajo | Opción |
|---|---|---|
| ≥ 0,97 | ≥ 0,97 | (ninguna): simetría doble |
| < 0,95 | ≥ 0,97 | `--simetria-ab` |
| ≥ 0,97 | < 0,95 | `--simetria-lr` |
| < 0,95 | < 0,95 | `--sin-simetria` |

Funciona mejor con imágenes de **500 px o más**, en PNG, con fondo liso y sin marca de agua. Detecta el trazo por color rojo o, si no lo hay, por tinta oscura.

### Letras y texto desde una fuente

```bash
.venv/bin/python tools/letras.py "AMOR" amor --fuente "/System/Library/Fonts/Avenir Next.ttc" --indice 0
.venv/bin/python tools/letras.py "福" fu-hiragino --fuente "/System/Library/Fonts/Hiragino Sans GB.ttc" --indice 2
```

El texto sale centrado en el origen. `--separadas` genera además un modelo por letra y `--ligera` la versión de galería. Escribe `fuentes/<nombre>.png` con la silueta exacta de la fuente, que sirve para verificarlo igual que un símbolo. Usa estilos gruesos (Bold, Demi, Heavy): en los finos el redondeo se come el trazo.

### Visor

```bash
.venv/bin/python -m http.server 8791
# abrir http://localhost:8791/visor.html?s=shou-cruz
```

En macOS basta con doble clic en `ver.command`. Parámetros: `?s=<modelo>` y, opcionalmente, `&cam=x,y,z&mira=x,y,z` para fijar la cámara.

### Vídeo para redes

Vídeo vertical 1080×1350, 10 s y 30 fps con música tradicional china sintetizada (guzheng, xiao), sin licencias de terceros:

```bash
.venv/bin/python video/musica.py                             # genera video/musica.wav
.venv/bin/python video/exportar.py fu-hiragino               # fotogramas + MP4 (≈13 min)
.venv/bin/python video/exportar.py fu-hiragino --solo-audio  # cambia solo la música, en segundos
```

Necesita Google Chrome. La escena está en `video/fu-x.html`; el rótulo está escrito para 福 y hay que cambiarlo para otros símbolos.

## El verificador

`tools/verificar.py` proyecta el modelo de frente, lo registra con la imagen (escala ±1 % y traslación) y exige:

| Criterio | Umbral |
|---|---|
| Parecido global (IoU) con la imagen tal cual | ≥ 0,97 |
| Contorno: percentil 95 de la distancia | ≤ 0,3 % del diámetro |
| Contorno: distancia máxima | ≤ 0,8 % del diámetro |
| Mayor zona de discrepancia | ≤ 0,02 % del área |
| Piezas y huecos | iguales que en la imagen |
| Malla | cerrada, con canto en todas las piezas, normales exactas y material `laca` |

Contorno y zonas se miden contra la imagen **con el mismo redondeo de esquinas aplicado**: el acabado no cuenta como error y todo lo demás sí. Con imágenes pequeñas, las tolerancias de distancia suben a medio píxel (p95) y 1,5 píxeles (máximo) del original, porque no se puede exigir más precisión que la de la fuente. El informe marca en rojo lo que falta y en verde lo que sobra, con las zonas numeradas de peor a mejor.

## Estructura

```
tools/
  redibujar.py   imagen → geometría exacta → .glb (modo principal)
  letras.py      texto + fuente .ttf/.otf/.ttc → .glb
  verificar.py   juez: .glb contra la imagen, PASA/FALLA por criterio
  simbolo.py     común: máscara, canto redondeado, normales, exportación
glb/             modelos detallados y ligeros · glb/web/ versiones meshopt
svg/             planta 2D de cada modelo y máscara de comprobación
fuentes/         imágenes de origen
video/           escena, exportador, música y vídeo de ejemplo
visor.html       visor three.js
docs/            imágenes del README
```

## Licencia

Código y modelos bajo licencia [MIT](LICENSE).

Los caracteres 壽, 福 y 囍 son símbolos tradicionales de dominio público. Las imágenes de origen de `shou-sello` y `xi-doble` procedían de bancos de imágenes con marca de agua y no se incluyen en el repositorio. Para uso comercial de esos dos modelos, conviene regenerarlos desde imágenes propias o con licencia.
