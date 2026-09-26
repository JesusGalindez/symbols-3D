"""Renderiza video/fu-x.html fotograma a fotograma y lo codifica para X.

Uso:  .venv/bin/python video/exportar.py [modelo]      (por defecto fu-hiragino)
      .venv/bin/python video/exportar.py [modelo] --solo-audio   reusa los fotogramas ya
      renderizados en video/cuadros/<modelo>/ y solo vuelve a mezclar video/musica.wav
Salida: video/<modelo>-x.mp4  (1080×1350, 30 fps, H.264 High, yuv420p, faststart, AAC 192k)
Antes: video/musica.py genera video/musica.wav.

Levanta un servidor local que sirve el proyecto y recibe los PNG por POST, abre Chrome
sin ventana en la página, espera a /fin y codifica con el ffmpeg de imageio-ffmpeg.
"""
import http.server
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import imageio_ffmpeg

RAIZ = Path(__file__).resolve().parent.parent
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PUERTO = 8830
solo_audio = "--solo-audio" in sys.argv
args = [a for a in sys.argv[1:] if a != "--solo-audio"]
modelo = args[0] if args else "fu-hiragino"
cuadros = RAIZ / "video" / "cuadros" / modelo
fin = threading.Event()


class Manejador(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(RAIZ), **k)

    def do_POST(self):
        cuerpo = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.path.startswith("/frame/"):
            (cuadros / Path(self.path).name).write_bytes(cuerpo)
            n = int(Path(self.path).stem)
            if n % 30 == 0:
                print(f"  fotograma {n}", flush=True)
        elif self.path == "/fin":
            fin.set()
        self.send_response(204)
        self.end_headers()

    def log_message(self, *a):
        pass


def renderizar():
    shutil.rmtree(cuadros, ignore_errors=True)
    cuadros.mkdir(parents=True)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", PUERTO), Manejador)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    # sin --user-data-dir: con un perfil nuevo Chrome headless se queda colgado en este Mac
    chrome = subprocess.Popen(
        [CHROME, "--headless=new", "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
         "--window-size=600,760", f"http://127.0.0.1:{PUERTO}/video/fu-x.html?s={modelo}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if not fin.wait(timeout=3600):
            sys.exit("no llegó /fin en una hora")
    finally:
        chrome.kill()
        srv.shutdown()


def main():
    if not solo_audio:
        renderizar()
    salida = RAIZ / "video" / f"{modelo}-x.mp4"
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error",
                    "-framerate", "30", "-i", str(cuadros / "%04d.png"),
                    "-i", str(RAIZ / "video" / "musica.wav"),  # de video/musica.py
                    "-c:a", "aac", "-b:a", "192k", "-shortest",
                    "-c:v", "libx264", "-profile:v", "high", "-preset", "slow", "-crf", "17",
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(salida)], check=True)
    print(salida)


if __name__ == "__main__":
    main()
