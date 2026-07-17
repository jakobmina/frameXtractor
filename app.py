#!/usr/bin/env python3
"""
app.py
Interfaz Streamlit para frame_extractor. Reusa toda la lógica de main.py
(get_video_title, get_direct_stream_url, build_ffmpeg_cmd, run_ffmpeg,
extract_frames_at_timestamps, etc.) sin duplicar código.

Correr con:
    streamlit run app.py
"""

import io
import os
import shutil
import tempfile
import zipfile

import streamlit as st

import main as core  # reusa toda la lógica de main.py

st.set_page_config(page_title="Frame Xtractor", page_icon="🎬", layout="centered")

# --------------------------------------------------------------------------- #
# Límites del plan gratuito
# --------------------------------------------------------------------------- #
# La versión gratuita está pensada para FRAGMENTOS CORTOS, no para procesar
# videos completos de larga duración (eso queda reservado para un plan
# premium a futuro). Ajusta estas constantes según la política de producto.

MAX_FREE_SEGMENT_SECONDS = 120   # tope de duración del segmento en modo "serie de frames"
MAX_FREE_TIMESTAMPS = 10         # tope de capturas puntuales en modo "capturas exactas"

# --------------------------------------------------------------------------- #
# Dependencias
# --------------------------------------------------------------------------- #

missing = [cmd for cmd in ("yt-dlp", "ffmpeg") if shutil.which(cmd) is None]
if missing:
    st.error(
        f"❌ Faltan dependencias en el sistema: {', '.join(missing)}. "
        "Instálalas antes de continuar (yt-dlp: `pip install -U yt-dlp`, "
        "ffmpeg: `apt install ffmpeg` o desde ffmpeg.org)."
    )
    st.stop()

# --------------------------------------------------------------------------- #
# Estado
# --------------------------------------------------------------------------- #

if "timestamps" not in st.session_state:
    st.session_state.timestamps = [""]
if "results" not in st.session_state:
    st.session_state.results = []  # lista de rutas de archivos generados
if "work_dir" not in st.session_state:
    st.session_state.work_dir = None

# --------------------------------------------------------------------------- #
# UI
# --------------------------------------------------------------------------- #

st.title("🎬 Frame Xtractor")
st.caption("Extrae frames de un video (YouTube, etc.) sin descargarlo completo.")

video_url = st.text_input("URL del video", placeholder="https://youtu.be/XXXX")

img_format = st.selectbox(
    "Formato de imagen", ["png", "jpg"],
    help="png = sin pérdida de calidad (más pesado). jpg = más liviano.",
)
quality = st.slider(
    "Calidad JPG (solo aplica si eliges jpg)", min_value=2, max_value=31, value=2,
    help="2 = mejor calidad, 31 = peor calidad.",
)

mode = st.radio(
    "¿Qué necesitas?",
    ["📸 Capturas exactas (pocos momentos puntuales)", "🎞️ Serie de frames (segmento completo)"],
)

# --------------------------------------------------------------------------- #
# Modo: capturas exactas
# --------------------------------------------------------------------------- #

if mode.startswith("📸"):
    st.subheader("Momentos a capturar")
    st.caption(
        f"Formato: SS, MM:SS o HH:MM:SS (ej. 90, 01:30, 00:01:30). "
        f"🆓 Plan gratuito: hasta {MAX_FREE_TIMESTAMPS} capturas por video."
    )

    for i, ts in enumerate(st.session_state.timestamps):
        cols = st.columns([5, 1])
        st.session_state.timestamps[i] = cols[0].text_input(
            f"Momento {i + 1}", value=ts, key=f"ts_{i}", label_visibility="collapsed",
            placeholder="ej. 00:01:23",
        )
        if len(st.session_state.timestamps) > 1:
            if cols[1].button("✕", key=f"del_{i}"):
                st.session_state.timestamps.pop(i)
                st.rerun()

    if st.button("➕ Agregar captura"):
        st.session_state.timestamps.append("")
        st.rerun()

    extract_clicked = st.button("🚀 Extraer capturas", type="primary")

    if extract_clicked:
        raw_timestamps = [t.strip() for t in st.session_state.timestamps if t.strip()]
        if not video_url:
            st.warning("Ingresa la URL del video.")
        elif not raw_timestamps:
            st.warning("Agrega al menos un momento a capturar.")
        elif len(raw_timestamps) > MAX_FREE_TIMESTAMPS:
            st.error(
                f"⚠️ El plan gratuito permite hasta {MAX_FREE_TIMESTAMPS} capturas por video. "
                f"Tienes {len(raw_timestamps)}. Elimina algunas o próximamente podrás "
                "desbloquear capturas ilimitadas con el plan premium."
            )
        else:
            try:
                timestamps = [core.validate_time(t) for t in raw_timestamps]
            except Exception as e:
                st.error(f"❌ {e}")
                st.stop()

            with st.spinner("Resolviendo información del video..."):
                title = core.get_video_title(video_url)

            work_dir = tempfile.mkdtemp(prefix="frames_")
            os.makedirs(work_dir, exist_ok=True)

            with st.spinner("Resolviendo URL directa del stream (sin descargar)..."):
                stream_url = core.get_direct_stream_url(video_url, "bestvideo[ext=mp4]/bestvideo/best")

            with st.spinner(f"Capturando {len(timestamps)} frame(s)..."):
                results = core.extract_frames_at_timestamps(
                    stream_url, work_dir, timestamps, img_format, quality
                )

            st.session_state.results = results
            st.session_state.work_dir = work_dir
            st.session_state.video_title = title

# --------------------------------------------------------------------------- #
# Modo: serie de frames (segmento a fps)
# --------------------------------------------------------------------------- #

else:
    st.subheader("Segmento a extraer")
    st.caption(
        f"🆓 Plan gratuito: fragmentos cortos, hasta {MAX_FREE_SEGMENT_SECONDS // 60} minutos "
        "por extracción. El video completo estará disponible en el plan premium."
    )
    col1, col2 = st.columns(2)
    start = col1.text_input("Inicio (opcional)", placeholder="00:01:00")
    end = col2.text_input("Fin (opcional)", placeholder="00:02:00")
    fps = st.number_input(
        "Frames por segundo a extraer", min_value=0.1, max_value=30.0, value=1.0, step=0.5,
        help="1.0 = un frame cada segundo. Valores altos generan MUCHOS archivos.",
    )

    extract_clicked = st.button("🚀 Extraer serie de frames", type="primary")

    if extract_clicked:
        if not video_url:
            st.warning("Ingresa la URL del video.")
        else:
            try:
                start_v = core.validate_time(start) if start.strip() else None
                end_v = core.validate_time(end) if end.strip() else None
            except Exception as e:
                st.error(f"❌ {e}")
                st.stop()

            if start_v is None or end_v is None:
                st.error(
                    "⚠️ En el plan gratuito, la extracción por segmento requiere "
                    "especificar Inicio y Fin (no se puede procesar el video completo). "
                    f"Duración máxima por segmento: {MAX_FREE_SEGMENT_SECONDS // 60} min. "
                    "El procesamiento del video completo estará disponible en el plan premium."
                )
                st.stop()

            segment_seconds = core.time_to_seconds(end_v) - core.time_to_seconds(start_v)
            if segment_seconds <= 0:
                st.error("❌ El Fin debe ser posterior al Inicio.")
                st.stop()
            if segment_seconds > MAX_FREE_SEGMENT_SECONDS:
                st.error(
                    f"⚠️ El segmento pedido dura {segment_seconds:.0f}s, y el plan gratuito "
                    f"permite hasta {MAX_FREE_SEGMENT_SECONDS}s ({MAX_FREE_SEGMENT_SECONDS // 60} min) "
                    "por extracción. Acorta el rango o próximamente podrás desbloquear "
                    "segmentos más largos con el plan premium."
                )
                st.stop()

            with st.spinner("Resolviendo información del video..."):
                title = core.get_video_title(video_url)

            work_dir = tempfile.mkdtemp(prefix="frames_")
            os.makedirs(work_dir, exist_ok=True)

            with st.spinner("Resolviendo URL directa del stream (sin descargar)..."):
                stream_url = core.get_direct_stream_url(video_url, "bestvideo[ext=mp4]/bestvideo/best")

            cmd = core.build_ffmpeg_cmd(stream_url, work_dir, start_v, end_v, fps, img_format, quality)

            with st.spinner("Extrayendo frames con ffmpeg... (puede tardar según la duración)"):
                core.run_ffmpeg(cmd)

            results = sorted(
                os.path.join(work_dir, f) for f in os.listdir(work_dir)
                if f.endswith(f".{img_format}")
            )
            st.session_state.results = results
            st.session_state.work_dir = work_dir
            st.session_state.video_title = title

# --------------------------------------------------------------------------- #
# Resultados
# --------------------------------------------------------------------------- #

if st.session_state.results:
    st.success(f"✅ {len(st.session_state.results)} frame(s) extraído(s)")

    preview = st.session_state.results[:12]
    cols = st.columns(4)
    # use_container_width se agregó en Streamlit 1.29+; en versiones más
    # viejas (ej. la que trae Anaconda por default) el parámetro equivalente
    # es use_column_width. Se intenta el nuevo y se cae al viejo si falla,
    # para no depender de que el usuario tenga Streamlit actualizado.
    for i, path in enumerate(preview):
        try:
            cols[i % 4].image(path, caption=os.path.basename(path), use_container_width=True)
        except TypeError:
            cols[i % 4].image(path, caption=os.path.basename(path), use_column_width=True)
    if len(st.session_state.results) > 12:
        st.caption(f"...y {len(st.session_state.results) - 12} más (incluidos en la descarga).")

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in st.session_state.results:
            zf.write(path, arcname=os.path.basename(path))
    zip_buffer.seek(0)

    st.download_button(
        "⬇️ Descargar todo (.zip)",
        data=zip_buffer,
        file_name=f"{st.session_state.get('video_title', 'frames')}.zip",
        mime="application/zip",
    )
