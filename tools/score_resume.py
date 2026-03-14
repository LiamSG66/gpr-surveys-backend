"""
Score a resume via Claude AI.

Fetches the resume PDF from Supabase Storage, extracts text, calls the Claude API
with context about the job, and returns a structured score.

payload keys: application_id, resume_url, resume_filename, job_title, job_description,
              first_name, last_name

Returns: {
    ai_score: int (1-10),
    ai_score_summary: str,
    ai_score_breakdown: { experience: int, skills: int, education: int, overall_fit: int },
    recommendation: str,
}
"""

import json
import logging
import httpx

logger = logging.getLogger(__name__)


def _fetch_pdf_bytes(resume_url: str) -> bytes:
    """Download the PDF from the given URL (Supabase Storage public URL)."""
    with httpx.Client(timeout=30) as client:
        resp = client.get(resume_url)
        resp.raise_for_status()
        return resp.content


def _extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract plain text from a PDF using pymupdf (fitz), which is already in requirements."""
    try:
        import fitz  # pymupdf
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pages = [page.get_text() for page in doc]
        doc.close()
        return "\n".join(pages).strip()
    except Exception as e:
        logger.warning(f"[score_resume] pymupdf extraction failed: {e} — falling back to raw bytes")
        # Last resort: decode bytes as UTF-8 ignoring errors (picks up some readable text)
        return pdf_bytes.decode("utf-8", errors="ignore")


def run(payload: dict) -> dict:
    resume_url   = payload.get("resume_url", "")
    job_title    = payload.get("job_title", "the position")
    job_description = payload.get("job_description", "")
    first_name   = payload.get("first_name", "")
    last_name    = payload.get("last_name", "")

    if not resume_url:
        return {"error": "score_resume: resume_url is required"}

    # Step 1 — Fetch PDF
    try:
        pdf_bytes = _fetch_pdf_bytes(resume_url)
    except Exception as e:
        logger.error(f"[score_resume] Failed to fetch resume from {resume_url}: {e}")
        return {"error": f"score_resume: could not fetch resume — {e}"}

    # Step 2 — Extract text
    try:
        resume_text = _extract_text_from_pdf(pdf_bytes)
    except Exception as e:
        logger.error(f"[score_resume] Failed to extract text: {e}")
        return {"error": f"score_resume: could not extract text from PDF — {e}"}

    if not resume_text.strip():
        return {"error": "score_resume: extracted resume text is empty"}

    # Step 3 — Call Claude
    try:
        import anthropic

        client = anthropic.Anthropic()

        candidate_name = f"{first_name} {last_name}".strip() or "the candidate"

        system_prompt = (
            "You are an expert recruiter and hiring manager. "
            "Evaluate resumes objectively and return structured JSON scores. "
            "Always respond with valid JSON only — no markdown, no explanation outside the JSON."
        )

        user_prompt = f"""Evaluate this resume for the following job opening.

JOB TITLE: {job_title}

JOB DESCRIPTION:
{job_description or "No description provided."}

CANDIDATE: {candidate_name}

RESUME TEXT:
{resume_text[:8000]}

Score the candidate on a 1-10 scale across four dimensions, then provide an overall score and recommendation.

Respond with this exact JSON structure:
{{
  "ai_score": <integer 1-10, overall score>,
  "ai_score_summary": "<2-3 sentences summarizing the candidate's fit>",
  "ai_score_breakdown": {{
    "experience": <integer 1-10>,
    "skills": <integer 1-10>,
    "education": <integer 1-10>,
    "overall_fit": <integer 1-10>
  }},
  "recommendation": "<one of: Strong fit, Good fit, Possible fit, Weak fit, Not a fit>"
}}"""

        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )

        raw = message.content[0].text.strip()

        # Strip markdown code fences if Claude wrapped in them despite instructions
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        result = json.loads(raw)

        return {
            "ai_score":           int(result.get("ai_score", 0)),
            "ai_score_summary":   str(result.get("ai_score_summary", "")),
            "ai_score_breakdown": result.get("ai_score_breakdown", {}),
            "recommendation":     str(result.get("recommendation", "")),
        }

    except json.JSONDecodeError as e:
        logger.error(f"[score_resume] Claude returned invalid JSON: {e}")
        return {"error": f"score_resume: Claude returned invalid JSON — {e}"}
    except Exception as e:
        logger.error(f"[score_resume] Claude API call failed: {e}")
        return {"error": f"score_resume: Claude API error — {e}"}
