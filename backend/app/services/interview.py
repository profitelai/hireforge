"""Interview practice service: question generation, answer evaluation, TTS, STT."""

import io
import json
import logging

from app.services.llm import OPERATION_FIT_ANALYSIS, call_llm, clean_llm_json

logger = logging.getLogger(__name__)

OPERATION_INTERVIEW = "interview"

# ── System prompts ────────────────────────────────────────────────────────────

_QUESTIONS_SYSTEM = """\
You are a senior hiring manager and interview coach with 20+ years of experience.
Your task is to generate realistic interview questions tailored to the candidate's background and the target role.

For each question, provide:
- A behavioural or competency question drawn directly from the job description requirements
- A model answer using the STAR method, drawing on the candidate's REAL experience from their profile
- 3-4 key talking points the answer should hit

LANGUAGE RULE:
- If language is "FR": write all questions, model answers, and key points in French
- If language is "EN": write in English

OUTPUT FORMAT — return ONLY this JSON, no markdown, no explanation:
{
  "questions": [
    {
      "id": 1,
      "question": "...",
      "type": "behavioural|technical|situational",
      "model_answer": "...",
      "key_points": ["...", "...", "..."]
    }
  ]
}"""

_ANSWER_LENGTH_INSTRUCTIONS = {
    "short":    "ANSWER LENGTH: Short. Each model_answer must be 2-3 sentences (35-55 words). Capture only the single strongest example. No filler.",
    "medium":   "ANSWER LENGTH: Medium. Each model_answer should be 4-6 sentences (100-130 words) using the STAR method.",
    "detailed": "ANSWER LENGTH: Detailed. Each model_answer should be 8-10 sentences (200-240 words) with full STAR, specific metrics, and context.",
}

_EVALUATE_SYSTEM = """\
You are a strict but fair interview coach. Evaluate the candidate's answer honestly.

LANGUAGE RULE:
- If language is "FR": all feedback must be in French, and evaluate French grammar/vocabulary
- If language is "EN": all feedback in English

Score from 0–100:
- 90-100: Exceptional — complete STAR, specific metrics, compelling delivery
- 70-89:  Good — covers STAR, could be more specific or impactful
- 50-69:  Adequate — partial STAR, missing key elements
- 30-49:  Weak — vague, generic, or off-topic
- 0-29:   Poor — did not address the question

OUTPUT FORMAT — return ONLY this JSON:
{
  "score": 72,
  "feedback": "Overall assessment in 2-3 sentences.",
  "strengths": ["point 1", "point 2"],
  "areas_to_improve": ["point 1", "point 2"],
  "grammar_errors": ["error 1 or empty list"],
  "improved_answer": "Rewritten version of their answer (100-150 words), fixing gaps and grammar."
}"""


# ── Question generation ───────────────────────────────────────────────────────

def generate_questions(
    profile_text: str,
    job_description: str,
    language: str,
    provider: str,
    api_key: str,
    n: int = 5,
    profile_id: int | None = None,
    answer_length: str = "medium",
) -> dict:
    lang = language.upper() if language else "EN"
    length_instruction = _ANSWER_LENGTH_INSTRUCTIONS.get(answer_length, _ANSWER_LENGTH_INSTRUCTIONS["medium"])
    prompt = (
        f"CANDIDATE PROFILE:\n{profile_text}\n\n"
        f"JOB DESCRIPTION:\n{job_description}\n\n"
        f"LANGUAGE: {lang}\n"
        f"{length_instruction}\n"
        f"Generate exactly {n} interview questions."
    )
    raw = call_llm(
        prompt,
        system=_QUESTIONS_SYSTEM,
        provider=provider,
        api_key=api_key,
        timeout=270,
        operation=OPERATION_INTERVIEW,
        profile_id=profile_id,
    )
    data = json.loads(clean_llm_json(raw))
    return data


# ── Answer evaluation ─────────────────────────────────────────────────────────

def evaluate_answer(
    question: str,
    model_answer: str,
    user_answer: str,
    language: str,
    provider: str,
    api_key: str,
    profile_id: int | None = None,
) -> dict:
    lang = language.upper() if language else "EN"
    prompt = (
        f"LANGUAGE: {lang}\n\n"
        f"QUESTION:\n{question}\n\n"
        f"MODEL ANSWER:\n{model_answer}\n\n"
        f"CANDIDATE'S ANSWER:\n{user_answer}\n\n"
        "Evaluate the candidate's answer."
    )
    raw = call_llm(
        prompt,
        system=_EVALUATE_SYSTEM,
        provider=provider,
        api_key=api_key,
        timeout=120,
        operation=OPERATION_INTERVIEW,
        profile_id=profile_id,
    )
    try:
        return json.loads(clean_llm_json(raw))
    except json.JSONDecodeError:
        # Last-resort: pull individual scalar fields via regex so we never lose the score
        import re as _re
        def _grab(pattern: str, default):
            m = _re.search(pattern, raw, _re.DOTALL | _re.IGNORECASE)
            return m.group(1).strip() if m else default

        def _grab_list(key: str) -> list:
            m = _re.search(rf'"{key}"\s*:\s*\[([^\]]*)\]', raw, _re.DOTALL)
            if not m:
                return []
            items = _re.findall(r'"([^"]*)"', m.group(1))
            return items

        score_m = _re.search(r'"score"\s*:\s*(\d+)', raw)
        return {
            "score": int(score_m.group(1)) if score_m else None,
            "feedback": _grab(r'"feedback"\s*:\s*"(.*?)"(?=\s*[,}])', ""),
            "strengths": _grab_list("strengths"),
            "areas_to_improve": _grab_list("areas_to_improve"),
            "grammar_errors": _grab_list("grammar_errors"),
            "improved_answer": _grab(r'"improved_answer"\s*:\s*"(.*?)"(?=\s*})', ""),
        }


# ── OpenAI TTS ────────────────────────────────────────────────────────────────

def text_to_speech(text: str, openai_api_key: str, voice: str = "onyx", speed: float = 0.92) -> bytes:
    """Call OpenAI TTS and return raw MP3 bytes."""
    from openai import OpenAI
    client = OpenAI(api_key=openai_api_key)
    resp = client.audio.speech.create(
        model="tts-1-hd",
        voice=voice,
        input=text,
        speed=speed,
    )
    return resp.content


# ── Whisper STT ───────────────────────────────────────────────────────────────

def transcribe_audio(audio_bytes: bytes, filename: str, openai_api_key: str, language: str = "EN") -> str:
    """Transcribe audio bytes using Whisper. Returns transcribed text."""
    from openai import OpenAI
    client = OpenAI(api_key=openai_api_key)
    lang_code = "fr" if language.upper() == "FR" else "en"
    buf = io.BytesIO(audio_bytes)
    buf.name = filename
    result = client.audio.transcriptions.create(
        model="whisper-1",
        file=buf,
        language=lang_code,
    )
    return result.text.strip()
