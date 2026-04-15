import os
import uuid
from io import BytesIO

import requests
from bs4 import BeautifulSoup
from PIL import Image
from rembg import remove

# Directorio para guardar evidencias multimedia
MEDIA_DIR = os.path.join(os.getcwd(), "media_edi")
os.makedirs(MEDIA_DIR, exist_ok=True)


class EDIEngine:
    @staticmethod
    def procesar_imagen_perfil(image_bytes: bytes) -> str:
        try:
            output_bytes = remove(image_bytes)
            img = Image.open(BytesIO(output_bytes)).convert("RGBA")
            bbox = img.getbbox()
            if bbox:
                img = img.crop(bbox)
            img.thumbnail((800, 800), Image.Resampling.LANCZOS)
            filename = f"profile_{uuid.uuid4().hex}.webp"
            filepath = os.path.join(MEDIA_DIR, filename)
            img.save(filepath, "WEBP", quality=85)
            return f"/media/{filename}"
        except Exception as e:
            print(f"[!] Error en IA de imagen: {e}")
            return None

    @staticmethod
    def escanear_wikipedia(url: str) -> dict:
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            response = requests.get(url, headers=headers, timeout=5)
            soup = BeautifulSoup(response.text, "html.parser")
            paragraphs = soup.find_all("p")
            biografia = next((p.text.strip() for p in paragraphs if len(p.text) > 50), "")
            foto_url = None
            infobox = soup.find("table", {"class": "infobox"})
            if infobox:
                img_tag = infobox.find("img")
                if img_tag and img_tag.get("src"):
                    src = img_tag["src"]
                    foto_url = f"https:{src}" if src.startswith("//") else src

            return {"biografia": biografia, "foto_url": foto_url, "fuente": url}
        except Exception as e:
            print(f"[!] Error en Scraping: {e}")
            return {}
