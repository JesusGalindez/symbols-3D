"""Música del vídeo: guzheng, xiao y un colchón grave, sintetizados aquí (sin licencias).

Uso:  .venv/bin/python video/musica.py      Salida: video/musica.wav (48 kHz, estéreo, 10 s)

Pentatónica de re (re mi fa# la si), como la música tradicional china. Va sincronizada
con fu-x.html: entrada suave mientras gira el carácter, frase de xiao, glissando de
guzheng cuando pasa el brillo y aparece el rótulo (6 s), y cola que muere con el fundido.
Cada nota es síntesis aditiva: armónicos con su propio decaimiento, como una cuerda real.
"""
import subprocess
import wave
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from scipy.signal import butter, fftconvolve, sosfilt

SR, DURACION = 48000, 10.0
RAIZ = Path(__file__).resolve().parent
t_total = np.arange(int(SR * DURACION)) / SR
azar = np.random.default_rng(8)


def hz(nota):
    """'D4', 'F#5'… -> hercios (temperamento igual, la4 = 440)."""
    nombres = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
    n = nombres[nota[0]] + (1 if "#" in nota else 0)
    return 440 * 2 ** ((n + 12 * (int(nota[-1]) + 1) - 69) / 12)


def filtro(x, tipo, f):
    return sosfilt(butter(2, f, tipo, fs=SR, output="sos"), x)


def guzheng(nota, dur=3.5, fuerza=1.0, doblar=0.0):
    """Cuerda pulsada: armónicos con peine de punto de pulsación (p = 0,13), los agudos
    se apagan antes; doblar = semitonos de presión de la mano izquierda (滑音) tras 0,35 s."""
    t = np.arange(int(SR * dur)) / SR
    f0 = hz(nota)
    curva = 1 + (2 ** (doblar / 12) - 1) * np.clip((t - 0.35) / 0.25, 0, 1) ** 2
    fase = 2 * np.pi * np.cumsum(f0 * curva) / SR
    y = np.zeros_like(t)
    for k in range(1, 16):
        if k * f0 > 16000:
            break
        amp = abs(np.sin(np.pi * k * 0.13)) / k ** 1.05
        tau = 2.6 / (1 + 0.45 * (k - 1))
        y += amp * np.exp(-t / tau) * np.sin(k * fase * (1 + 0.0004 * k * k))
    y *= np.clip(t / 0.003, 0, 1)
    ruido = filtro(azar.standard_normal(len(t)), "bandpass", [1800, 5000]) * np.exp(-t / 0.012)
    return fuerza * (y + 0.25 * ruido)


def xiao(nota, dur, fuerza=1.0):
    """Flauta de bambú: casi senoidal, vibrato que entra tarde, soplo filtrado."""
    t = np.arange(int(SR * dur)) / SR
    vib = 1 + 0.004 * np.sin(2 * np.pi * 5.2 * t) * np.clip((t - 0.35) / 0.4, 0, 1)
    fase = 2 * np.pi * np.cumsum(hz(nota) * vib) / SR
    tono = np.sin(fase) + 0.22 * np.sin(2 * fase) + 0.07 * np.sin(3 * fase)
    env = np.clip(t / 0.18, 0, 1) * np.clip((dur - t) / 0.35, 0, 1)
    soplo = filtro(azar.standard_normal(len(t)), "bandpass", [hz(nota) * 1.5, hz(nota) * 5])
    return fuerza * env * (tono + 0.35 * soplo * (0.4 + 0.6 * env))


def colchon():
    """Re y la graves, lentos y anchos; entra con el vídeo."""
    t = t_total
    y = sum(a * np.sin(2 * np.pi * hz(n) * (1 + d) * t) for n, a in (("D2", 1), ("A2", .6), ("D3", .35))
            for d in (-0.0015, 0.0015))
    return 0.5 * y * np.clip(t / 2.0, 0, 1) * (0.85 + 0.15 * np.sin(2 * np.pi * 0.2 * t))


def poner(pista, sonido, en, pan):
    """Suma el sonido en la pista estéreo a partir del segundo `en`; pan -1 izq … 1 der."""
    i = int(en * SR)
    s = sonido[:len(pista) - i]
    pista[i:i + len(s), 0] += s * np.sqrt((1 - pan) / 2)
    pista[i:i + len(s), 1] += s * np.sqrt((1 + pan) / 2)


def reverberacion(x, segundos=2.8, mezcla=0.32):
    n = int(SR * segundos)
    t = np.arange(n) / SR
    ir = [filtro(azar.standard_normal(n), "lowpass", 6000) * np.exp(-t / (segundos / 6.9)) for _ in range(2)]
    for c in ir:
        c[:int(0.018 * SR)] = 0  # predelay: la nota seca va por delante
        c /= np.sqrt((c ** 2).sum())
    humedo = np.stack([fftconvolve(x[:, i], ir[i])[:len(x)] for i in range(2)], 1)
    return (1 - mezcla) * x + mezcla * 3.2 * humedo


def main():
    seco = np.zeros((len(t_total), 2))
    col = colchon()
    seco += np.stack([col, col], 1) * 0.35

    # entrada: el carácter gira y se acerca (0–4,5 s)
    for en, nota, f, d in [(0.35, "D3", .8, 0), (1.15, "A3", .6, 0), (1.8, "D4", .6, 0),
                           (2.55, "F#4", .55, 0), (3.2, "E4", .6, -1), (4.1, "B3", .5, 0),
                           (4.55, "A3", .7, 0)]:
        poner(seco, guzheng(nota, fuerza=f, doblar=d), en, -0.25 + 0.1 * (hz(nota) > 300))
    for en, nota, dur in [(2.0, "A4", 1.25), (3.2, "B4", 0.5), (3.65, "A4", 0.6), (4.2, "F#4", 1.4)]:
        poner(seco, xiao(nota, dur, .22), en, 0.3)

    # pasa el brillo y entra el rótulo: glissando ascendente que acaba en re5 a las 6,0 s
    gliss = ["D4", "E4", "F#4", "A4", "B4", "D5", "E5", "F#5", "A5"]
    for i, nota in enumerate(gliss):
        poner(seco, guzheng(nota, 2.5, .28 + .03 * i), 5.62 + 0.045 * i, -0.5 + i / 8)
    poner(seco, guzheng("D5", 4.0, .9), 6.05, 0.1)
    poner(seco, guzheng("D4", 4.0, .6), 6.05, -0.1)

    # cierre: xiao largo sobre re, guzheng grave que se apaga con el fundido
    poner(seco, xiao("D5", 1.9, .2), 6.6, 0.3)
    poner(seco, xiao("A4", 1.3, .18), 8.3, 0.3)
    poner(seco, guzheng("A3", fuerza=.55), 7.4, -0.2)
    poner(seco, guzheng("D3", fuerza=.7), 8.2, -0.25)

    y = reverberacion(filtro(seco.T, "highpass", 45).T)
    y *= np.clip(t_total / 0.4, 0, 1)[:, None]                                # sin chasquido
    y *= (1 - np.clip((t_total - 9.2) / 0.8, 0, 1) ** 1.5)[:, None]           # con el fundido
    y *= 10 ** (-2.4 / 20) / np.abs(y).max()                                   # ≈ -16 LUFS, suave

    ruta = RAIZ / "musica.wav"
    with wave.open(str(ruta), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes((y * 32767).astype("<i2").tobytes())
    # sonoridad medida (EBU R128), para dejarla a unos -16 LUFS al mezclar
    r = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-i", str(ruta),
                        "-af", "ebur128", "-f", "null", "-"], capture_output=True, text=True)
    print(ruta)
    print([l.strip() for l in r.stderr.splitlines() if l.strip().startswith(("I:", "Peak"))][-1:])


if __name__ == "__main__":
    main()
