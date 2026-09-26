"""
Generador de metadatos virales para redes sociales (TikTok, YouTube Shorts, Instagram Reels).
Crea titulos SEO, descripciones persuasivas con hashtags y primer comentario fijado.
"""
import json
import re
import requests
from config import OLLAMA_URL, OLLAMA_MODEL


METADATA_PROMPT_TEMPLATE = """Eres un estratega de contenido viral para TikTok, Shorts y Reels.
A partir del siguiente extracto de un clip, genera los metadatos optimizados para maximizar visualizaciones, retencion y comentarios.

Titulo del clip: {title}
Texto del clip: "{transcript_snippet}"

Responde UNICAMENTE con un objeto JSON valido con esta estructura exacta:
{{
  "viral_title": "Titulo intrigante o con gancho (max 60 caracteres)",
  "tiktok_caption": "Texto corto para el copy con 4-6 hashtags virales (#fyp #viral ...)",
  "youtube_shorts_title": "Titulo con gancho + 3 hashtags (#Shorts #viral ...)",
  "instagram_reels_caption": "Copy mas estructurado con llamada a la accion (CTA) y hashtags",
  "pinned_comment": "Pregunta polemica o intrigante para fijar en el primer comentario y generar debate",
  "best_post_time": "18:00 - 21:00 (hora recomendada)",
  "hook_rating": "95/100 (Gancho directo)"
}}
"""


def generate_social_metadata(title: str, transcript_snippet: str) -> dict:
    """Invoca a Ollama para generar copys y hashtags para redes sociales."""
    prompt = METADATA_PROMPT_TEMPLATE.format(
        title=title,
        transcript_snippet=transcript_snippet[:600]
    )

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.5},
            },
            timeout=60,
        )
        response.raise_for_status()
        raw = response.json()["response"]
        
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                return json.loads(match.group(0))
    except Exception as e:
        pass

    # Fallback predeterminado si falla el LLM
    clean_title = re.sub(r"[^\w\s]", "", title)
    return {
        "viral_title": f"{title} 🔥",
        "tiktok_caption": f"{title} ¿Qué opinas de esto? 👇 #fyp #viral #parati #podcast #clips",
        "youtube_shorts_title": f"{title} #Shorts #viral #podcast",
        "instagram_reels_caption": f"💡 {title}\n\nGuarda este reel si te aportó valor y compártelo con alguien que necesite escucharlo. 🚀\n\n#reels #viral #crecimiento #desarrollo #inspiracion",
        "pinned_comment": "¿Estás de acuerdo con lo que se dice en este clip? Déjamelo saber en los comentarios 👇",
        "best_post_time": "19:00 - 21:00",
        "hook_rating": "88/100"
    }
