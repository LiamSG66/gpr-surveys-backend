"""
Update a job_applications record in Supabase with AI scoring fields.

payload keys: application_id, ai_score, ai_score_summary, ai_score_breakdown
"""

import logging
from supabase import create_client
from config import settings

logger = logging.getLogger(__name__)


def run(payload: dict) -> dict:
    application_id = payload.get("application_id")
    if not application_id:
        return {"error": "update_candidate_record: application_id is required"}

    ai_score          = payload.get("ai_score")
    ai_score_summary  = payload.get("ai_score_summary")
    ai_score_breakdown = payload.get("ai_score_breakdown")

    if ai_score is None:
        return {"error": "update_candidate_record: ai_score is required"}

    try:
        sb = create_client(settings.supabase_url, settings.supabase_service_key)

        updates = {
            "ai_score":          ai_score,
            "ai_score_summary":  ai_score_summary or "",
            "ai_score_breakdown": ai_score_breakdown or {},
        }

        result = sb.table("job_applications") \
            .update(updates) \
            .eq("id", application_id) \
            .execute()

        return {"candidate_record_updated": True, "application_id": application_id}

    except Exception as e:
        logger.error(f"[update_candidate_record] {e}")
        return {"error": str(e)}
