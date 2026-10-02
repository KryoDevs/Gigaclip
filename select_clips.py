"""
Selector inteligente de momentos virales con LLM multi-proveedor.
Soporta OpenAI, DeepSeek y Ollama (local).
Incorpora analisis de texto, transcripcion con timestamps y senales
de energia acustica para priorizar momentos con ganchos solidos y alta retencion.
"""
import json
import math
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
        peak_str = " 🔥" if s.get("has_energy_peak") else ""
        lines.append(f"[{s['start']:.1f}-{s['end']:.1f} | Energia: {energy:.1f}/10{peak_str}] {s['text']}")
    return "\n".join(lines)


def _get_llm_config() -> dict:
    """Lee la configuracion del proveedor de LLM desde social_config.json."""
    from social_publisher import get_social_config
    cfg = get_social_config()
    return {
        "provider": cfg.get("llm_provider", "ollama"),
        "api_key": cfg.get("llm_api_key", ""),
        "model": cfg.get("llm_model", "gpt-4o-mini"),
    }

def test_llm_connection():
    config = _get_llm_config()
    provider = config.get("provider", "ollama")
    api_key = config.get("api_key", "")
    model = config.get("model", "gpt-4o-mini" if provider == "openai" else "deepseek-chat")
    
    try:
        if provider == "openai":
            import requests
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            data = {"model": model, "messages": [{"role": "user", "content": "Say OK"}], "max_tokens": 5}
            r = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=data, timeout=10)
            if r.status_code == 200:
                return {"success": True, "provider": "OpenAI", "model": model, "message": "Conexión exitosa"}
            else:
                return {"success": False, "provider": "OpenAI", "error": r.text}
                
        elif provider == "deepseek":
            import requests
            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            data = {"model": model, "messages": [{"role": "user", "content": "Say OK"}], "max_tokens": 5}
            r = requests.post("https://api.deepseek.com/v1/chat/completions", headers=headers, json=data, timeout=10)
            if r.status_code == 200:
                return {"success": True, "provider": "DeepSeek", "model": model, "message": "Conexión exitosa"}
            else:
                return {"success": False, "provider": "DeepSeek", "error": r.text}
                
        elif provider == "ollama":
            import requests
            r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
            if r.status_code == 200:
                return {"success": True, "provider": "Ollama", "model": OLLAMA_MODEL, "message": "Servidor activo"}
            else:
                return {"success": False, "provider": "Ollama", "error": "Servidor inactivo"}
    except Exception as e:
        return {"success": False, "provider": provider.capitalize(), "error": str(e)}


def _call_cloud_llm(prompt: str, provider: str, api_key: str, model: str) -> str:
    """Llama a OpenAI o DeepSeek via la libreria oficial de OpenAI."""
    from openai import OpenAI

    if provider == "deepseek":
        base_url = "https://api.deepseek.com/v1"
    else:
        base_url = None

    client = OpenAI(api_key=api_key, base_url=base_url)

    kwargs = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.4,
        "max_tokens": 4000,
    }
    # response_format solo para OpenAI (DeepSeek no siempre lo soporta)
    if provider == "openai":
        kwargs["response_format"] = {"type": "json_object"}

    resp = client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content


def _call_ollama(prompt: str) -> str:
    """Llama al servidor Ollama local."""
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
    return response.json()["response"]


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

    clips = []
    llm_cfg = _get_llm_config()
    provider = llm_cfg["provider"]

    try:
        if provider in ("openai", "deepseek") and llm_cfg["api_key"]:
            print(f"[LLM] Usando {provider.upper()} ({llm_cfg['model']})")
            raw = _call_cloud_llm(prompt, provider, llm_cfg["api_key"], llm_cfg["model"])
        else:
            print(f"[LLM] Usando Ollama local ({OLLAMA_MODEL})")
            raw = _call_ollama(prompt)

        data = _parse_llm_json(raw)
        clips = data.get("clips", [])
    except Exception as e:
        print(f"[LLM] Error en {provider}: {e}")
        clips = _fallback_heuristic_clips(segments, num_clips, min_s, max_s)

    # Validación estricta: el modelo no debe pedir segmentos fuera del video
    # ni ignorar el rango de duración elegido por el usuario.
    valid_clips = []
    if not isinstance(clips, list):
        clips = []
    lower_bound = float(segments[0]["start"]) if segments else 0.0
    upper_bound = float(segments[-1]["end"]) if segments else 0.0
    for clip in clips:
        if not isinstance(clip, dict):
            continue
        try:
            start = float(clip["start"])
            end = float(clip["end"])
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if (not math.isfinite(start) or not math.isfinite(end) or
                start < lower_bound or end > upper_bound or
                end <= start or end - start < min_s or end - start > max_s):
            continue
        try:
            score = max(0, min(100, int(clip.get("score", 85))))
            hook_strength = max(0, min(100, int(clip.get("hook_strength", 88))))
            retention_score = max(0, min(100, int(clip.get("retention_score", 85))))
        except (TypeError, ValueError, OverflowError):
            continue
        valid_clips.append({
            "start": round(start, 2),
            "end": round(end, 2),
            "title": str(clip.get("title", f"Clip {len(valid_clips) + 1}"))[:120],
            "hook": str(clip.get("hook", ""))[:500],
            "score": score,
            "hook_strength": hook_strength,
            "retention_score": retention_score,
            "reason": str(clip.get("reason", "Momento con alto valor."))[:500],
        })

    valid_clips.sort(key=lambda item: item["score"], reverse=True)
    return valid_clips[:num_clips]



def _fallback_heuristic_clips(segments: list[dict], num_clips: int, min_s: int, max_s: int) -> list[dict]:
    """Genera clips por duracion si el LLM no estuviera disponible."""
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
