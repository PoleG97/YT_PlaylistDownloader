# YT Playlist Downloader

Descarga una playlist de YouTube y convierte cada vídeo a MP3, con varias descargas en paralelo y barras de progreso.

## Requisitos

- Linux con Python 3
- `ffmpeg` (`sudo apt install ffmpeg`)
- Un navegador con la sesión de YouTube iniciada (por defecto **Brave**). Sin sus cookies, YouTube a menudo devuelve la playlist vacía.

Las dependencias de Python (`requirements.txt`) se instalan solas la primera vez que se ejecuta `descargar.sh`.

## Uso

```bash
./descargar.sh "https://www.youtube.com/playlist?list=..."
```

Si no se pasa la URL, la pide por teclado.

Para lanzarlo desde cualquier carpeta como `descargar-playlist`:

```bash
ln -s "$PWD/descargar.sh" ~/.local/bin/descargar-playlist
descargar-playlist "https://www.youtube.com/playlist?list=..."
```

### Opciones

| Opción | Por defecto | Descripción |
|---|---|---|
| `-j N`, `--hilos N` | 4 | Descargas simultáneas. Más de 6–8 y YouTube empieza a limitar. |
| `-n NAV`, `--navegador NAV` | `brave` | Navegador del que leer las cookies (`firefox`, `chrome`, `chromium`…). |

La carpeta de destino (`/home/jairo/Music`) se cambia en `download_path`, al principio de `converter.py`.

## Qué hace

1. **Comprobaciones**: que `ffmpeg` está instalado y que el navegador tiene una sesión de YouTube válida. Si las cookies no sirven, explica por qué y sigue sin ellas.
2. **Lee la playlist** con las cookies. Si YouTube la devuelve vacía, reintenta hasta 5 veces.
3. **Descarga** cada canción y la convierte a MP3:
   - Las que ya existen en la carpeta de destino se saltan, así que relanzarlo solo baja las nuevas.
   - Los ficheros intermedios (`.webm`, `.part`) van a una carpeta temporal: en el destino solo aparecen MP3 terminados, aunque se interrumpa con Ctrl+C.
   - Los fallos puntuales (p. ej. `403 Forbidden`) se reintentan hasta 3 veces.
4. **Resumen**: cuántas se han descargado, cuántas ya existían y cuáles han fallado y por qué.

El detalle completo de cada ejecución queda en `converter.log`.

## Problemas habituales

| Mensaje | Causa y solución |
|---|---|
| `Cookies: no hay sesión de YouTube iniciada en …` | Inicia sesión en YouTube en ese navegador, o usa `-n` con el navegador donde la tengas. |
| `Cookies: … cifradas y no se pudieron descifrar` | El llavero del sistema está bloqueado. Ejecútalo desde tu sesión de escritorio, no por SSH. |
| `No se pudo obtener la lista de vídeos de la playlist` | YouTube devolvió la playlist vacía 5 veces. Revisa las cookies y comprueba que la playlist sea pública o tuya. |
| `Sign in to confirm your age` | Vídeo con restricción de edad: no se puede descargar sin sesión. |
| `Video unavailable` / `Private video` | El vídeo se ha borrado o es privado. |
| Empiezan a fallar muchas descargas | YouTube cambia a menudo; actualiza yt-dlp: `.venv/bin/pip install -U yt-dlp` |

Las descargas se hacen **sin** cookies a propósito: con sesión iniciada, YouTube exige resolver un reto JavaScript que necesita [deno](https://deno.land) y, sin él, solo ofrece imágenes y no audio.
