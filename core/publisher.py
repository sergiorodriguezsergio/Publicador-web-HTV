import os
import requests
from dotenv import load_dotenv
from requests.auth import HTTPBasicAuth
from datetime import datetime
from urllib.parse import quote

load_dotenv()

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

    def _get_tag_ids(self, tags_list):
        if not tags_list or not self.auth:
            return []
            
        ids = []
        for tag in tags_list:
            try:
                res = requests.get(f"{self.site_url}/tags?search={tag}", auth=self.auth)
                if res.status_code == 200:
                    data = res.json()
                    if data: ids.append(data[0]['id'])
            except Exception:
                pass
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

        response = requests.post(f"{self.site_url}/posts", auth=self.auth, json=post_data, allow_redirects=False)
        
        if response.status_code == 201:
            return response.json().get('link')
        else:
            raise Exception(f"HTTP {response.status_code}: {response.text}")
