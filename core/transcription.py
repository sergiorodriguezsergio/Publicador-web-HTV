import os
import wave
import json
from pydub import AudioSegment
from vosk import Model, KaldiRecognizer, SetLogLevel
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Asegurar que FFMPEG de la otra carpeta está en el path si no se copia localmente
FFMPEG_PATH = os.path.join(BASE_DIR, "Herramientas_Htv", "ffmpeg-master-latest-win64-gpl", "bin")
os.environ["PATH"] += os.pathsep + FFMPEG_PATH

class TranscriptionService:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.client = OpenAI(api_key=self.api_key) if self.api_key else None
        
    def transcribe_with_whisper(self, input_file):
        with open(input_file, "rb") as audio_file:
            transcript = self.client.audio.transcriptions.create(
                model="whisper-1", 
                file=audio_file,
                language="es"
            )
        return transcript.text

    def transcribe_with_vosk(self, input_file):
        SetLogLevel(-1)
        audio = AudioSegment.from_file(input_file)
        audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)
        temp_wav = "temp_vosk_audio.wav"
        audio.export(temp_wav, format="wav")
        
        # Modelo Vosk desde la ruta original (Herramientas_Htv) para no duplicarlo por ahora
        model_path = os.path.join(BASE_DIR, "Herramientas_Htv", "model")
        
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
            return self.transcribe_with_whisper(file_path), "Whisper"
        else:
            return self.transcribe_with_vosk(file_path), "Vosk"
