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

        response = self.client.chat.completions.create(
            model=modelo,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
        )

        noticia_json = json.loads(response.choices[0].message.content)
        noticia_json["archivo_original"] = original_filename
        return noticia_json
