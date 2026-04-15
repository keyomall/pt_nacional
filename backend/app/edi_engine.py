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
    def procesar_imagen_perfil(image_bytes: bytes) -> str | None:
        """Usa IA (rembg) para quitar fondo, recorta y comprime."""
        try:
            # 1. Quitar fondo con IA
            output_bytes = remove(image_bytes)

            # 2. Abrir con Pillow para optimizar
            img = Image.open(BytesIO(output_bytes)).convert("RGBA")

            # 3. Calcular Bounding Box (recortar espacio vacío extra)
            bbox = img.getbbox()
            if bbox:
                img = img.crop(bbox)

            # 4. Redimensionar si es muy grande (Max 800px)
            img.thumbnail((800, 800), Image.Resampling.LANCZOS)

            # 5. Guardar como WEBP (soporta transparencia y alta compresión)
            filename = f"profile_{uuid.uuid4().hex}.webp"
            filepath = os.path.join(MEDIA_DIR, filename)
            img.save(filepath, "WEBP", quality=85)

            return f"/media/{filename}"
        except Exception as e:
            print(f"[!] Error en IA de imagen: {e}")
            return None

    @staticmethod
    def escanear_wikipedia(url: str) -> dict:
        """Minería de datos básica desde una URL."""
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            response = requests.get(url, headers=headers, timeout=5)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

            # Extraer primer párrafo (biografía)
            paragraphs = soup.find_all("p")
            biografia = ""
            for p in paragraphs:
                if len(p.text) > 50:
                    biografia = p.text.strip()
                    break

            # Extraer imagen principal de la infobox
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
