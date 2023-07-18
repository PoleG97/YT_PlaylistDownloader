import os
from pytube import Playlist
import subprocess

# Definicion de la ruta de descarga
download_path = "/home/jairo/Music"

# Función para descargar la playlist en MP3
def download_playlist():
    # Obtener la URL de la playlist del usuario
    playlist_url = input("Ingrese la URL de la playlist de YouTube: ")

    playlist = Playlist(playlist_url)

    if not os.path.exists(download_path):
        os.makedirs(download_path)

    for video in playlist.videos:
        try:
            stream = video.streams.filter(only_audio=True).first()
            output_file = os.path.join(download_path, f'{video.title}.mp3')
            print(f"Downloading: {video.title}")
            stream.download(output_path=download_path)
            base, ext = os.path.splitext(output_file)
            new_file = base + '.mp3'
            os.rename(output_file, new_file)
            print(f"Converted to MP3: {new_file}")
        except Exception as e:
            print(f"Error downloading {video.watch_url}: {str(e)}")

# Función para convertir todos los .mp4 a .mp3
def convert_mp4_to_mp3(input_path):
    for file_name in os.listdir(input_path):
        if file_name.endswith(".mp4"):
            video_path = os.path.join(input_path, file_name)
            audio_path = os.path.join(input_path, os.path.splitext(file_name)[0] + ".mp3")
            print(f"Converting: {file_name}")

            try:
                command = ['ffmpeg', '-i', video_path, '-vn', '-acodec', 'libmp3lame', audio_path]
                subprocess.run(command, check=True)
                print(f"Converted to MP3: {audio_path}")
                os.remove(video_path)  # Eliminamos el archivo .mp4 después de la conversión
            except Exception as e:
                print(f"Error converting {file_name}: {str(e)}")

# Ejecutar la función para descargar la playlist en MP3
download_playlist()

# Ejecutar la función para convertir los .mp4 a .mp3
convert_mp4_to_mp3(download_path)
