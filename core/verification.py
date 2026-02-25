import os
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")
PROMPTS_PATH = os.path.join(CONFIG_DIR, "prompts.json")


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

        response = self.client.chat.completions.create(
            model=modelo,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )

        raw_text = response.choices[0].message.content or ""

        annotations = []
        msg = response.choices[0].message
        if hasattr(msg, "annotations") and msg.annotations:
            for ann in msg.annotations:
                if hasattr(ann, "url"):
                    annotations.append(ann.url)

        start = raw_text.find("{")
        end = raw_text.rfind("}") + 1
        if start == -1 or end == 0:
            raise Exception("La IA no devolvió un formato JSON válido.")

        result = json.loads(raw_text[start:end])

        if annotations and not result.get("fuentes_consultadas"):
            result["fuentes_consultadas"] = annotations

        return result
