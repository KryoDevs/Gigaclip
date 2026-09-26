"""
Le pide a un LLM local (via Ollama) que revise la transcripcion completa
y elija los mejores momentos para convertir en clips virales.

Requiere tener Ollama corriendo: https://ollama.com
    ollama pull llama3.2:3b
(el servicio suele quedar corriendo solo en localhost:11434 tras instalarlo)
"""
import json
import re

import requests

from config import OLLAMA_URL, OLLAMA_MODEL, NUM_CLIPS, CLIP_MIN_SECONDS, CLIP_MAX_SECONDS


PROMPT_TEMPLATE = """Eres un editor experto en encontrar los momentos mas virales de podcasts y videos largos para convertirlos en Shorts/Reels/TikToks.

Te paso la transcripcion completa con timestamps (en segundos). Elige los {num_clips} MEJORES momentos para clips cortos, aplicando estos criterios:
- Tienen un gancho claro en los primeros 3 segundos (pregunta intrigante, dato sorprendente, afirmacion polemica)
- Son autoconclusivos: se entienden sin haber visto el resto del video
- Duran entre {min_s} y {max_s} segundos
- Tienen carga emocional, humor, un consejo accionable, o un momento de tension/revelacion

Responde SOLO con un JSON valido (sin texto adicional, sin markdown), con este formato exacto:
{{
  "clips": [
    {{
      "start": 123.4,
      "end": 178.9,
      "title": "Titulo corto y llamativo para el clip",
      "hook": "La frase textual que funciona como gancho inicial",
      "score": 8.5
    }}
  ]
}}

Transcripcion (formato [inicio-fin] texto):
{transcript}
"""


def _format_transcript(segments: list[dict]) -> str:
    lines = [f"[{s['start']:.1f}-{s['end']:.1f}] {s['text']}" for s in segments]
    return "\n".join(lines)


def select_clips(segments: list[dict], num_clips: int = NUM_CLIPS) -> list[dict]:
    transcript_text = _format_transcript(segments)

    prompt = PROMPT_TEMPLATE.format(
        num_clips=num_clips,
        min_s=CLIP_MIN_SECONDS,
        max_s=CLIP_MAX_SECONDS,
        transcript=transcript_text,
    )

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "format": "json",  # Ollama fuerza salida JSON valida
            "options": {"temperature": 0.4},
        },
        timeout=600,
    )
    response.raise_for_status()
    raw = response.json()["response"]

    data = _parse_llm_json(raw)
    clips = data.get("clips", [])

    # Filtro de seguridad por si el modelo se sale de formato/rango
    clips = [
        c for c in clips
        if isinstance(c.get("start"), (int, float))
        and isinstance(c.get("end"), (int, float))
        and c["end"] > c["start"]
    ]
    clips.sort(key=lambda c: c.get("score", 0), reverse=True)
    return clips[:num_clips]


def _parse_llm_json(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: extrae el primer bloque {...} por si el modelo agrego texto extra
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise ValueError(f"El LLM no devolvio JSON valido:\n{raw[:500]}")


if __name__ == "__main__":
    import sys
    from transcribe import transcribe

    data = transcribe(sys.argv[1])
    clips = select_clips(data["segments"])
    print(json.dumps(clips, ensure_ascii=False, indent=2))
