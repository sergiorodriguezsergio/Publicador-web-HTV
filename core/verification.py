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


class VerificationService:
    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.client = OpenAI(api_key=self.api_key) if self.api_key else None

    def verify(self, news_data: dict) -> dict:
        if not self.client:
            raise Exception("OpenAI API Key no configurada.")

        cfg = _load_prompts()["verificacion"]
        modelo = cfg.get("modelo", "gpt-4o-search-preview")
        system_prompt = cfg["system_prompt"]

        titulo = news_data.get("titulo", "")
        entradilla = news_data.get("entradilla", "")
        contenido = news_data.get("contenido", "")
        etiquetas = news_data.get("etiquetas", [])

        user_prompt = cfg["user_prompt_template"].format(
            titulo=titulo,
            entradilla=entradilla,
            contenido=contenido,
            etiquetas=", ".join(etiquetas),
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        last_exc = None
        response = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                log.info("[Verification] Intento %d/%d - modelo %s", attempt, _MAX_RETRIES, modelo)
                response = self.client.chat.completions.create(
                    model=modelo,
                    messages=messages,
                )
                break
            except APIStatusError as e:
                last_exc = e
                if e.status_code in _RETRY_CODES and attempt < _MAX_RETRIES:
                    delay = _BASE_DELAY * (2 ** (attempt - 1))
                    log.warning("[Verification] HTTP %s, reintentando en %ss...", e.status_code, delay)
                    time.sleep(delay)
                else:
                    raise
            except APIConnectionError as e:
                last_exc = e
                if attempt < _MAX_RETRIES:
                    delay = _BASE_DELAY * (2 ** (attempt - 1))
                    log.warning("[Verification] Error de conexión, reintentando en %ss...", delay)
                    time.sleep(delay)
                else:
                    raise
        if response is None:
            raise last_exc

        raw_text = response.choices[0].message.content or ""

        annotations = []
        msg = response.choices[0].message
        if hasattr(msg, "annotations") and msg.annotations:
            for ann in msg.annotations:
                # SDK moderno: url_citation.url
                url_citation = getattr(ann, "url_citation", None)
                if url_citation is not None:
                    url = getattr(url_citation, "url", None)
                    if url:
                        annotations.append(url)
                else:
                    # Fallback para versiones antiguas del SDK
                    url = getattr(ann, "url", None)
                    if url:
                        annotations.append(url)

        start = raw_text.find("{")
        end = raw_text.rfind("}") + 1
        if start == -1 or end == 0:
            raise Exception("La IA no devolvió un formato JSON válido.")

        result = json.loads(raw_text[start:end])

        if annotations and not result.get("fuentes_consultadas"):
            result["fuentes_consultadas"] = annotations

        return result
