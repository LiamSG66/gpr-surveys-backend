"""
Modal app — exposes webhook endpoints for Supabase and a daily cron for reminders.

Webhook architecture: A single dispatcher endpoint handles all Supabase DB webhooks.
It routes to the correct workflow based on the `table` and `type` fields in the payload.
This keeps total web endpoints under Modal's free-tier limit of 8.
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

def _is_assignment_only_change(record: dict, old_record: dict) -> bool:
    """Returns True if the ONLY significant change is assigned_to (no date/time/service change)."""
    changed = {f for f in _SIGNIFICANT_FIELDS if record.get(f) != old_record.get(f)}
    return changed == {"assigned_to"}

def _has_datetime_change(record: dict, old_record: dict) -> bool:
    """Returns True if date or booking_time changed."""
    return (record.get("date") != old_record.get("date") or
            record.get("booking_time") != old_record.get("booking_time"))


# ─── Webhook Dispatcher (all Supabase DB webhooks → single endpoint) ──────────
#
# Point all 4 Supabase webhooks at this one URL:
#   - bookings INSERT  → new_booking workflow
#   - bookings UPDATE  → cancel/assign/modify_booking workflow
#   - booking_files INSERT → sync_file_to_drive workflow
#   - contact_submissions INSERT → new_contact workflow

@app.function(image=gpr_image, secrets=[gpr_secrets, gpr_service_account], scaledown_window=60)
@modal.fastapi_endpoint(method="POST")
async def webhook_dispatcher(request: Request) -> dict:
    headers = dict(request.headers)
    if not _verify_webhook_secret(headers):
        raise HTTPException(status_code=401, detail="Unauthorized")

    payload = await request.json()
    table      = payload.get("table", "")
    event_type = payload.get("type", "")   # INSERT | UPDATE | DELETE
    record     = payload.get("record") or {}
    old_record = payload.get("old_record") or {}

    logger.info(f"[webhook_dispatcher] table={table!r} type={event_type!r}")

    # ── bookings INSERT ───────────────────────────────────────────────────────
    if table == "bookings" and event_type == "INSERT":
        booking_id = record.get("id")
        if not booking_id:
            return {"error": "No booking id in payload"}
        try:
            run_workflow("new_booking", {"booking_id": booking_id})
            return {"status": "ok", "workflow": "new_booking", "booking_id": booking_id}
        except Exception as e:
            logger.error(f"[webhook_dispatcher/new_booking] {e}")
            return {"status": "error", "message": str(e)}

    # ── bookings UPDATE ───────────────────────────────────────────────────────
    if table == "bookings" and event_type == "UPDATE":
        booking_id = record.get("id")
        if not booking_id:
            return {"error": "No booking id in payload"}

        if not _has_significant_change(record, old_record):
            return {"status": "skipped", "reason": "no significant field changes"}

        new_status = record.get("status")
        old_status = old_record.get("status")

        if new_status == "cancelled" and old_status != "cancelled":
            workflow = "cancel_booking"
        elif new_status == "confirmed" and old_status != "confirmed":
            workflow = "confirm_booking"
        elif _is_assignment_only_change(record, old_record):
            # Tech assignment/unassignment — update calendar only, no customer email
            # (tech notification email is handled by the Next.js API route directly)
            workflow = "assign_booking"
        elif _has_datetime_change(record, old_record):
            # Date or time changed — notify customer (unless suppressed by drag-drop)
            workflow = "modify_booking"
        else:
            return {"status": "skipped", "reason": "no date/time change — customer not notified"}

        skip_customer_email = bool(record.get("skip_customer_email", False))
        tech_email = None

        if workflow == "modify_booking":
            assigned_to = record.get("assigned_to")
            if assigned_to:
                try:
                    from config import settings
                    from supabase import create_client
                    _sb = create_client(settings.supabase_url, settings.supabase_service_key)
                    tech_row = _sb.table("technicians").select("email").eq("id", assigned_to).single().execute()
                    tech_email = (tech_row.data or {}).get("email")
                except Exception as _e:
                    logger.warning(f"[webhook_dispatcher/modify_booking] Could not fetch tech email: {_e}")

            if skip_customer_email:
                try:
                    from config import settings as _settings
                    from supabase import create_client as _create_client
                    _sb2 = _create_client(_settings.supabase_url, _settings.supabase_service_key)
                    _sb2.table("bookings").update({"skip_customer_email": False}).eq("id", booking_id).execute()
                except Exception as _e2:
                    logger.warning(f"[webhook_dispatcher/modify_booking] Could not reset skip_customer_email: {_e2}")

        try:
            run_workflow(workflow, {
                "booking_id":          booking_id,
                "old_date":            old_record.get("date"),
                "old_booking_time":    old_record.get("booking_time"),
                "skip_customer_email": skip_customer_email,
                "tech_email":          tech_email,
            })
            return {"status": "ok", "workflow": workflow, "booking_id": booking_id}
        except Exception as e:
            logger.error(f"[webhook_dispatcher/{workflow}] {e}")
            return {"status": "error", "message": str(e)}

    # ── booking_files INSERT ──────────────────────────────────────────────────
    if table == "booking_files" and event_type == "INSERT":
        job_number = record.get("job_number")
        file_path  = record.get("file_path")
        file_name  = record.get("file_name")
        if not job_number or not file_path or not file_name:
            return {"error": "Missing job_number, file_path, or file_name in record"}
        try:
            result = run_workflow("sync_file_to_drive", {
                "job_number": job_number,
                "file_path":  file_path,
                "file_name":  file_name,
            })
            return {"status": "ok", "workflow": "sync_file_to_drive", **result}
        except Exception as e:
            logger.error(f"[webhook_dispatcher/sync_file_to_drive] {e}")
            return {"status": "error", "message": str(e)}

    # ── contact_submissions INSERT ────────────────────────────────────────────
    if table == "contact_submissions" and event_type == "INSERT":
        submission_id = record.get("id")
        if not submission_id:
            return {"error": "No submission id"}
        try:
            run_workflow("new_contact", {"submission_id": submission_id, "record": record})
            return {"status": "ok", "workflow": "new_contact"}
        except Exception as e:
            logger.error(f"[webhook_dispatcher/new_contact] {e}")
            return {"status": "error", "message": str(e)}

    # ── Unrecognised event ────────────────────────────────────────────────────
    logger.warning(f"[webhook_dispatcher] No handler for table={table!r} type={event_type!r}")
    return {"status": "skipped", "reason": f"no handler for {table}/{event_type}"}


# ─── HTTP: Generate Quote PDF ─────────────────────────────────────────────────

@app.function(image=gpr_image, secrets=[gpr_secrets, gpr_service_account], scaledown_window=60)
@modal.fastapi_endpoint(method="POST")
async def generate_quote_pdf_endpoint(request: Request) -> dict:
    headers = dict(request.headers)
    if not _verify_webhook_secret(headers):
        raise HTTPException(status_code=401, detail="Unauthorized")

    payload = await request.json()
    if not payload.get("contact") or not payload.get("quote_data"):
        raise HTTPException(status_code=400, detail="contact and quote_data are required")

    try:
        result = run_workflow("generate_quote", payload)
        return {
            "drive_file_id": result.get("drive_file_id"),
            "drive_url":     result.get("drive_url"),
        }
    except Exception as e:
        logger.error(f"[generate_quote_pdf_endpoint] {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─── HTTP: Field Report ───────────────────────────────────────────────────────

@app.function(image=gpr_image, secrets=[gpr_secrets, gpr_service_account], scaledown_window=60)
@modal.fastapi_endpoint(method="POST")
async def field_report_endpoint(request: Request) -> dict:
    headers = dict(request.headers)
    if not _verify_webhook_secret(headers):
        raise HTTPException(status_code=401, detail="Unauthorized")

    payload = await request.json()
    if not payload.get("report_data") or not payload.get("booking"):
        raise HTTPException(status_code=400, detail="report_data and booking are required")

    import tools.generate_field_report_pdf as pdf_gen
    import tools.upload_field_report_to_drive as drive_upload
    import tools.send_email as emailer

    report_data    = payload["report_data"]
    photos         = payload.get("photos", [])
    cover_photo    = payload.get("cover_photo", None)
    booking        = payload["booking"]
    create_invoice = payload.get("create_invoice", False)
    invoice_data   = payload.get("invoice_data", {})
    review_email   = payload.get("review_email", False)
    report_date    = report_data.get("report_date", "")

    try:
        # Step 1 — Generate PDF
        pdf_result = pdf_gen.run({"report_data": report_data, "photos": photos, "cover_photo": cover_photo})
        pdf_bytes  = pdf_result["pdf_bytes"]

        # Step 2 — Upload to Drive
        drive_result = drive_upload.run({
            "booking":     booking,
            "pdf_bytes":   pdf_bytes,
            "report_date": report_date,
        })
        drive_file_id  = drive_result["drive_file_id"]
        drive_file_url = drive_result["drive_file_url"]

        invoice_id  = None
        invoice_url = None

        # Step 3+4 — QuickBooks invoice
        if create_invoice and invoice_data:
            try:
                import tools.create_quickbooks_invoice as qb_invoice
                import tools.attach_to_quickbooks_invoice as qb_attach

                qb_result   = qb_invoice.run({"invoice_data": invoice_data})
                invoice_id  = qb_result["invoice_id"]
                invoice_url = qb_result["invoice_url"]
                filename    = f"{report_data.get('job_number', 'report')}_Field_Report_{report_date}.pdf"
                qb_attach.run({"invoice_id": invoice_id, "pdf_bytes": pdf_bytes, "filename": filename})
            except Exception as e:
                logger.error(f"[field_report_endpoint] QB invoice failed: {e}")
                # Don't fail — Drive upload already succeeded

        # Step 5 — Schedule Google Review email (sent by cron 24h later)
        if review_email:
            try:
                from config import settings
                from supabase import create_client
                from datetime import datetime, timezone, timedelta
                supabase_client = create_client(settings.supabase_url, settings.supabase_service_key)
                scheduled_at = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
                supabase_client.table("bookings") \
                    .update({"review_email_scheduled_at": scheduled_at, "review_email_sent": False}) \
                    .eq("id", booking["id"]) \
                    .execute()
                logger.info(f"[field_report_endpoint] Review email scheduled for {scheduled_at}")
            except Exception as e:
                logger.error(f"[field_report_endpoint] Failed to schedule review email: {e}")

        return {
            "drive_file_id":  drive_file_id,
            "drive_file_url": drive_file_url,
            "invoice_id":     invoice_id,
            "invoice_url":    invoice_url,
        }

    except Exception as e:
        logger.error(f"[field_report_endpoint] {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─── HTTP: Send Quote Email ───────────────────────────────────────────────────

@app.function(image=gpr_image, secrets=[gpr_secrets, gpr_service_account], scaledown_window=60)
@modal.fastapi_endpoint(method="POST")
async def send_quote_email_endpoint(request: Request) -> dict:
    headers = dict(request.headers)
    if not _verify_webhook_secret(headers):
        raise HTTPException(status_code=401, detail="Unauthorized")

    payload = await request.json()
    if not payload.get("contact") or not payload.get("drive_file_id"):
        raise HTTPException(status_code=400, detail="contact and drive_file_id are required")

    try:
        result = run_workflow("send_quote", payload)
        return {"email_id": result.get("email_quote_email_id")}
    except Exception as e:
        logger.error(f"[send_quote_email_endpoint] {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─── HTTP: Send Technician Credentials ───────────────────────────────────────

@app.function(image=gpr_image, secrets=[gpr_secrets, gpr_service_account], scaledown_window=60)
@modal.fastapi_endpoint(method="POST")
async def send_tech_credentials_endpoint(request: Request) -> dict:
    headers = dict(request.headers)
    if not _verify_webhook_secret(headers):
        raise HTTPException(status_code=401, detail="Unauthorized")

    payload = await request.json()
    name          = payload.get("name")
    email         = payload.get("email")
    temp_password = payload.get("temp_password")

    if not name or not email or not temp_password:
        raise HTTPException(status_code=400, detail="name, email, and temp_password are required")

    try:
        import tools.send_email as emailer
        emailer.run({
            "template":      "technician_credentials",
            "name":          name,
            "email":         email,
            "temp_password": temp_password,
        })
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"[send_tech_credentials_endpoint] {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─── HTTP: Tech Assignment Notification ──────────────────────────────────────

@app.function(image=gpr_image, secrets=[gpr_secrets, gpr_service_account], scaledown_window=60)
@modal.fastapi_endpoint(method="POST")
async def send_tech_notification_endpoint(request: Request) -> dict:
    """Send a technician_assignment or technician_unassignment email."""
    headers = dict(request.headers)
    if not _verify_webhook_secret(headers):
        raise HTTPException(status_code=401, detail="Unauthorized")

    payload = await request.json()
    template = payload.get("template")
    if template not in ("technician_assignment", "technician_unassignment"):
        raise HTTPException(status_code=400, detail="template must be technician_assignment or technician_unassignment")
    if not payload.get("tech_email"):
        raise HTTPException(status_code=400, detail="tech_email is required")

    try:
        import tools.send_email as emailer
        result = emailer.run(payload)
        return {"status": "ok", **result}
    except Exception as e:
        logger.error(f"[send_tech_notification_endpoint] {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─── HTTP: Time Off Request ───────────────────────────────────────────────────

@app.function(image=gpr_image, secrets=[gpr_secrets, gpr_service_account], scaledown_window=60)
@modal.fastapi_endpoint(method="POST")
async def send_time_off_request_endpoint(request: Request) -> dict:
    """
    Send an admin notification email.
    type="request"  → email admin that a tech submitted a time-off request
    type="approval" → email tech that their time-off request was approved
    type="billing"  → email admin that a customer submitted billing info
    """
    headers = dict(request.headers)
    if not _verify_webhook_secret(headers):
        raise HTTPException(status_code=401, detail="Unauthorized")

    payload    = await request.json()
    email_type = payload.get("type", "request")  # "request" | "approval" | "billing"

    try:
        import tools.send_email as emailer

        if email_type == "billing":
            result = emailer.run({
                "template":               "billing_notification",
                "first_name":             payload.get("first_name", ""),
                "last_name":              payload.get("last_name", ""),
                "email":                  payload.get("email", ""),
                "phone":                  payload.get("phone", ""),
                "company":                payload.get("company", ""),
                "billing_email":          payload.get("billing_email", ""),
                "billing_address_line1":  payload.get("billing_address_line1", ""),
                "billing_address_line2":  payload.get("billing_address_line2", ""),
                "billing_city":           payload.get("billing_city", ""),
                "billing_province":       payload.get("billing_province", ""),
                "billing_postal_code":    payload.get("billing_postal_code", ""),
            })
        else:
            tech_name  = payload.get("tech_name")
            tech_email = payload.get("tech_email")
            dates      = payload.get("dates", [])

            if not tech_name or not tech_email:
                raise HTTPException(status_code=400, detail="tech_name and tech_email are required")
            if not dates:
                raise HTTPException(status_code=400, detail="at least one date is required")

            template = "time_off_request" if email_type == "request" else "time_off_approval"
            result = emailer.run({
                "template":   template,
                "tech_name":  tech_name,
                "tech_email": tech_email,
                "dates":      dates,
                "notes":      payload.get("notes", ""),
            })

        return {"status": "ok", **result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[send_time_off_request_endpoint] {e}")
        raise HTTPException(status_code=500, detail=str(e))


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


# ─── Cron: Stale Contact Alert ────────────────────────────────────────────────

@app.function(
    image=gpr_image,
    secrets=[gpr_secrets, gpr_service_account],
    schedule=modal.Period(hours=24),
)
def alert_stale_contacts():
    """Runs daily — emails admin if any contacts have been in 'new' status for 24h+ (no quote sent)."""
    from config import settings
    from supabase import create_client
    import tools.send_email as emailer
    from datetime import datetime, timezone, timedelta

    supabase = create_client(settings.supabase_url, settings.supabase_service_key)
    cutoff   = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()

    result = supabase.table("contact_submissions") \
        .select("id, first_name, last_name, company, email, service, created_at") \
        .eq("quote_status", "new") \
        .lt("created_at", cutoff) \
        .execute()

    contacts = result.data or []
    logger.info(f"[alert_stale_contacts] Found {len(contacts)} stale contacts")

    if contacts:
        try:
            emailer.run({"contacts": contacts, "template": "stale_contacts_alert"})
            logger.info(f"[alert_stale_contacts] Alert sent for {len(contacts)} contacts")
        except Exception as e:
            logger.error(f"[alert_stale_contacts] Failed: {e}")


# ─── Cron: Quote Follow-up ────────────────────────────────────────────────────

@app.function(
    image=gpr_image,
    secrets=[gpr_secrets, gpr_service_account],
    schedule=modal.Period(hours=24),
)
def followup_stale_quotes():
    """Runs daily — sends a one-time follow-up email 30 days after a quote is sent.

    Rules:
    - quote_status = 'quoted'
    - converted_booking_id IS NULL  (not yet booked)
    - quote_sent_at between 29 and 31 days ago  (±1 day window handles cron timing jitter)
    - quote_followup_sent_at IS NULL  (not already followed up)
    After a successful send, sets quote_followup_sent_at to prevent duplicate sends.
    """
    from config import settings
    from supabase import create_client
    import tools.send_email as emailer
    from datetime import datetime, timezone, timedelta

    supabase  = create_client(settings.supabase_url, settings.supabase_service_key)
    now       = datetime.now(timezone.utc)
    cutoff_31 = (now - timedelta(days=31)).isoformat()
    cutoff_29 = (now - timedelta(days=29)).isoformat()

    result = supabase.table("contact_submissions") \
        .select("*") \
        .eq("quote_status", "quoted") \
        .gt("quote_sent_at", cutoff_31) \
        .lt("quote_sent_at", cutoff_29) \
        .is_("converted_booking_id", "null") \
        .is_("quote_followup_sent_at", "null") \
        .execute()

    contacts = result.data or []
    logger.info(f"[followup_stale_quotes] Found {len(contacts)} quotes eligible for follow-up")

    for contact in contacts:
        try:
            sent_at  = contact.get("quote_sent_at", "")
            days_ago = 30
            if sent_at:
                try:
                    sent_dt  = datetime.fromisoformat(sent_at.replace("Z", "+00:00"))
                    days_ago = (now - sent_dt).days
                except Exception:
                    pass

            emailer.run({
                "contact":      contact,
                "template":     "quote_followup",
                "days_ago":     days_ago,
                "quote_number": contact.get("quote_number", ""),
            })

            # Mark as sent to prevent duplicates
            supabase.table("contact_submissions") \
                .update({"quote_followup_sent_at": now.isoformat()}) \
                .eq("id", contact["id"]) \
                .execute()

            logger.info(f"[followup_stale_quotes] Follow-up sent for {contact.get('quote_number')}")
        except Exception as e:
            logger.error(f"[followup_stale_quotes] Failed for {contact.get('quote_number')}: {e}")


# ─── Cron: Google Review Requests ─────────────────────────────────────────────

@app.function(
    image=gpr_image,
    secrets=[gpr_secrets, gpr_service_account],
    schedule=modal.Period(hours=24),
)
def send_review_requests():
    """Runs daily — sends Google Review request emails to customers whose review_email_scheduled_at has passed."""
    from config import settings
    from supabase import create_client
    import tools.send_email as emailer
    from datetime import datetime, timezone

    supabase = create_client(settings.supabase_url, settings.supabase_service_key)
    now      = datetime.now(timezone.utc)

    result = supabase.table("bookings") \
        .select("*, customers(*)") \
        .lte("review_email_scheduled_at", now.isoformat()) \
        .eq("review_email_sent", False) \
        .not_.is_("review_email_scheduled_at", "null") \
        .execute()

    bookings = result.data or []
    logger.info(f"[send_review_requests] Found {len(bookings)} review emails to send")

    for booking in bookings:
        try:
            emailer.run({"booking": booking, "template": "google_review_request"})
            supabase.table("bookings") \
                .update({"review_email_sent": True}) \
                .eq("id", booking["id"]) \
                .execute()
            logger.info(f"[send_review_requests] Review email sent for {booking.get('job_number')}")
        except Exception as e:
            logger.error(f"[send_review_requests] Failed for {booking.get('job_number')}: {e}")
