import logging
import os
import sys

from yt_dlp import YoutubeDL

# Definicion de la ruta de descarga
download_path = "/home/jairo/Music"
log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "converter.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(log_file, encoding="utf-8"), logging.StreamHandler()],
)
log = logging.getLogger("converter")


# Adaptador para que yt-dlp escriba en nuestro logger
class YtdlpLogger:
    def debug(self, msg):
        # yt-dlp manda los mensajes informativos por debug con el prefijo "[...]"
        if not msg.startswith("[debug] "):
            log.info(msg)

    def info(self, msg):
        log.info(msg)

    def warning(self, msg):
        log.warning(msg)

    def error(self, msg):
        log.error(msg)


# Función para descargar la playlist en MP3
def download_playlist(playlist_url):
    os.makedirs(download_path, exist_ok=True)

    options = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(download_path, "%(title)s.%(ext)s"),
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
        ],
        "ignoreerrors": True,  # Si un vídeo falla, seguir con el resto
        "logger": YtdlpLogger(),
    }

    log.info(f"Descargando playlist: {playlist_url} -> {download_path}")
    with YoutubeDL(options) as ydl:
        result = ydl.download([playlist_url])

    if result != 0:
        log.warning("Algunos vídeos no se pudieron descargar (ver mensajes de error arriba)")
    log.info("Terminado")


if __name__ == "__main__":
    # Obtener la URL de la playlist del usuario
    url = sys.argv[1] if len(sys.argv) > 1 else input("Ingrese la URL de la playlist de YouTube: ").strip()
    if not url:
        log.error("No se ha introducido ninguna URL")
        sys.exit(1)
    download_playlist(url)
