# Frame Xtractor 🎬

Extrae frames de un video (YouTube, Twitch VOD, etc.) usando `yt-dlp` + `ffmpeg`,
**sin descargar el video completo a disco**. Pensado para creadores de contenido
que necesitan capturas de alta calidad (mejor que un screenshot) de momentos
puntuales o de un fragmento corto.

## Cómo funciona

1. `yt-dlp` resuelve la URL directa del stream (no descarga nada, solo pide al
   servidor el enlace real del archivo de video).
2. `ffmpeg` lee ese stream directamente por red y extrae los frames, usando
   `-ss`/`-to` para saltar (seek) al segmento pedido sin bajar el resto del video.

## Requisitos

- Python 3.9+
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) (`pip install -U yt-dlp`)
- [ffmpeg](https://ffmpeg.org/download.html) instalado y disponible en el `PATH`
  del sistema (verifica con `which ffmpeg`)

```bash
pip install -r requirements.txt
```

## Uso — línea de comandos (`main.py`)
usage python3 main.py "https://youtu.be/xxxxxxxxxx" \
  --start 00:05:00 \ #hh/mm/ss
  --end 00:05:30 \#hh/mm/ss
  --fps 1            # frames per sec
si=tTQvPKelyzv2DR6V" --timestamps "00:01:23,00:04:56,90" --format png (env) (base) user@jmydevice:~/Downloadss/frameXtractor$ python3 main.py "https://youtu.be/xxxxxxxxxx" --timestamps "00:01:23,00:04:56,90" --format png

🔎 Resolviendo información del video...

🔗 Resolviendo URL directa del stream (sin descargar)...

📸 Capturando frame en 00:01:23 -> shot_001_00-01-23.png

📸 Capturando frame en 00:04:56 -> shot_002_00-04-56.png

📸 Capturando frame en 90 -> shot_003_90.png

✅ 3/3 frames capturados en 6.9s

📂 Carpeta: /home/user/Downloads/extracted_frames/Video title


### Serie de frames en un segmento

```bash
python3 main.py "https://youtu.be/XXXX" --start 00:01:00 --end 00:02:00 --fps 1
```

- `--start` / `--end`: recorta el segmento a procesar (formato `SS`, `MM:SS` o `HH:MM:SS`)
- `--fps`: frames por segundo a extraer. Si se omite, extrae **todos** los
  frames del segmento (puede generar miles de archivos).
- `--format`: `jpg` (default) o `png` (sin pérdida de calidad, más pesado)
- `--quality`: calidad JPG, `2` (mejor) a `31` (peor). Default `2`.
- `--output`: carpeta de salida. Default `~/Downloads/extracted_frames/<título>`
- `--cookies`: ruta a archivo de cookies, para videos privados o con login

### Capturas exactas en momentos puntuales

Para cuando solo necesitas unos pocos frames en timestamps específicos, en vez
de escanear todo un segmento:

```bash
python3 main.py "https://youtu.be/XXXX" --timestamps "00:01:23,00:04:56,90"
```

Cada timestamp genera **un solo frame** mediante seek rápido (`-ss` antes de
`-i` + `-vframes 1`), mucho más rápido que un escaneo por fps cuando solo
necesitas unas pocas capturas puntuales. Ignora `--start`/`--end`/`--fps` si
se usa junto con `--timestamps`.

## Uso — interfaz web (`app.py`, Streamlit)

```bash
streamlit run app.py
```

Se abre en `http://localhost:8501`. Ofrece los mismos dos modos que el CLI
(Capturas exactas / Serie de frames) con una interfaz visual: agregar/quitar
timestamps con botones, sliders para calidad, preview de las imágenes
generadas y descarga de todo como `.zip` con un click.

### ⚠️ Límites del plan gratuito

La versión gratuita de la app web está diseñada explícitamente para
**fragmentos cortos**, no para procesar videos completos de larga duración:

| Modo | Límite gratuito |
|---|---|
| Serie de frames (segmento) | Hasta **2 minutos** por extracción. Requiere especificar Inicio y Fin — no se puede procesar el video completo. |
| Capturas exactas (timestamps) | Hasta **10 capturas** por video. |

Estos límites existen para mantener el servicio sostenible en el plan
gratuito. **El procesamiento de videos completos y capturas ilimitadas
están planeados para un plan premium** a futuro.

> Nota: estos límites aplican solo a `app.py` (la interfaz web). El script
> `main.py` (CLI, uso local) no tiene restricciones — corre en tu propia
> máquina con tus propios recursos.

Los límites son configurables en `app.py` vía las constantes
`MAX_FREE_SEGMENT_SECONDS` y `MAX_FREE_TIMESTAMPS`.

## Notas sobre calidad

Extraer frames directo del stream con ffmpeg da mejor calidad que un
screenshot de pantalla, porque evita la doble compresión del player de video.
Para máxima fidelidad (sin pérdida), usa `--format png`.
