#!/usr/bin/env python3
"""
frame_extractor.py
Extrae frames desde una URL de video (YouTube, Twitch VOD, etc.) usando
yt-dlp + ffmpeg, SIN descargar el video completo a disco.

Estrategia:
  1. yt-dlp resuelve la URL directa del stream (no descarga nada, solo
     pide al servidor el enlace real del archivo de video).
  2. ffmpeg lee ese stream directamente por red y extrae los frames,
     usando -ss/-to para saltar (seek) al segmento pedido sin bajar
     el resto del video.

Requiere:
    - yt-dlp   (pip install -U yt-dlp)
    - ffmpeg   (debe estar en el PATH del sistema)

Ejemplos:
    python frame_extractor.py "https://youtu.be/XXXX"
    python frame_extractor.py "https://youtu.be/XXXX" --start 00:01:30 --end 00:02:00
    python frame_extractor.py "https://youtu.be/XXXX" --fps 1 --output ./frames
    python frame_extractor.py "https://youtu.be/XXXX" --format png --start 90 --end 120
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime

# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #

def check_dependency(cmd, install_hint):
    if shutil.which(cmd) is None:
        print(f"❌ No se encontró '{cmd}' en el sistema. {install_hint}")
        sys.exit(1)


TIME_RE = re.compile(r'^(\d{1,2}:)?\d{1,2}:\d{2}(\.\d+)?$|^\d+(\.\d+)?$')


def validate_time(value):
    """Acepta segundos puros ('90'), MM:SS ('01:30') o HH:MM:SS ('00:01:30')."""
    if value is None:
        return None
    if not TIME_RE.match(value):
        raise argparse.ArgumentTypeError(
            f"Formato de tiempo inválido: '{value}'. Usa SS, MM:SS o HH:MM:SS"
        )
    return value


def time_to_seconds(value):
    """
    Convierte un tiempo válido (SS, MM:SS o HH:MM:SS, ya validado por
    validate_time) a segundos totales (float). Usado para comparar
    duraciones contra límites de uso.
    """
    if value is None:
        return 0.0
    parts = value.split(":")
    parts = [float(p) for p in parts]
    while len(parts) < 3:
        parts.insert(0, 0.0)
    h, m, s = parts
    return h * 3600 + m * 60 + s


def sanitize_filename(name):
    name = re.sub(r'[\\/*?:"<>|]', "_", name).strip()
    return name or "video"


# --------------------------------------------------------------------------- #
# yt-dlp
# --------------------------------------------------------------------------- #

def get_video_title(video_url):
    try:
        result = subprocess.run(
            ["yt-dlp", "--no-playlist", "--print", "%(title)s", video_url],
            capture_output=True, text=True, check=True, timeout=30,
        )
        return sanitize_filename(result.stdout.strip()) or "video"
    except Exception:
        return "video"


def get_direct_stream_url(video_url, format_selector, cookies_file=None):
    """
    Resuelve la URL directa del stream de video (sin descargar el archivo).
    """
    cmd = [
        "yt-dlp",
        "-f", format_selector,
        "-g",              # get-url: solo imprime la(s) URL(s) directa(s)
        "--no-playlist",
    ]
    if cookies_file:
        cmd += ["--cookies", cookies_file]
    cmd.append(video_url)

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=True, timeout=60
        )
    except FileNotFoundError:
        print("❌ No se encontró el ejecutable 'yt-dlp'.")
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print("❌ yt-dlp no pudo resolver la URL del video.")
        print(e.stderr.strip())
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print("❌ Tiempo de espera agotado al consultar yt-dlp.")
        sys.exit(1)

    urls = [u for u in result.stdout.strip().splitlines() if u.strip()]
    if not urls:
        print("❌ yt-dlp no devolvió ninguna URL de stream. "
              "¿El video es privado, geo-restringido o requiere login?")
        sys.exit(1)

    # Con el selector "bestvideo" debería devolver solo 1 URL (video sin audio),
    # que es lo único que necesitamos para extraer frames.
    return urls[0]


# --------------------------------------------------------------------------- #
# ffmpeg
# --------------------------------------------------------------------------- #

def build_ffmpeg_cmd(stream_url, output_folder, start, end, fps, img_format, quality):
    pattern = os.path.join(output_folder, f"frame_%05d.{img_format}")

    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-stats"]

    # -ss ANTES de -i = "fast seek": ffmpeg salta directo al punto pedido
    # en el stream remoto en vez de leer y descartar todo lo anterior.
    if start:
        cmd += ["-ss", start]

    cmd += ["-i", stream_url]

    if end:
        # Con -ss antes de -i, ffmpeg (versiones modernas) interpreta -to
        # como tiempo absoluto del archivo original automáticamente.
        cmd += ["-to", end]

    if fps:
        cmd += ["-vf", f"fps={fps}"]

    if img_format in ("jpg", "jpeg"):
        cmd += ["-q:v", str(quality)]  # 2 = mejor calidad, 31 = peor

    cmd.append(pattern)
    return cmd


def build_ffmpeg_snapshot_cmd(stream_url, output_path, timestamp, quality):
    """
    Construye el comando ffmpeg para extraer UN solo frame en un timestamp
    exacto. Usa -ss antes de -i (fast seek) y -vframes 1, así no decodifica
    nada del video que no sea el frame pedido: es casi instantáneo comparado
    con escanear un segmento completo a X fps.
    """
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-ss", timestamp,
        "-i", stream_url,
        "-vframes", "1",
    ]
    if output_path.endswith((".jpg", ".jpeg")):
        cmd += ["-q:v", str(quality)]
    cmd.append(output_path)
    return cmd


def extract_frames_at_timestamps(stream_url, output_folder, timestamps, img_format, quality):
    """
    Extrae un frame por cada timestamp en la lista `timestamps`.
    Cada uno es una llamada independiente a ffmpeg (una por captura), lo que
    permite seek rápido a cada punto sin tener que leer/descartar todo lo
    que hay entre ellos.
    """
    results = []
    for i, ts in enumerate(timestamps, start=1):
        safe_ts = ts.replace(":", "-")
        filename = f"shot_{i:03d}_{safe_ts}.{img_format}"
        output_path = os.path.join(output_folder, filename)
        cmd = build_ffmpeg_snapshot_cmd(stream_url, output_path, ts, quality)
        print(f"📸 Capturando frame en {ts} -> {filename}")
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            results.append(output_path)
        except subprocess.CalledProcessError as e:
            print(f"⚠ No se pudo capturar el frame en {ts}: {e.stderr.strip()}")
        except FileNotFoundError:
            print("❌ No se encontró el ejecutable 'ffmpeg'.")
            sys.exit(1)
    return results


def run_ffmpeg(cmd):
    print("\n▶ Ejecutando ffmpeg:")
    print("   " + " ".join(cmd) + "\n")
    try:
        subprocess.run(cmd, check=True)
    except FileNotFoundError:
        print("❌ No se encontró el ejecutable 'ffmpeg'.")
        sys.exit(1)
    except subprocess.CalledProcessError:
        print("❌ ffmpeg falló durante la extracción de frames "
              "(revisa que --start/--end estén dentro de la duración del video).")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n⚠ Extracción interrumpida por el usuario.")
        sys.exit(1)


def count_frames(output_folder, img_format):
    if not os.path.isdir(output_folder):
        return 0
    return len([f for f in os.listdir(output_folder) if f.endswith(f".{img_format}")])


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main():
    parser = argparse.ArgumentParser(
        description="Extrae frames desde una URL de video usando yt-dlp + ffmpeg, "
                    "sin descargar el video completo."
    )
    parser.add_argument("url", nargs="?", help="URL del video (YouTube, etc.)")
    parser.add_argument("--start", type=validate_time, default=None,
                         help="Inicio del recorte: SS, MM:SS o HH:MM:SS")
    parser.add_argument("--end", type=validate_time, default=None,
                         help="Fin del recorte: SS, MM:SS o HH:MM:SS")
    parser.add_argument("--fps", type=float, default=None,
                         help="Frames por segundo a extraer (ej. 1 = 1 frame/seg). "
                              "Si se omite, extrae TODOS los frames del segmento.")
    parser.add_argument("--timestamps", type=str, default=None,
                         help="Lista de momentos exactos separados por coma "
                              "(ej. '00:01:23,00:04:56,90'). Si se usa, ignora "
                              "--start/--end/--fps y captura solo un frame por "
                              "cada timestamp (más rápido para pocas capturas).")
    parser.add_argument("--output", default=None,
                         help="Carpeta de salida (default: ~/Downloads/extracted_frames/<titulo>)")
    parser.add_argument("--format", choices=["jpg", "png"], default="jpg",
                         help="Formato de imagen de salida (default: jpg)")
    parser.add_argument("--quality", type=int, default=2,
                         help="Calidad JPG: 2 (mejor) a 31 (peor). Default: 2")
    parser.add_argument("--video-format", default="bestvideo[ext=mp4]/bestvideo/best",
                         help="Selector de formato de yt-dlp (avanzado)")
    parser.add_argument("--cookies", default=None,
                         help="Ruta a archivo de cookies (para videos privados/con login)")

    args = parser.parse_args()

    check_dependency("yt-dlp", "Instálalo con: pip install -U yt-dlp")
    check_dependency("ffmpeg", "Instálalo desde https://ffmpeg.org/download.html y asegúrate de que esté en tu PATH.")

    video_url = args.url or input("Pega aquí la URL del video: ").strip()
    if not video_url:
        print("❌ No se proporcionó ninguna URL.")
        sys.exit(1)

    print("🔎 Resolviendo información del video...")
    title = get_video_title(video_url)

    output_folder = args.output or os.path.join(
        os.path.expanduser("~/Downloads/extracted_frames"), title
    )
    os.makedirs(output_folder, exist_ok=True)

    print("🔗 Resolviendo URL directa del stream (sin descargar)...")
    stream_url = get_direct_stream_url(video_url, args.video_format, args.cookies)

    t0 = datetime.now()

    if args.timestamps:
        timestamps = [validate_time(t.strip()) for t in args.timestamps.split(",") if t.strip()]
        if not timestamps:
            print("❌ No se proporcionó ningún timestamp válido.")
            sys.exit(1)
        results = extract_frames_at_timestamps(
            stream_url, output_folder, timestamps, args.format, args.quality
        )
        elapsed = (datetime.now() - t0).total_seconds()
        print(f"\n✅ {len(results)}/{len(timestamps)} frames capturados en {elapsed:.1f}s")
    else:
        cmd = build_ffmpeg_cmd(
            stream_url, output_folder, args.start, args.end,
            args.fps, args.format, args.quality
        )
        run_ffmpeg(cmd)
        elapsed = (datetime.now() - t0).total_seconds()
        total = count_frames(output_folder, args.format)
        print(f"\n✅ {total} frames extraídos en {elapsed:.1f}s")

    print(f"📂 Carpeta: {output_folder}")


if __name__ == "__main__":
    main()
