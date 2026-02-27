import os
import wave
import json
import shutil
import subprocess
import tempfile
from dotenv import load_dotenv
from openai import OpenAI
from core.logger import get_logger

# Extensiones de vídeo que requieren extracción de audio antes de enviar a Whisper
_VIDEO_EXTENSIONS = {".mp4", ".mpeg", ".mpg", ".webm", ".mov", ".avi"}
# Umbral de tamaño (en MB) por debajo del cual se envía el audio directamente
_WHISPER_MAX_MB = 24

load_dotenv()

log = get_logger(__name__)

# Directorio raíz del proyecto (donde está app.py)
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Directorio hermano con herramientas externas (puede no existir)
_TOOLS_DIR = os.path.join(os.path.dirname(PROJECT_DIR), "Herramientas_Htv")

def _ensure_ffmpeg_in_path():
    """Garantiza que ffmpeg esté en PATH antes de inicializar pydub."""
    if shutil.which("ffmpeg"):
        return
    _candidate = os.path.join(_TOOLS_DIR, "ffmpeg-master-latest-win64-gpl", "bin")
    if os.path.isdir(_candidate):
        # Prepend para que pydub encuentre esta ruta al importar.
        os.environ["PATH"] = _candidate + os.pathsep + os.environ.get("PATH", "")
        log.info("ffmpeg añadido desde ruta externa: %s", _candidate)
    else:
        log.warning("ffmpeg no encontrado en el PATH ni en la ruta externa. "
                    "Las transcripciones de audio pueden fallar.")


_ensure_ffmpeg_in_path()

from pydub import AudioSegment
from vosk import Model, KaldiRecognizer, SetLogLevel

class TranscriptionService:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.client = OpenAI(api_key=self.api_key) if self.api_key else None

    def _prepare_for_whisper(self, input_file: str) -> tuple[str, bool]:
        """
        Devuelve (ruta_a_enviar, es_temporal).
        Si el archivo es vídeo o pesa más de _WHISPER_MAX_MB MB,
        extrae el audio a un MP3 comprimido con ffmpeg.
        """
        ext = os.path.splitext(input_file)[1].lower()
        size_mb = os.path.getsize(input_file) / (1024 * 1024)

        if ext not in _VIDEO_EXTENSIONS and size_mb <= _WHISPER_MAX_MB:
            return input_file, False  # Se envía directamente

        log.info("Extrayendo audio para Whisper (%.1f MB, ext=%s): %s", size_mb, ext, input_file)
        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        tmp.close()
        ffmpeg_bin = shutil.which("ffmpeg") or "ffmpeg"
        try:
            subprocess.run(
                [
                    ffmpeg_bin,
                    "-i", input_file,
                    "-vn",           # eliminar pista de vídeo
                    "-ar", "16000",  # 16 kHz es suficiente para voz
                    "-ac", "1",      # mono
                    "-b:a", "64k",   # 64 kbps → ~28 MB/hora, muy por debajo del límite
                    "-y",
                    tmp.name,
                ],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as e:
            os.unlink(tmp.name)
            raise RuntimeError(
                f"No se pudo extraer el audio de '{input_file}': {e.stderr.decode(errors='replace')}"
            ) from e

        out_mb = os.path.getsize(tmp.name) / (1024 * 1024)
        log.info("Audio extraído: %s (%.1f MB)", tmp.name, out_mb)
        return tmp.name, True

    def transcribe_with_whisper(self, input_file):
        prepared, is_temp = self._prepare_for_whisper(input_file)
        try:
            with open(prepared, "rb") as audio_file:
                transcript = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language="es",
                )
            return transcript.text
        finally:
            if is_temp and os.path.exists(prepared):
                os.unlink(prepared)

    def transcribe_with_vosk(self, input_file):
        SetLogLevel(-1)
        audio = AudioSegment.from_file(input_file)
        audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)
        temp_wav = "temp_vosk_audio.wav"
        audio.export(temp_wav, format="wav")
        
        # Modelo Vosk: buscar primero dentro del proyecto, luego en ruta externa
        _local_model = os.path.join(PROJECT_DIR, "model")
        _extern_model = os.path.join(_TOOLS_DIR, "model")
        model_path = _local_model if os.path.exists(_local_model) else _extern_model
        
        if not os.path.exists(model_path):
            if os.path.exists(temp_wav): os.remove(temp_wav)
            raise Exception("Modelo local de Vosk no encontrado.")

        model = Model(model_path)
        wf = wave.open(temp_wav, "rb")
        rec = KaldiRecognizer(model, wf.getframerate())
        rec.SetWords(True)

        results = []
        while True:
            data = wf.readframes(4000)
            if len(data) == 0: break
            if rec.AcceptWaveform(data):
                part = json.loads(rec.Result())
                results.append(part.get("text", ""))
        
        final_res = json.loads(rec.FinalResult())
        results.append(final_res.get("text", ""))
        
        wf.close()
        if os.path.exists(temp_wav): os.remove(temp_wav)
            
        return " ".join(results).strip()

    def transcribe(self, file_path):
        if self.api_key and not self.api_key.startswith("tu_clave"):
            log.info("Transcribiendo con Whisper: %s", file_path)
            result = self.transcribe_with_whisper(file_path), "Whisper"
            log.info("Transcripción Whisper completada (%d chars)", len(result[0]))
            return result
        else:
            log.info("Transcribiendo con Vosk: %s", file_path)
            result = self.transcribe_with_vosk(file_path), "Vosk"
            log.info("Transcripción Vosk completada (%d chars)", len(result[0]))
            return result
