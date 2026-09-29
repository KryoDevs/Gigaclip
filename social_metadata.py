"""
Generador de metadatos virales para redes sociales (TikTok, YouTube Shorts, Instagram Reels).
Crea titulos SEO, descripciones persuasivas con hashtags y primer comentario fijado.
Soporta OpenAI, DeepSeek y Ollama (local).
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


def _get_llm_config() -> dict:
    """Lee la configuracion del proveedor de LLM desde social_config.json."""
    try:
        from social_publisher import get_social_config
        cfg = get_social_config()
        return {
            "provider": cfg.get("llm_provider", "ollama"),
            "api_key": cfg.get("llm_api_key", ""),
            "model": cfg.get("llm_model", "gpt-4o-mini"),
        }
    except Exception:
        return {"provider": "ollama", "api_key": "", "model": "gpt-4o-mini"}


def _call_llm(prompt: str) -> str:
    """Llama al LLM configurado (OpenAI/DeepSeek/Ollama)."""
    cfg = _get_llm_config()
    provider = cfg["provider"]

    if provider in ("openai", "deepseek") and cfg["api_key"]:
        from openai import OpenAI

        base_url = "https://api.deepseek.com/v1" if provider == "deepseek" else None
        client = OpenAI(api_key=cfg["api_key"], base_url=base_url)

        kwargs = {
            "model": cfg["model"],
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.5,
            "max_tokens": 2000,
        }
        if provider == "openai":
            kwargs["response_format"] = {"type": "json_object"}

        resp = client.chat.completions.create(**kwargs)
        return resp.choices[0].message.content
    else:
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
        return response.json()["response"]


def generate_social_metadata(title: str, transcript_snippet: str) -> dict:
    """Genera copys y hashtags virales usando el LLM configurado."""
    prompt = METADATA_PROMPT_TEMPLATE.format(
        title=title,
        transcript_snippet=transcript_snippet[:600]
    )

    try:
        raw = _call_llm(prompt)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                return json.loads(match.group(0))
    except Exception:
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
