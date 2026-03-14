"""
Fetch a job_applications record and its associated job_postings record from Supabase.

Returns a flat dict with all application fields plus job_posting_id, job_title, job_description.

payload keys: application_id
"""

import logging
from supabase import create_client
from config import settings

logger = logging.getLogger(__name__)


def run(payload: dict) -> dict:
    application_id = payload.get("application_id")
    if not application_id:
        return {"error": "fetch_application: application_id is required"}

    try:
        sb = create_client(settings.supabase_url, settings.supabase_service_key)

        result = sb.table("job_applications") \
            .select("*, job_postings(id, title, description)") \
            .eq("id", application_id) \
            .single() \
            .execute()

        row = result.data
        if not row:
            return {"error": f"fetch_application: no record found for id={application_id}"}

        posting = row.pop("job_postings", None) or {}

        # Generate a signed URL so score_resume.py can fetch the PDF (bucket is private)
        resume_path = row.get("resume_url", "") or ""
        if resume_path and not resume_path.startswith("http"):
            signed = sb.storage.from_("resumes").create_signed_url(resume_path, expires_in=300)
            resume_url = signed.get("signedURL") or signed.get("signed_url") or ""
        else:
            resume_url = resume_path

        return {
            **row,
            "application_id":  row.get("id", application_id),
            "job_posting_id":  posting.get("id", ""),
            "job_title":       posting.get("title", ""),
            "job_description": posting.get("description", ""),
            "resume_url":      resume_url,
        }

    except Exception as e:
        logger.error(f"[fetch_application] {e}")
        return {"error": str(e)}
