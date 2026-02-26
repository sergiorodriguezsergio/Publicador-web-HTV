import os
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth
from datetime import datetime
from urllib.parse import quote
from core.logger import get_logger

load_dotenv()

log = get_logger(__name__)

_RETRY_STATUS = {429, 500, 502, 503, 504}
_MAX_RETRIES  = 3
_BASE_DELAY   = 2

class PublisherService:
    def __init__(self):
        self.site_url = os.getenv("WP_SITE_URL", "https://huelvatv.com/wp-json/wp/v2")
        self.user = os.getenv("WP_USER")
        self.password = os.getenv("WP_PASSWORD")
        self.auth = HTTPBasicAuth(self.user, str(self.password).replace(" ", "")) if self.password else None

        self.meses = {
            "01": "ENERO", "02": "FEBRERO", "03": "MARZO", "04": "ABRIL",
            "05": "MAYO", "06": "JUNIO", "07": "JULIO", "08": "AGOSTO",
            "09": "SEPTIEMBRE", "10": "OCTUBRE", "11": "NOVIEMBRE", "12": "DICIEMBRE"
        }

    def _fetch_tag_id(self, tag: str):
        """Resuelve el ID de una etiqueta. Devuelve None si no existe."""
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                res = requests.get(
                    f"{self.site_url}/tags",
                    params={"search": tag, "per_page": 1},
                    auth=self.auth,
                    timeout=10,
                )
                if res.status_code == 200:
                    data = res.json()
                    return data[0]["id"] if data else None
                if res.status_code in _RETRY_STATUS and attempt < _MAX_RETRIES:
                    time.sleep(_BASE_DELAY * (2 ** (attempt - 1)))
                    continue
                log.warning("[Publisher] tag '%s' HTTP %s", tag, res.status_code)
                return None
            except Exception as exc:
                log.warning("[Publisher] tag '%s' error: %s", tag, exc)
                if attempt < _MAX_RETRIES:
                    time.sleep(_BASE_DELAY * (2 ** (attempt - 1)))
        return None

    def _get_tag_ids(self, tags_list):
        if not tags_list or not self.auth:
            return []

        ids = []
        with ThreadPoolExecutor(max_workers=min(len(tags_list), 5)) as pool:
            futures = {pool.submit(self._fetch_tag_id, tag): tag for tag in tags_list}
            for fut in as_completed(futures):
                tag_id = fut.result()
                if tag_id is not None:
                    ids.append(tag_id)
        log.info("[Publisher] %d/%d etiquetas resueltas", len(ids), len(tags_list))
        return ids

    def _generate_video_embed(self, original_filename):
        now = datetime.now()
        year = now.strftime("%Y")
        month_str = self.meses[now.strftime("%m")]
        date_str = now.strftime("%d-%m-%y")
        
        nombre_base = os.path.basename(original_filename)
        nombre_sin_ext, _ = os.path.splitext(nombre_base)
        video_filename = f"{nombre_sin_ext}.mp4"
        
        video_url = f"https://videos.huelvatv.com/{year}/NOTICIAS/{month_str}/{date_str}/{video_filename}"
        return f'<figure class="wp-block-video"><video src="{video_url}" autoplay="autoplay" muted="" controls="controls" width="100%" height="auto"></video></figure>'

    def publish(self, news_data):
        if not self.auth:
            raise Exception("Credenciales de WordPress no configuradas.")

        titulo = news_data.get("titulo", "")
        entradilla = news_data.get("entradilla", "")
        contenido_crudo = news_data.get("contenido", "")
        etiquetas = news_data.get("etiquetas", [])
        archivo_original = news_data.get("archivo_original", "")

        tags_ids = self._get_tag_ids(etiquetas)
        bloque_video = self._generate_video_embed(archivo_original)
        separador_html = '<hr class="wp-block-separator has-alpha-channel-opacity"/>'
        
        contenido_final = f"{bloque_video}\n\n{separador_html}\n\n{contenido_crudo}"

        post_data = {
            "title": titulo,
            "content": contenido_final,
            "excerpt": entradilla,
            "status": "pending", 
            "tags": tags_ids
        }

        last_exc = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                log.info("[Publisher] Publicando post - intento %d/%d", attempt, _MAX_RETRIES)
                response = requests.post(
                    f"{self.site_url}/posts",
                    auth=self.auth,
                    json=post_data,
                    allow_redirects=False,
                    timeout=30,
                )
                if response.status_code == 201:
                    link = response.json().get("link")
                    log.info("[Publisher] Post creado: %s", link)
                    return link
                if response.status_code in _RETRY_STATUS and attempt < _MAX_RETRIES:
                    delay = _BASE_DELAY * (2 ** (attempt - 1))
                    log.warning("[Publisher] HTTP %s, reintentando en %ss...", response.status_code, delay)
                    time.sleep(delay)
                    continue
                raise Exception(f"HTTP {response.status_code}: {response.text}")
            except requests.RequestException as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    delay = _BASE_DELAY * (2 ** (attempt - 1))
                    log.warning("[Publisher] Error de red, reintentando en %ss...", delay)
                    time.sleep(delay)
                else:
                    raise
        raise last_exc
