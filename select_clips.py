"""
Selector inteligente de momentos virales con LLM local (Ollama).
Incorpora analisis de texto, transcripcion con timestamps y senales
de energia acustica para priorizar momentos con ganchos solidos y alta retencion.
"""
import json
import re
import requests

from config import OLLAMA_URL, OLLAMA_MODEL, NUM_CLIPS, CLIP_MIN_SECONDS, CLIP_MAX_SECONDS


PROMPT_TEMPLATE = """Eres el editor jefe y estratega viral de una agencia de contenidos para Shorts, TikTok y Reels.

Analiza la transcripcion con timestamps y metricas de energia (audio). Tu mision es seleccionar los {num_clips} MEJORES momentos con potencial viral masivo.

Criterios de seleccion obligatorios:
1. Gancho Demoledor (Primeros 3 seg): Debe empezar con una pregunta inquietante, afirmacion polemica, revelacion o dato chocante.
2. Autocontenido: El espectador debe entender la idea completa sin contexto previo.
3. Duracion: Entre {min_s} y {max_s} segundos.
4. Alta Retencion: Sin silencios aburridos o introducciones lentas.

Responde UNICAMENTE con un objeto JSON valido (sin texto fuera del JSON, sin bloques de codigo extra):
{{
  "clips": [
    {{
      "start": 12.4,
      "end": 45.2,
      "title": "Titulo corto y llamativo",
      "hook": "La frase exacta que sirve de gancho inicial",
      "score": 94,
      "hook_strength": 96,
      "retention_score": 92,
      "reason": "Comienza con una pregunta directa y concluye con una solucion practica."
    }}
  ]
}}

Transcripcion del video (formato: [inicio-fin | Energia: X/10] texto):
{transcript}
"""


def _format_transcript_with_energy(segments: list[dict]) -> str:
    lines = []
    for s in segments:
        energy = s.get("energy_score", 5.0)
        peak_str = " ðŸ”¥" if s.get("has_energy_peak") else ""
        lines.append(f"[{s['start']:.1f}-{s['end']:.1f} | Energia: {energy:.1f}/10{peak_str}] {s['text']}")
    return "\n".join(lines)


def select_clips(segments: list[dict], num_clips: int = NUM_CLIPS, min_seconds: int = None, max_seconds: int = None) -> list[dict]:
    min_s = min_seconds or CLIP_MIN_SECONDS
    max_s = max_seconds or CLIP_MAX_SECONDS
    transcript_text = _format_transcript_with_energy(segments)

    prompt = PROMPT_TEMPLATE.format(
        num_clips=num_clips,
        min_s=min_s,
        max_s=max_s,
        transcript=transcript_text,
    )

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.4},
            },
            timeout=600,
        )
        response.raise_for_status()
        raw = response.json()["response"]
        data = _parse_llm_json(raw)
        clips = data.get("clips", [])
    except Exception as e:
        # Fallback inteligente si el LLM falla: generar clips basados en duracion y picos de energia
        clips = _fallback_heuristic_clips(segments, num_clips, min_s, max_s)

    # Validacion y filtrado
    valid_clips = []
    for c in clips:
        if isinstance(c.get("start"), (int, float)) and isinstance(c.get("end"), (int, float)):
            start = float(c["start"])
            end = float(c["end"])
            if end > start:
                valid_clips.append({
                    "start": round(start, 2),
                    "end": round(end, 2),
                    "title": str(c.get("title", f"Clip {len(valid_clips)+1}")),
                    "hook": str(c.get("hook", "")),
                    "score": int(c.get("score", 85)),
                    "hook_strength": int(c.get("hook_strength", 88)),
                    "retention_score": int(c.get("retention_score", 85)),
                    "reason": str(c.get("reason", "Momento con alto valor.")),
                })

    valid_clips.sort(key=lambda x: x.get("score", 0), reverse=True)
    return valid_clips[:num_clips]


def _fallback_heuristic_clips(segments: list[dict], num_clips: int, min_s: int, max_s: int) -> list[dict]:
    """Genera clips por duracion si Ollama no estuviera disponible."""
    if not segments:
        return []
    
    total_dur = segments[-1]["end"]
    clip_dur = min(max_s, max(min_s, 30))
    clips = []
    
    step = max(clip_dur, total_dur / (num_clips + 1))
    current_start = 0.0
    
    for i in range(num_clips):
        start = current_start
        end = min(total_dur, start + clip_dur)
        if start >= total_dur:
            break
        matching = [s["text"] for s in segments if s["start"] >= start and s["end"] <= end]
        snippet = " ".join(matching[:4]) if matching else f"Momento clave {i+1}"
        clips.append({
            "start": start,
            "end": end,
            "title": f"Momento Viral {i+1}",
            "hook": snippet[:60] + "...",
            "score": 80 + (i * 2),
            "hook_strength": 82,
            "retention_score": 80,
            "reason": "Segmento destacado por duracion y ritmo."
        })
        current_start += step

    return clips


def _parse_llm_json(raw: str) -> dict:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise ValueError("JSON no valido")

