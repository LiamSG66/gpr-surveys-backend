"""
Modal app — exposes webhook endpoints for Supabase and a daily cron for reminders.
"""

import sys, os
sys.path.insert(0, "/root")

import modal
import logging
from fastapi import Request, HTTPException
from agent import run_workflow

logger = logging.getLogger(__name__)

# ─── Modal App Definition ────────────────────────────────────────────────────

app = modal.App("gpr-surveys-backend")

gpr_image = (
    modal.Image.debian_slim()
    .pip_install_from_requirements("requirements.txt")
    .pip_install("fastapi[standard]")
    .add_local_dir(".", remote_path="/root")
)

# Load secrets from Modal's secret store (set via modal secret create)
gpr_secrets = modal.Secret.from_name("gpr-surveys-secrets")
gpr_service_account = modal.Secret.from_name("gpr-service-account")


def _verify_webhook_secret(headers: dict) -> bool:
    """Verify the Authorization header matches our webhook secret."""
    expected = os.environ.get("WEBHOOK_SECRET", "")
    auth = headers.get("authorization", "") or headers.get("Authorization", "")
    return auth == f"Bearer {expected}"


# Fields that, when changed, warrant running the modify_booking workflow
_SIGNIFICANT_FIELDS = {"date", "booking_time", "assigned_to", "service", "status"}

def _has_significant_change(record: dict, old_record: dict) -> bool:
    """Returns True if any field that matters to workflows changed."""
    for field in _SIGNIFICANT_FIELDS:
        if record.get(field) != old_record.get(field):
            return True
    return False


# ─── Webhook: Booking Created ─────────────────────────────────────────────────

@app.function(image=gpr_image, secrets=[gpr_secrets, gpr_service_account], scaledown_window=60)
@modal.fastapi_endpoint(method="POST")
async def webhook_booking_created(request: Request) -> dict:
    headers = dict(request.headers)
    if not _verify_webhook_secret(headers):
        raise HTTPException(status_code=401, detail="Unauthorized")

    payload = await request.json()
    booking_id = (payload.get("record") or {}).get("id")
    if not booking_id:
        return {"error": "No booking id in payload"}

    try:
        run_workflow("new_booking", {"booking_id": booking_id})
        return {"status": "ok", "workflow": "new_booking", "booking_id": booking_id}
    except Exception as e:
        logger.error(f"[webhook_booking_created] {e}")
        return {"status": "error", "message": str(e)}


# ─── Webhook: Booking Updated ─────────────────────────────────────────────────

@app.function(image=gpr_image, secrets=[gpr_secrets, gpr_service_account], scaledown_window=60)
@modal.fastapi_endpoint(method="POST")
async def webhook_booking_updated(request: Request) -> dict:
    headers = dict(request.headers)
    if not _verify_webhook_secret(headers):
        raise HTTPException(status_code=401, detail="Unauthorized")

    payload = await request.json()
    record = payload.get("record") or {}
    old_record = payload.get("old_record") or {}
    booking_id = record.get("id")

    if not booking_id:
        return {"error": "No booking id in payload"}

    if not _has_significant_change(record, old_record):
        return {"status": "skipped", "reason": "no significant field changes"}

    new_status = record.get("status")
    old_status = old_record.get("status")

    if new_status == "cancelled" and old_status != "cancelled":
        workflow = "cancel_booking"
    else:
        workflow = "modify_booking"

    try:
        run_workflow(workflow, {
            "booking_id": booking_id,
            "old_date": old_record.get("date"),
            "old_booking_time": old_record.get("booking_time"),
        })
        return {"status": "ok", "workflow": workflow, "booking_id": booking_id}
    except Exception as e:
        logger.error(f"[webhook_booking_updated] {e}")
        return {"status": "error", "message": str(e)}


# ─── Webhook: Booking File Uploaded ──────────────────────────────────────────

@app.function(image=gpr_image, secrets=[gpr_secrets, gpr_service_account], scaledown_window=60)
@modal.fastapi_endpoint(method="POST")
async def webhook_booking_file_created(request: Request) -> dict:
    headers = dict(request.headers)
    if not _verify_webhook_secret(headers):
        raise HTTPException(status_code=401, detail="Unauthorized")

    payload = await request.json()
    record = payload.get("record") or {}
    job_number = record.get("job_number")
    file_path = record.get("file_path")
    file_name = record.get("file_name")

    if not job_number or not file_path or not file_name:
        return {"error": "Missing job_number, file_path, or file_name in record"}

    try:
        result = run_workflow("sync_file_to_drive", {
            "job_number": job_number,
            "file_path": file_path,
            "file_name": file_name,
        })
        return {"status": "ok", "workflow": "sync_file_to_drive", **result}
    except Exception as e:
        logger.error(f"[webhook_booking_file_created] {e}")
        return {"status": "error", "message": str(e)}


# ─── Webhook: Contact Submission ──────────────────────────────────────────────

@app.function(image=gpr_image, secrets=[gpr_secrets, gpr_service_account], scaledown_window=60)
@modal.fastapi_endpoint(method="POST")
async def webhook_contact_created(request: Request) -> dict:
    headers = dict(request.headers)
    if not _verify_webhook_secret(headers):
        raise HTTPException(status_code=401, detail="Unauthorized")

    payload = await request.json()
    submission_id = (payload.get("record") or {}).get("id")
    if not submission_id:
        return {"error": "No submission id"}

    try:
        run_workflow("new_contact", {"submission_id": submission_id, "record": payload.get("record", {})})
        return {"status": "ok", "workflow": "new_contact"}
    except Exception as e:
        logger.error(f"[webhook_contact_created] {e}")
        return {"status": "error", "message": str(e)}


# ─── Cron: 48-hour Reminders ──────────────────────────────────────────────────

@app.function(
    image=gpr_image,
    secrets=[gpr_secrets, gpr_service_account],
    schedule=modal.Period(hours=24),
)
def send_reminders():
    """Runs daily — fetches bookings 48h out and sends reminder emails."""
    import tools.fetch_pending_reminders as fetcher
    import tools.send_email as emailer

    result = fetcher.run({})
    bookings = result.get("bookings", [])

    logger.info(f"[send_reminders] Found {len(bookings)} bookings to remind")

    for booking in bookings:
        try:
            emailer.run({"booking": booking, "template": "booking_reminder"})
            logger.info(f"[send_reminders] Reminder sent for {booking.get('job_number')}")
        except Exception as e:
            logger.error(f"[send_reminders] Failed for {booking.get('job_number')}: {e}")
