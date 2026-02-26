import os
import json
import time
from openai import OpenAI, APIStatusError, APIConnectionError
from dotenv import load_dotenv
from core.logger import get_logger

load_dotenv()

log = get_logger(__name__)

CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")
PROMPTS_PATH = os.path.join(CONFIG_DIR, "prompts.json")

_RETRY_CODES = {429, 500, 502, 503, 504}
_MAX_RETRIES = 3
_BASE_DELAY  = 2  # segundos


def _load_prompts():
    with open(PROMPTS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


class WriterService:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.client = OpenAI(api_key=self.api_key) if self.api_key else None

    def write_news(self, transcription: str, original_filename: str) -> dict:
        if not self.client:
            raise Exception("OpenAI API Key no configurada.")

        cfg = _load_prompts()["redaccion"]
        modelo = cfg.get("modelo", "gpt-4o")
        system_prompt = cfg["system_prompt"]
        user_prompt = cfg["user_prompt_template"].format(
            transcription=transcription,
            original_filename=original_filename,
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        last_exc = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                log.info("[Writer] Intento %d/%d - modelo %s", attempt, _MAX_RETRIES, modelo)
                response = self.client.chat.completions.create(
                    model=modelo,
                    messages=messages,
                    response_format={"type": "json_object"},
                )
                noticia_json = json.loads(response.choices[0].message.content)
                noticia_json["archivo_original"] = original_filename
                log.info("[Writer] Noticia generada correctamente.")
                return noticia_json
            except APIStatusError as e:
                last_exc = e
                if e.status_code in _RETRY_CODES and attempt < _MAX_RETRIES:
                    delay = _BASE_DELAY * (2 ** (attempt - 1))
                    log.warning("[Writer] HTTP %s, reintentando en %ss...", e.status_code, delay)
                    time.sleep(delay)
                else:
                    raise
            except APIConnectionError as e:
                last_exc = e
                if attempt < _MAX_RETRIES:
                    delay = _BASE_DELAY * (2 ** (attempt - 1))
                    log.warning("[Writer] Error de conexión, reintentando en %ss...", delay)
                    time.sleep(delay)
                else:
                    raise
        raise last_exc
