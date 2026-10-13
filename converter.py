import argparse
import logging
import os
import re
import shutil
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from rich.console import Console, Group
from rich.live import Live
from rich.progress import (
    BarColumn,
    DownloadColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.table import Column
from yt_dlp import YoutubeDL
from yt_dlp.cookies import extract_cookies_from_browser
from yt_dlp.utils import DownloadError

# Definicion de la ruta de descarga
download_path = "/home/jairo/Music"
# Navegador con la sesión de YouTube abierta: sin sus cookies YouTube devuelve
# la playlist vacía ("0 items of N")
cookies_browser = "brave"
# Descargas simultáneas. Con muchas más YouTube empieza a limitar o bloquear
default_workers = 4
log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "converter.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(log_file, encoding="utf-8")],
)
log = logging.getLogger("converter")
console = Console()

ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")
# Avisos que salen en cada vídeo y no impiden descargar
IGNORED_WARNINGS = ("JavaScript runtime", "challenge solving failed", "Signature solving failed")
# Cookies que YouTube solo pone con la sesión iniciada
SESSION_COOKIES = ("SAPISID", "__Secure-3PAPISID", "LOGIN_INFO")
# Errores que no se arreglan reintentando
PERMANENT_ERRORS = ("confirm your age", "Private video", "unavailable", "removed", "copyright", "not available in your country")


# Adaptador para que yt-dlp escriba solo en el fichero de log, no en pantalla
class YtdlpLogger:
    def __init__(self, prefix=""):
        self.prefix = prefix

    def _log(self, level, msg):
        log.log(level, self.prefix + ANSI_ESCAPE.sub("", msg))

    def debug(self, msg):
        # yt-dlp manda los mensajes informativos por debug con el prefijo "[...]"
        if not msg.startswith("[debug] "):
            self._log(logging.INFO, msg)

    def info(self, msg):
        self._log(logging.INFO, msg)

    def warning(self, msg):
        if not any(w in msg for w in IGNORED_WARNINGS):
            self._log(logging.WARNING, msg)

    def error(self, msg):
        self._log(logging.ERROR, msg)


# Comprueba que se pueden leer las cookies del navegador y que tienen una sesión
# de YouTube iniciada y sin caducar. Devuelve (válidas, explicación)
def check_cookies():
    try:
        jar = extract_cookies_from_browser(cookies_browser, logger=YtdlpLogger())
    except Exception as e:
        return False, f"no se pudieron leer las cookies de {cookies_browser}: {short_error(e)}"
    youtube = [c for c in jar if c.domain.endswith("youtube.com")]
    if not youtube:
        return False, f"{cookies_browser} no tiene cookies de YouTube (¿nunca has entrado a YouTube con él?)"
    session = [c for c in youtube if c.name in SESSION_COOKIES]
    if not session:
        return False, f"no hay sesión de YouTube iniciada en {cookies_browser}"
    if all(c.is_expired() for c in session):
        return False, f"la sesión de YouTube en {cookies_browser} ha caducado, vuelve a iniciar sesión"
    if not all(c.value for c in session):
        return False, f"las cookies de {cookies_browser} están cifradas y no se pudieron descifrar (¿llavero del sistema bloqueado?)"
    return True, f"sesión de YouTube en {cookies_browser}"


# Comprobaciones antes de empezar. Devuelve si se pueden usar las cookies
def preflight():
    if not shutil.which("ffmpeg"):
        console.print("[red]✗ ffmpeg no está instalado[/] (hace falta para convertir a mp3): sudo apt install ffmpeg")
        sys.exit(1)
    console.print("[green]✓[/] ffmpeg")

    with console.status(f"Comprobando cookies de {cookies_browser}..."):
        valid, detail = check_cookies()
    log.info(f"Cookies válidas: {valid} ({detail})")
    if valid:
        console.print(f"[green]✓[/] Cookies: {detail}")
    else:
        console.print(f"[yellow]! Cookies: {detail}[/]")
        console.print("  [dim]Se intentará sin cookies, pero YouTube puede devolver la playlist vacía[/]")
    return valid


# Obtiene los vídeos (id, url, título) de la playlist. YouTube a veces devuelve
# la página sin la lista de vídeos (0 de N), así que se reintenta.
def get_playlist(playlist_url, use_cookies, attempts=5):
    options = {
        "extract_flat": "in_playlist",
        "ignoreerrors": True,
        "logger": YtdlpLogger(),
    }
    if use_cookies:
        options["cookiesfrombrowser"] = (cookies_browser,)
    for attempt in range(1, attempts + 1):
        log.info(f"Leyendo playlist (intento {attempt}/{attempts}): {playlist_url}")
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(playlist_url, download=False)
        if info:
            entries = [e for e in info.get("entries") or [] if e and e.get("url")]
            if entries:
                log.info(f"Playlist '{info.get('title')}': {len(entries)} vídeos")
                return info.get("title") or playlist_url, entries
            log.warning(f"YouTube devolvió la playlist sin vídeos (total declarado: {info.get('playlist_count')})")
        time.sleep(2 * attempt)
    return None, []


# Mensaje de error corto para la pantalla: sin "ERROR: [youtube] <id>: "
def short_error(error):
    msg = ANSI_ESCAPE.sub("", str(error))
    msg = re.sub(r"^ERROR:\s*", "", msg)
    msg = re.sub(r"^\[[^\]]+\]\s*[\w-]+:\s*", "", msg)
    return msg.split(". ")[0][:100]


class Downloader:
    def __init__(self, temp_dir, songs_progress):
        self.temp_dir = temp_dir
        self.songs_progress = songs_progress

    def _options(self, entry, task_id):
        def on_progress(d):
            if d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                self.songs_progress.update(task_id, completed=d.get("downloaded_bytes", 0), total=total, status="descargando")
            elif d["status"] == "finished":
                self.songs_progress.update(task_id, status="convirtiendo a mp3")

        return {
            "format": "bestaudio/best",
            # Los ficheros intermedios (.webm, .part) van a una carpeta temporal;
            # en download_path solo aparece el .mp3 terminado
            "paths": {"home": download_path, "temp": self.temp_dir},
            "outtmpl": "%(title)s.%(ext)s",
            "postprocessors": [
                {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}
            ],
            # Sin cookies: con sesión iniciada YouTube exige resolver un reto JS
            # (necesita deno) y sin él solo ofrece imágenes, no audio
            "logger": YtdlpLogger(prefix=f"[{entry['id']}] "),
            "noprogress": True,
            "progress_hooks": [on_progress],
        }

    # Descarga una canción. Devuelve ("ok" | "existe" | "error", detalle).
    # YouTube a veces da 403 u otros fallos puntuales, así que se reintenta salvo
    # que el error sea permanente (edad, vídeo privado o borrado...)
    def download(self, entry, attempts=3):
        title = entry.get("title") or entry["id"]
        task_id = self.songs_progress.add_task(title, total=None, status="preparando")
        try:
            for attempt in range(1, attempts + 1):
                try:
                    with YoutubeDL(self._options(entry, task_id)) as ydl:
                        mp3 = ydl.prepare_filename({**entry, "title": title, "ext": "mp3"})
                        if os.path.exists(mp3):
                            return "existe", None
                        ydl.extract_info(entry["url"], download=True)
                    return "ok", None
                except DownloadError as e:
                    error = short_error(e)
                    if attempt == attempts or any(p in error for p in PERMANENT_ERRORS):
                        return "error", error
                    log.warning(f"[{entry['id']}] Reintentando ({attempt}/{attempts}): {error}")
                    self.songs_progress.update(task_id, completed=0, total=None, status=f"reintento {attempt + 1}/{attempts}")
                    time.sleep(3 * attempt)
        except Exception as e:
            log.exception(f"[{entry['id']}] Error inesperado")
            return "error", short_error(e)
        finally:
            self.songs_progress.remove_task(task_id)


# Función para descargar la playlist en MP3
def download_playlist(playlist_url, workers):
    os.makedirs(download_path, exist_ok=True)

    use_cookies = preflight()
    with console.status("Leyendo playlist..."):
        title, entries = get_playlist(playlist_url, use_cookies)
    if not entries:
        console.print("[red]✗ No se pudo obtener la lista de vídeos de la playlist[/] (detalles en converter.log)")
        log.error("No se pudo obtener la lista de vídeos de la playlist")
        return

    console.print(f"[bold]{title}[/]: {len(entries)} vídeos → {download_path} ({workers} descargas a la vez)")
    log.info(f"Descargando {len(entries)} vídeos -> {download_path} con {workers} hilos")

    total_progress = Progress(
        TextColumn("[bold]Total"),
        BarColumn(),
        MofNCompleteColumn(),
        TextColumn("•"),
        TimeElapsedColumn(),
        TextColumn("• quedan"),
        TimeRemainingColumn(),
        console=console,
    )
    songs_progress = Progress(
        SpinnerColumn(),
        TextColumn("{task.description}", table_column=Column(width=50, no_wrap=True, overflow="ellipsis")),
        BarColumn(bar_width=20),
        DownloadColumn(),
        TransferSpeedColumn(),
        TextColumn("[cyan]{task.fields[status]}"),
        console=console,
    )
    total_task = total_progress.add_task("total", total=len(entries))

    temp_dir = tempfile.mkdtemp(prefix="yt-playlist-")
    downloader = Downloader(temp_dir, songs_progress)
    results = {"ok": [], "existe": [], "error": []}

    executor = ThreadPoolExecutor(max_workers=workers)
    try:
        with Live(Group(songs_progress, total_progress), console=console, refresh_per_second=8):
            futures = {executor.submit(downloader.download, e): e for e in entries}
            for future in as_completed(futures):
                entry = futures[future]
                name = entry.get("title") or entry["id"]
                status, detail = future.result()
                results[status].append((name, entry["url"], detail))
                if status == "ok":
                    console.print(f"[green]✓[/] {name}")
                    log.info(f"OK: {name}")
                elif status == "error":
                    console.print(f"[red]✗ {name}[/] [dim]— {detail}[/]")
                    log.error(f"FALLO: {name} ({entry['url']}): {detail}")
                total_progress.advance(total_task)
    except KeyboardInterrupt:
        executor.shutdown(wait=False, cancel_futures=True)
        console.print("\n[yellow]Interrumpido.[/] Las canciones a medias se descartan.")
        log.warning("Interrumpido por el usuario")
        print_summary(results)
        shutil.rmtree(temp_dir, ignore_errors=True)
        # Los hilos con descargas en curso no se pueden parar de otra forma
        os._exit(130)

    executor.shutdown()
    shutil.rmtree(temp_dir, ignore_errors=True)
    print_summary(results)


def print_summary(results):
    ok, existing, failed = results["ok"], results["existe"], results["error"]
    console.print()
    console.rule("Resumen")
    console.print(f"[green]✓ Descargadas:[/] {len(ok)}")
    console.print(f"[dim]• Ya existían:[/] {len(existing)}")
    console.print(f"[red]✗ Fallidas:[/] {len(failed)}")
    for name, url, detail in failed:
        console.print(f"   [red]•[/] {name} [dim]({url})[/]\n     {detail}")
    log.info(f"Resumen: {len(ok)} descargadas, {len(existing)} ya existían, {len(failed)} fallidas")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Descarga una playlist de YouTube en MP3")
    parser.add_argument("url", nargs="?", help="URL de la playlist")
    parser.add_argument("-j", "--hilos", type=int, default=default_workers,
                        help=f"descargas simultáneas (por defecto {default_workers})")
    parser.add_argument("-n", "--navegador", default=cookies_browser,
                        help=f"navegador con la sesión de YouTube abierta (por defecto {cookies_browser})")
    args = parser.parse_args()
    cookies_browser = args.navegador

    # Obtener la URL de la playlist del usuario
    url = args.url or input("Ingrese la URL de la playlist de YouTube: ").strip()
    if not url:
        console.print("[red]No se ha introducido ninguna URL[/]")
        sys.exit(1)
    download_playlist(url, max(1, args.hilos))
