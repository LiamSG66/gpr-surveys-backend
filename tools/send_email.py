"""
Send email via Gmail API.
Supports templates: booking_received, customer_confirmation, internal_notification, customer_cancellation,
                    customer_modification, booking_reminder, contact_notification,
                    quote_email, stale_contacts_alert, quote_followup,
                    technician_assignment, technician_unassignment, tech_date_change,
                    technician_credentials, time_off_request, google_review_request,
                    new_application, application_received, interview_scheduled, application_rejected
"""

import base64
import json
import logging
import os
import time
from html import escape as _esc
import jwt

logger = logging.getLogger(__name__)
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from tools.auth import get_google_service
from config import settings

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
GMAIL_SUBJECT = "info@gprsurveys.ca"


def _generate_modify_token(job_number: str, email: str) -> str:
    secret = os.environ.get("BOOKING_TOKEN_SECRET", "")
    payload = {
        "jobNumber": job_number,
        "email": email,
        "iat": int(time.time()),
        "exp": int(time.time()) + 2592000,  # 30 days
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def _get_service():
    return get_google_service("gmail", "v1", subject=GMAIL_SUBJECT, scopes=SCOPES)


def _send(service, to: str, subject: str, html: str, plain: str, attachment: dict | None = None) -> str:
    """
    attachment = { "filename": str, "content_bytes": bytes, "mime_type": str } | None
    """
    if attachment:
        outer = MIMEMultipart("mixed")
        outer["Subject"] = subject
        outer["From"] = settings.gmail_sender
        outer["To"] = to
        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(plain, "plain"))
        alt.attach(MIMEText(html, "html"))
        outer.attach(alt)
        # Attach the file
        part = MIMEBase("application", "pdf")
        part.set_payload(attachment["content_bytes"])
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            "attachment",
            filename=attachment["filename"],
        )
        outer.attach(part)
        msg = outer
    else:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.gmail_sender
        msg["To"] = to
        msg.attach(MIMEText(plain, "plain"))
        msg.attach(MIMEText(html, "html"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    result = service.users().messages().send(userId="me", body={"raw": raw}).execute()
    return result["id"]


def _fmt_date(date_str: str) -> str:
    from datetime import datetime
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%B %d, %Y")
    except Exception:
        return date_str


def _fmt_time(time_str: str) -> str:
    from datetime import datetime
    try:
        t = datetime.strptime(time_str[:5], "%H:%M")
        hour = t.strftime("%I").lstrip("0") or "12"
        return f"{hour}:{t.strftime('%M')} {t.strftime('%p')}"
    except Exception:
        return time_str[:5]


def _fmt_dates(booking: dict) -> str:
    additional_dates = booking.get("additional_dates") or []
    if len(additional_dates) > 1:
        return ", ".join(_fmt_date(d) for d in sorted(additional_dates))
    return _fmt_date(booking.get("date", ""))


def _fmt_address(booking: dict) -> str:
    parts = [
        booking.get("site_address_line1", ""),
        booking.get("site_address_line2", ""),
        booking.get("site_city", ""),
        booking.get("site_province", ""),
        booking.get("site_postal_code", ""),
    ]
    return ", ".join(p for p in parts if p)


def _customer_confirmation(booking: dict) -> tuple[str, str, str]:
    job = booking.get("job_number", "")
    service = booking.get("service", "")
    date = _fmt_dates(booking)
    booking_time = _fmt_time(booking.get("booking_time", ""))
    location = _fmt_address(booking)
    customer = booking.get("customers") or {}
    first_name = customer.get("first_name", "")
    customer_email = customer.get("email", "")

    modify_token = _generate_modify_token(job, customer_email) if job and customer_email else ""
    modify_url = f"https://gprsurveys.ca/modify?token={modify_token}" if modify_token else "https://gprsurveys.ca/modify"

    h_first_name = _esc(first_name)
    h_job        = _esc(job)
    h_service    = _esc(service)
    h_location   = _esc(location)

    subject = f"Booking Confirmed — {job} | GPR Surveys"
    html = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto;background:#0a0a0a;color:#fff;padding:40px;">
      <div style="border-top:2px solid #FFD700;padding-top:24px;margin-bottom:32px;">
        <h1 style="font-size:13px;letter-spacing:0.2em;text-transform:uppercase;color:#FFD700;margin:0 0 4px;">GPR SURVEYS</h1>
      </div>
      <h2 style="font-size:22px;margin:0 0 8px;">Booking Confirmed</h2>
      <p style="color:#94a3b8;margin-bottom:32px;">Hi {h_first_name}, your GPR survey has been confirmed.</p>
      <table style="width:100%;border-collapse:collapse;margin-bottom:32px;">
        <tr><td style="padding:10px 0;color:#94a3b8;font-size:13px;border-bottom:1px solid #2a2a2a;">Job Number</td><td style="padding:10px 0;font-size:13px;font-weight:600;border-bottom:1px solid #2a2a2a;">{h_job}</td></tr>
        <tr><td style="padding:10px 0;color:#94a3b8;font-size:13px;border-bottom:1px solid #2a2a2a;">Service</td><td style="padding:10px 0;font-size:13px;border-bottom:1px solid #2a2a2a;">{h_service}</td></tr>
        <tr><td style="padding:10px 0;color:#94a3b8;font-size:13px;border-bottom:1px solid #2a2a2a;">Date(s)</td><td style="padding:10px 0;font-size:13px;border-bottom:1px solid #2a2a2a;">{date}</td></tr>
        <tr><td style="padding:10px 0;color:#94a3b8;font-size:13px;border-bottom:1px solid #2a2a2a;">Time</td><td style="padding:10px 0;font-size:13px;border-bottom:1px solid #2a2a2a;">{booking_time}</td></tr>
        <tr><td style="padding:10px 0;color:#94a3b8;font-size:13px;">Location</td><td style="padding:10px 0;font-size:13px;">{h_location}</td></tr>
      </table>
      <p style="margin-bottom:8px;">
        <a href="{modify_url}" style="display:inline-block;background:#FFD700;color:#0a0a0a;text-decoration:none;font-size:12px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;padding:12px 24px;">
          Modify My Booking
        </a>
      </p>
      <p style="font-size:12px;color:#3a3a3a;border-top:1px solid #2a2a2a;padding-top:24px;">
        This link is valid for 30 days. If it expires, visit gprsurveys.ca/modify and enter your job number.
      </p>
    </div>
    """
    plain = f"Booking Confirmed — {job}\nService: {service}\nDate(s): {date} at {booking_time}\nLocation: {location}\n\nModify your booking: {modify_url}"
    return subject, html, plain


def _booking_received(booking: dict) -> tuple[str, str, str]:
    """Sent immediately on booking submission — job is pending review, not yet confirmed."""
    job = booking.get("job_number", "")
    service = booking.get("service", "")
    date = _fmt_dates(booking)
    booking_time = _fmt_time(booking.get("booking_time", ""))
    location = _fmt_address(booking)
    customer = booking.get("customers") or {}
    first_name = customer.get("first_name", "")
    customer_email = customer.get("email", "")

    modify_token = _generate_modify_token(job, customer_email) if job and customer_email else ""
    modify_url = f"https://gprsurveys.ca/modify?token={modify_token}" if modify_token else "https://gprsurveys.ca/modify"

    h_first_name = _esc(first_name)
    h_job        = _esc(job)
    h_service    = _esc(service)
    h_location   = _esc(location)

    subject = f"Booking Request Received — {job} | GPR Surveys"
    html = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto;background:#0a0a0a;color:#fff;padding:40px;">
      <div style="border-top:2px solid #FFD700;padding-top:24px;margin-bottom:32px;">
        <h1 style="font-size:13px;letter-spacing:0.2em;text-transform:uppercase;color:#FFD700;margin:0 0 4px;">GPR SURVEYS</h1>
      </div>
      <h2 style="font-size:22px;margin:0 0 8px;">We've Received Your Request</h2>
      <p style="color:#94a3b8;margin-bottom:32px;">Hi {h_first_name}, thank you for booking with GPR Surveys. Our team is reviewing your job request now — we'll send you a confirmation email once it's been confirmed.</p>
      <table style="width:100%;border-collapse:collapse;margin-bottom:32px;">
        <tr><td style="padding:10px 0;color:#94a3b8;font-size:13px;border-bottom:1px solid #2a2a2a;">Job Number</td><td style="padding:10px 0;font-size:13px;font-weight:600;border-bottom:1px solid #2a2a2a;">{h_job}</td></tr>
        <tr><td style="padding:10px 0;color:#94a3b8;font-size:13px;border-bottom:1px solid #2a2a2a;">Service</td><td style="padding:10px 0;font-size:13px;border-bottom:1px solid #2a2a2a;">{h_service}</td></tr>
        <tr><td style="padding:10px 0;color:#94a3b8;font-size:13px;border-bottom:1px solid #2a2a2a;">Requested Date(s)</td><td style="padding:10px 0;font-size:13px;border-bottom:1px solid #2a2a2a;">{date}</td></tr>
        <tr><td style="padding:10px 0;color:#94a3b8;font-size:13px;border-bottom:1px solid #2a2a2a;">Time</td><td style="padding:10px 0;font-size:13px;border-bottom:1px solid #2a2a2a;">{booking_time}</td></tr>
        <tr><td style="padding:10px 0;color:#94a3b8;font-size:13px;">Location</td><td style="padding:10px 0;font-size:13px;">{h_location}</td></tr>
      </table>
      <p style="margin-bottom:8px;">
        <a href="{modify_url}" style="display:inline-block;background:#FFD700;color:#0a0a0a;text-decoration:none;font-size:12px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;padding:12px 24px;">
          Modify My Request
        </a>
      </p>
      <p style="font-size:12px;color:#3a3a3a;border-top:1px solid #2a2a2a;padding-top:24px;">
        This link is valid for 30 days. If it expires, visit gprsurveys.ca/modify and enter your job number.
      </p>
    </div>
    """
    plain = (
        f"Booking Request Received — {job}\n\n"
        f"Hi {first_name}, thank you for booking with GPR Surveys. Our team is reviewing your job request now.\n"
        f"We'll send you a confirmation email once it's been confirmed.\n\n"
        f"Service: {service}\nRequested Date(s): {date} at {booking_time}\nLocation: {location}\n\n"
        f"Modify your request: {modify_url}"
    )
    return subject, html, plain


def _internal_notification(booking: dict) -> tuple[str, str, str]:
    job = booking.get("job_number", "")
    service = booking.get("service", "")
    date = _fmt_date(booking.get("date", ""))
    time = booking.get("booking_time", "")[:5]
    address = f"{booking.get('site_address_line1', '')} {booking.get('site_city', '')} {booking.get('site_province', '')}"
    customer = booking.get("customers") or {}
    customer_name = f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip()
    portal_url = f"https://gprsurveys.ca/admin/job/{job}" if job else "https://gprsurveys.ca/admin/jobs"

    h_job           = _esc(job)
    h_service       = _esc(service)
    h_address       = _esc(address)
    h_customer_name = _esc(customer_name)
    h_customer_email = _esc(customer.get("email", ""))
    h_site_contact  = _esc(f"{booking.get('site_contact_first_name', '')} {booking.get('site_contact_last_name', '')}".strip())
    h_site_phone    = _esc(booking.get("site_contact_phone", ""))
    h_notes         = _esc(booking.get("notes", "") or "—")

    subject = f"[NEW BOOKING] {job} — {service} — {booking.get('site_city', '')}"
    html = f"""
    <div style="font-family:sans-serif;max-width:600px;">
      <h2>[NEW BOOKING] {h_job}</h2>
      <p><strong>Service:</strong> {h_service}<br>
      <strong>Date:</strong> {date} at {time}<br>
      <strong>Site:</strong> {h_address}<br>
      <strong>Customer:</strong> {h_customer_name} — {h_customer_email}<br>
      <strong>Site Contact:</strong> {h_site_contact} {h_site_phone}</p>
      <p><strong>Notes:</strong> {h_notes}</p>
      <p style="margin-top:16px;">
        <a href="{portal_url}" style="display:inline-block;background:#111;color:#FFD700;text-decoration:none;font-size:12px;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;padding:10px 20px;border:1px solid #FFD700;">
          View in Admin Portal →
        </a>
      </p>
    </div>
    """
    plain = f"NEW BOOKING: {job}\nService: {service}\nDate: {date} at {time}\nSite: {address}\nCustomer: {customer_name}\n\nView in admin: {portal_url}"
    return subject, html, plain


def _booking_reminder(booking: dict) -> tuple[str, str, str]:
    job = booking.get("job_number", "")
    date = _fmt_date(booking.get("date", ""))
    time = booking.get("booking_time", "")[:5]
    customer = booking.get("customers") or {}
    first_name = customer.get("first_name", "")

    h_first_name = _esc(first_name)
    h_job        = _esc(job)

    subject = f"Reminder: Your GPR Survey — {job}"
    html = f"""
    <div style="font-family:sans-serif;max-width:600px;background:#0a0a0a;color:#fff;padding:40px;">
      <h2>Survey Reminder</h2>
      <p>Hi {h_first_name}, this is a reminder that your GPR survey is scheduled for:</p>
      <p><strong>Job:</strong> {h_job}<br><strong>Date:</strong> {date} at {time}</p>
      <p style="color:#94a3b8;font-size:12px;">Questions? Reply to this email or call 1-800-555-0199.</p>
    </div>
    """
    plain = f"Reminder: GPR Survey {job} is scheduled for {date} at {time}."
    return subject, html, plain


def _customer_modification(payload: dict) -> tuple[str, str, str]:
    booking = payload.get("booking") or {}
    job = booking.get("job_number", "")
    service = booking.get("service", "")
    new_date = _fmt_date(booking.get("date", ""))
    new_time = booking.get("booking_time", "")[:5]
    city = booking.get("site_city", "")
    customer = booking.get("customers") or {}
    first_name = customer.get("first_name", "")
    customer_email = customer.get("email", "")

    old_date_raw = payload.get("old_date") or ""
    old_time_raw = payload.get("old_booking_time") or ""
    old_date = _fmt_date(old_date_raw) if old_date_raw else "—"
    old_time = old_time_raw[:5] if old_time_raw else "—"

    modify_token = _generate_modify_token(job, customer_email) if job and customer_email else ""
    modify_url = f"https://gprsurveys.ca/modify?token={modify_token}" if modify_token else "https://gprsurveys.ca/modify"

    h_first_name = _esc(first_name)
    h_job        = _esc(job)
    h_service    = _esc(service)
    h_city       = _esc(city)
    h_old_date   = _esc(old_date)
    h_old_time   = _esc(old_time)
    h_new_date   = _esc(new_date)
    h_new_time   = _esc(new_time)

    subject = f"Booking Rescheduled — {job} | GPR Surveys"
    html = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto;background:#0a0a0a;color:#fff;padding:40px;">
      <div style="border-top:2px solid #FFD700;padding-top:24px;margin-bottom:32px;">
        <h1 style="font-size:13px;letter-spacing:0.2em;text-transform:uppercase;color:#FFD700;margin:0 0 4px;">GPR SURVEYS</h1>
      </div>
      <h2 style="font-size:22px;margin:0 0 8px;">Your Booking Has Been Rescheduled</h2>
      <p style="color:#94a3b8;margin-bottom:32px;">Hi {h_first_name}, your booking ({h_job}) has been rescheduled. Please note the updated date and time below.</p>
      <div style="background:#111111;border:1px solid #2a2a2a;border-radius:4px;padding:20px 24px;margin-bottom:32px;">
        <p style="font-size:11px;letter-spacing:0.18em;text-transform:uppercase;color:#FFD700;opacity:0.7;margin:0 0 16px;">UPDATED SCHEDULE</p>
        <table style="width:100%;border-collapse:collapse;">
          <tr>
            <td style="padding:6px 0;width:28%;border-bottom:1px solid #1e1e1e;"></td>
            <td style="padding:6px 0;font-size:12px;color:#555555;border-bottom:1px solid #1e1e1e;width:36%;">Previously</td>
            <td style="padding:6px 0;font-size:12px;color:#FFD700;font-weight:700;border-bottom:1px solid #1e1e1e;">New</td>
          </tr>
          <tr>
            <td style="padding:12px 0;color:#94a3b8;font-size:13px;border-bottom:1px solid #1e1e1e;">Date</td>
            <td style="padding:12px 0;font-size:13px;color:#555555;text-decoration:line-through;border-bottom:1px solid #1e1e1e;">{h_old_date}</td>
            <td style="padding:12px 0;font-size:15px;font-weight:700;border-bottom:1px solid #1e1e1e;">{h_new_date}</td>
          </tr>
          <tr>
            <td style="padding:12px 0;color:#94a3b8;font-size:13px;">Time</td>
            <td style="padding:12px 0;font-size:13px;color:#555555;text-decoration:line-through;">{h_old_time}</td>
            <td style="padding:12px 0;font-size:15px;font-weight:700;">{h_new_time}</td>
          </tr>
        </table>
      </div>
      <table style="width:100%;border-collapse:collapse;margin-bottom:32px;">
        <tr><td style="padding:10px 0;color:#94a3b8;font-size:13px;border-bottom:1px solid #2a2a2a;">Job Number</td><td style="padding:10px 0;font-size:13px;font-weight:600;border-bottom:1px solid #2a2a2a;">{h_job}</td></tr>
        <tr><td style="padding:10px 0;color:#94a3b8;font-size:13px;border-bottom:1px solid #2a2a2a;">Service</td><td style="padding:10px 0;font-size:13px;border-bottom:1px solid #2a2a2a;">{h_service}</td></tr>
        <tr><td style="padding:10px 0;color:#94a3b8;font-size:13px;">Location</td><td style="padding:10px 0;font-size:13px;">{h_city}</td></tr>
      </table>
      <p style="margin-bottom:8px;">
        <a href="{modify_url}" style="display:inline-block;background:#FFD700;color:#0a0a0a;text-decoration:none;font-size:12px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;padding:12px 24px;">
          Modify My Booking
        </a>
      </p>
      <p style="font-size:12px;color:#3a3a3a;border-top:1px solid #2a2a2a;padding-top:24px;margin-top:24px;">
        If you did not expect this change, please contact us at info@gprsurveys.ca.
      </p>
    </div>
    """
    plain = (
        f"Your booking {job} has been rescheduled.\n\n"
        f"Date:  {old_date}  →  {new_date}\n"
        f"Time:  {old_time}  →  {new_time}\n\n"
        f"Service: {service}\nLocation: {city}\n\n"
        f"Modify your booking: {modify_url}"
    )
    return subject, html, plain


def _internal_modification(payload: dict) -> tuple[str, str, str]:
    """Internal notification for a modified booking — shows before/after date/time."""
    booking = payload.get("booking") or {}
    job = booking.get("job_number", "")
    service = booking.get("service", "")
    new_date = _fmt_date(booking.get("date", ""))
    new_time = booking.get("booking_time", "")[:5]
    address = f"{booking.get('site_address_line1', '')} {booking.get('site_city', '')} {booking.get('site_province', '')}".strip()
    customer = booking.get("customers") or {}
    customer_name = f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip()

    old_date_raw = payload.get("old_date") or ""
    old_time_raw = payload.get("old_booking_time") or ""
    old_date = _fmt_date(old_date_raw) if old_date_raw else "—"
    old_time = old_time_raw[:5] if old_time_raw else "—"

    h_job           = _esc(job)
    h_service       = _esc(service)
    h_address       = _esc(address)
    h_customer_name = _esc(customer_name)
    h_customer_email = _esc(customer.get("email", ""))
    h_site_contact  = _esc(f"{booking.get('site_contact_first_name', '')} {booking.get('site_contact_last_name', '')}".strip())
    h_site_phone    = _esc(booking.get("site_contact_phone", ""))
    h_old_date      = _esc(old_date)
    h_old_time      = _esc(old_time)
    h_new_date      = _esc(new_date)
    h_new_time      = _esc(new_time)
    h_notes         = _esc(booking.get("notes", "") or "—")

    subject = f"[UPDATED BOOKING] {job} — {service} — {booking.get('site_city', '')}"
    html = f"""
    <div style="font-family:sans-serif;max-width:600px;">
      <h2>[UPDATED BOOKING] {h_job}</h2>
      <p><strong>Service:</strong> {h_service}<br>
      <strong>Site:</strong> {h_address}<br>
      <strong>Customer:</strong> {h_customer_name} — {h_customer_email}<br>
      <strong>Site Contact:</strong> {h_site_contact} {h_site_phone}</p>
      <table style="border-collapse:collapse;margin:16px 0;">
        <tr>
          <th style="text-align:left;padding:6px 16px 6px 0;color:#666;font-weight:normal;">Field</th>
          <th style="text-align:left;padding:6px 16px 6px 0;color:#666;font-weight:normal;">Before</th>
          <th style="text-align:left;padding:6px 0;color:#666;font-weight:normal;">After</th>
        </tr>
        <tr>
          <td style="padding:6px 16px 6px 0;"><strong>Date</strong></td>
          <td style="padding:6px 16px 6px 0;">{h_old_date}</td>
          <td style="padding:6px 0;"><strong>{h_new_date}</strong></td>
        </tr>
        <tr>
          <td style="padding:6px 16px 6px 0;"><strong>Time</strong></td>
          <td style="padding:6px 16px 6px 0;">{h_old_time}</td>
          <td style="padding:6px 0;"><strong>{h_new_time}</strong></td>
        </tr>
      </table>
      <p><strong>Notes:</strong> {h_notes}</p>
    </div>
    """
    plain = (
        f"UPDATED BOOKING: {job}\n"
        f"Service: {service}\n"
        f"Date: {old_date} → {new_date}\n"
        f"Time: {old_time} → {new_time}\n"
        f"Site: {address}\n"
        f"Customer: {customer_name}"
    )
    return subject, html, plain


def _internal_cancellation(booking: dict) -> tuple[str, str, str]:
    job = booking.get("job_number", "")
    service = booking.get("service", "")
    date = _fmt_date(booking.get("date", ""))
    time_str = booking.get("booking_time", "")[:5]
    address = f"{booking.get('site_address_line1', '')} {booking.get('site_city', '')} {booking.get('site_province', '')}".strip()
    customer = booking.get("customers") or {}
    customer_name = f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip()
    tech = booking.get("technicians") or {}
    tech_name = tech.get("name", "Unassigned")

    h_job           = _esc(job)
    h_service       = _esc(service)
    h_address       = _esc(address)
    h_customer_name = _esc(customer_name)
    h_customer_email = _esc(customer.get("email", ""))
    h_site_contact  = _esc(f"{booking.get('site_contact_first_name', '')} {booking.get('site_contact_last_name', '')}".strip())
    h_site_phone    = _esc(booking.get("site_contact_phone", ""))
    h_tech_name     = _esc(tech_name)
    h_notes         = _esc(booking.get("notes", "") or "—")

    subject = f"[CANCELLED BOOKING] {job} — {service} — {booking.get('site_city', '')}"
    html = f"""
    <div style="font-family:sans-serif;max-width:600px;">
      <h2>[CANCELLED BOOKING] {h_job}</h2>
      <p><strong>Service:</strong> {h_service}<br>
      <strong>Date:</strong> {date} at {time_str}<br>
      <strong>Site:</strong> {h_address}<br>
      <strong>Customer:</strong> {h_customer_name} — {h_customer_email}<br>
      <strong>Site Contact:</strong> {h_site_contact} {h_site_phone}<br>
      <strong>Assigned Tech:</strong> {h_tech_name}</p>
      <p><strong>Notes:</strong> {h_notes}</p>
    </div>
    """
    plain = (
        f"CANCELLED BOOKING: {job}\n"
        f"Service: {service}\n"
        f"Date: {date} at {time_str}\n"
        f"Site: {address}\n"
        f"Customer: {customer_name}\n"
        f"Assigned Tech: {tech_name}"
    )
    return subject, html, plain


def _customer_cancellation(booking: dict) -> tuple[str, str, str]:
    job = booking.get("job_number", "")
    service = booking.get("service", "")
    date = _fmt_date(booking.get("date", ""))
    customer = booking.get("customers") or {}
    first_name = customer.get("first_name", "")

    h_first_name = _esc(first_name)
    h_job        = _esc(job)
    h_service    = _esc(service)

    subject = f"Booking Cancelled — {job} | GPR Surveys"
    html = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto;background:#0a0a0a;color:#fff;padding:40px;">
      <div style="border-top:2px solid #FFD700;padding-top:24px;margin-bottom:32px;">
        <h1 style="font-size:13px;letter-spacing:0.2em;text-transform:uppercase;color:#FFD700;margin:0 0 4px;">GPR SURVEYS</h1>
      </div>
      <h2 style="font-size:22px;margin:0 0 8px;">Booking Cancelled</h2>
      <p style="color:#94a3b8;margin-bottom:32px;">Hi {h_first_name}, your booking has been cancelled.</p>
      <table style="width:100%;border-collapse:collapse;margin-bottom:32px;">
        <tr><td style="padding:10px 0;color:#94a3b8;font-size:13px;border-bottom:1px solid #2a2a2a;">Job Number</td><td style="padding:10px 0;font-size:13px;font-weight:600;border-bottom:1px solid #2a2a2a;">{h_job}</td></tr>
        <tr><td style="padding:10px 0;color:#94a3b8;font-size:13px;border-bottom:1px solid #2a2a2a;">Service</td><td style="padding:10px 0;font-size:13px;border-bottom:1px solid #2a2a2a;">{h_service}</td></tr>
        <tr><td style="padding:10px 0;color:#94a3b8;font-size:13px;">Date</td><td style="padding:10px 0;font-size:13px;">{date}</td></tr>
      </table>
      <p style="color:#94a3b8;font-size:13px;">
        If you believe this was an error or would like to rebook, please contact us at
        <a href="mailto:info@gprsurveys.ca" style="color:#FFD700;">info@gprsurveys.ca</a>.
      </p>
    </div>
    """
    plain = f"Booking Cancelled — {job}\nService: {service}\nDate: {date}\n\nContact info@gprsurveys.ca to rebook."
    return subject, html, plain


def _contact_notification(record: dict) -> tuple[str, str, str]:
    first_name   = record.get("first_name", "")
    last_name    = record.get("last_name", "")
    name         = f"{first_name} {last_name}".strip() or "Unknown"
    company      = record.get("company", "")
    email        = record.get("email", "")
    phone        = record.get("phone", "")
    service      = record.get("service", "")
    message      = record.get("message", "")
    urgency      = record.get("quote_urgency", "")
    quote_number = record.get("quote_number", "")
    addr1        = record.get("site_address_line1", "")
    city         = record.get("site_city", "")
    province     = record.get("site_province", "")
    location     = ", ".join(filter(None, [addr1, city, province]))
    contact_id   = record.get("id", "")
    portal_url   = f"https://gprsurveys.ca/admin/contacts/{contact_id}" if contact_id else "https://gprsurveys.ca/admin/contacts"

    def _row(label, value):
        if not value:
            return ""
        return (
            f"<tr>"
            f"<td style='padding:8px 16px 8px 0;color:#666;font-size:13px;white-space:nowrap;vertical-align:top;'>{label}</td>"
            f"<td style='padding:8px 0;font-size:13px;'>{_esc(value)}</td>"
            f"</tr>"
        )

    rows_html = (
        _row("Quote #", quote_number)
        + _row("Name", name)
        + _row("Company", company)
        + _row("Email", email)
        + _row("Phone", phone)
        + _row("Service", service)
        + _row("Location", location)
        + _row("Quote Urgency", urgency)
    )

    plain_lines = "\n".join(filter(None, [
        f"Quote #: {quote_number}" if quote_number else "",
        f"Name: {name}",
        f"Company: {company}" if company else "",
        f"Email: {email}",
        f"Phone: {phone}" if phone else "",
        f"Service: {service}" if service else "",
        f"Location: {location}" if location else "",
        f"Quote Urgency: {urgency}" if urgency else "",
    ]))

    h_name    = _esc(name)
    h_message = _esc(message)

    subject = f"[NEW CONTACT] {name} — {service or 'gprsurveys.ca'}"
    html = f"""
    <div style="font-family:sans-serif;max-width:600px;">
      <h2 style="margin:0 0 4px;">[NEW CONTACT] {h_name}</h2>
      <p style="color:#666;font-size:13px;margin:0 0 16px;">New contact form submission from gprsurveys.ca</p>
      <table style="border-collapse:collapse;margin-bottom:16px;">{rows_html}</table>
      <p style="font-size:13px;"><strong>Message:</strong><br>{h_message}</p>
      <p style="margin-top:16px;">
        <a href="{portal_url}" style="display:inline-block;background:#111;color:#FFD700;text-decoration:none;font-size:12px;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;padding:10px 20px;border:1px solid #FFD700;">
          View in Admin Portal →
        </a>
      </p>
    </div>
    """
    plain = f"New contact form submission from gprsurveys.ca\n\n{plain_lines}\n\nMessage:\n{message}\n\nView in admin: {portal_url}"
    return subject, html, plain


_QUOTE_SERVICE_LABELS = {
    "locate_single":  "subsurface utility locating services",
    "dual_services":  "subsurface utility locating and deliverable services",
    "full_services":  "subsurface utility locating, topographic survey, and deliverable services",
    "survey_single":  "topographic surveying services",
}


def _quote_email(contact: dict, quote_number: str, template_type: str = "locate_single") -> tuple[str, str, str]:
    first_name  = contact.get("first_name", "")
    site_city   = contact.get("site_city", "")
    address     = contact.get("site_address_line1", "")
    location    = f"{address}, {site_city}" if site_city else address
    service_label = _QUOTE_SERVICE_LABELS.get(template_type, "subsurface investigation services")

    h_first_name  = _esc(first_name)
    h_quote_number = _esc(quote_number)
    h_location    = _esc(location)

    subject = f"Proposal {quote_number} — GPR Surveys Inc."
    html = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto;background:#ffffff;color:#0a0a0a;padding:40px;">
      <div style="border-top:2px solid #1F4E79;padding-top:24px;margin-bottom:32px;">
        <h1 style="font-size:13px;letter-spacing:0.2em;text-transform:uppercase;color:#1F4E79;margin:0 0 4px;">GPR SURVEYS INC.</h1>
      </div>
      <h2 style="font-size:20px;margin:0 0 8px;">Professional Services Proposal</h2>
      <p style="color:#555555;margin-bottom:24px;">
        Dear {h_first_name},<br/><br/>
        Thank you for reaching out to GPR Surveys Inc. Please find attached our proposal
        <strong>{h_quote_number}</strong> for the work at <strong>{h_location}</strong>.
      </p>
      <p style="color:#555555;margin-bottom:24px;">
        This proposal outlines the scope of work, pricing, and terms for the requested {service_label}.
        Please review the attached document and do not hesitate to contact us with any questions.
      </p>
      <p style="color:#555555;margin-bottom:24px;">
        To authorize this proposal, please sign and return the Client Authorization page (Page 5)
        along with a purchase order number.
      </p>
      <p style="color:#555555;margin-bottom:24px;">
        To help us process your invoice, please confirm your billing details:<br/>
        <a href="https://gprsurveys.ca/billing" style="color:#1F4E79;font-weight:600;">Update Billing Info →</a>
      </p>
      <p style="color:#555555;font-size:13px;border-top:1px solid #dddddd;padding-top:20px;margin-top:32px;">
        Louis Gosselin — Managing Partner<br/>
        GPR Surveys Inc.<br/>
        <a href="mailto:LG@gprsurveys.ca" style="color:#1F4E79;">LG@gprsurveys.ca</a> | (250) 896-7576
      </p>
    </div>
    """
    plain = (
        f"Dear {first_name},\n\n"
        f"Please find attached our proposal {quote_number} for work at {location}.\n\n"
        f"Please review and return the signed authorization page along with a PO number.\n\n"
        f"To help us process your invoice, please confirm your billing details:\n"
        f"https://gprsurveys.ca/billing\n\n"
        f"Louis Gosselin — Managing Partner\nGPR Surveys Inc.\nLG@gprsurveys.ca | (250) 896-7576"
    )
    return subject, html, plain


def _stale_contacts_alert(contacts: list) -> tuple[str, str, str]:
    count = len(contacts)
    rows = ""
    plain_rows = ""
    for c in contacts:
        name = f"{c.get('first_name', '')} {c.get('last_name', '')}".strip()
        company = c.get("company", "")
        email = c.get("email", "")
        service = c.get("service", "")
        created = c.get("created_at", "")[:10]
        rows += (
            f"<tr><td style='padding:6px 12px;border-bottom:1px solid #eee;'>{_esc(name)}</td>"
            f"<td style='padding:6px 12px;border-bottom:1px solid #eee;'>{_esc(company)}</td>"
            f"<td style='padding:6px 12px;border-bottom:1px solid #eee;'>{_esc(service)}</td>"
            f"<td style='padding:6px 12px;border-bottom:1px solid #eee;'>{created}</td></tr>"
        )
        plain_rows += f"  • {name} ({company}) — {service} — received {created}\n"

    subject = f"[ACTION REQUIRED] {count} uncontacted lead{'s' if count != 1 else ''} — GPR Surveys"
    html = f"""
    <div style="font-family:sans-serif;max-width:680px;">
      <h2 style="color:#1F4E79;">[STALE CONTACTS] {count} lead{'s' if count != 1 else ''} uncontacted for 48h+</h2>
      <p>The following contact{'s have' if count != 1 else ' has'} not been actioned in over 48 hours:</p>
      <table style="border-collapse:collapse;width:100%;">
        <thead>
          <tr style="background:#1F4E79;color:#fff;">
            <th style="padding:8px 12px;text-align:left;">Name</th>
            <th style="padding:8px 12px;text-align:left;">Company</th>
            <th style="padding:8px 12px;text-align:left;">Service</th>
            <th style="padding:8px 12px;text-align:left;">Received</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>
      <p style="margin-top:20px;">
        <a href="https://gprsurveys.ca/admin/customers" style="background:#1F4E79;color:#fff;padding:10px 20px;text-decoration:none;font-size:12px;font-weight:bold;letter-spacing:0.1em;text-transform:uppercase;">
          View Contacts →
        </a>
      </p>
    </div>
    """
    plain = (
        f"STALE CONTACTS: {count} lead(s) uncontacted for 48h+\n\n"
        f"{plain_rows}\n"
        f"Review at: https://gprsurveys.ca/admin/customers"
    )
    return subject, html, plain


def _google_review_request(booking: dict) -> tuple[str, str, str]:
    job = booking.get("job_number", "")
    customer = booking.get("customers") or {}
    first_name = customer.get("first_name", "")
    review_url = os.environ.get("GOOGLE_REVIEW_URL", "https://gprsurveys.ca")

    h_first_name = _esc(first_name)
    h_job        = _esc(job)

    subject = "How did we do? — GPR Surveys Inc."
    html = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto;background:#ffffff;color:#0a0a0a;padding:40px;">
      <div style="border-top:2px solid #1F4E79;padding-top:24px;margin-bottom:32px;">
        <h1 style="font-size:13px;letter-spacing:0.2em;text-transform:uppercase;color:#1F4E79;margin:0 0 4px;">GPR SURVEYS INC.</h1>
      </div>
      <h2 style="font-size:20px;margin:0 0 8px;">Thank You for Choosing GPR Surveys</h2>
      <p style="color:#555555;margin-bottom:24px;">
        Hi {h_first_name},<br/><br/>
        Thank you for working with us on job <strong>{h_job}</strong>. We hope the survey met your expectations
        and helped support your project safely and efficiently.
      </p>
      <p style="color:#555555;margin-bottom:24px;">
        If you have a moment, we'd really appreciate it if you could share your experience with a
        Google review — it helps other clients find us and means a lot to our small team.
      </p>
      <p style="margin-bottom:32px;">
        <a href="{review_url}" style="display:inline-block;background:#1F4E79;color:#ffffff;text-decoration:none;font-size:12px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;padding:12px 28px;">
          Leave a Google Review
        </a>
      </p>
      <p style="color:#555555;font-size:13px;border-top:1px solid #dddddd;padding-top:20px;margin-top:32px;">
        Louis Gosselin — Managing Partner<br/>
        GPR Surveys Inc.<br/>
        <a href="mailto:LG@gprsurveys.ca" style="color:#1F4E79;">LG@gprsurveys.ca</a> | (250) 896-7576
      </p>
    </div>
    """
    plain = (
        f"Hi {first_name},\n\n"
        f"Thank you for working with us on job {job}. We hope the survey met your expectations.\n\n"
        f"If you have a moment, we'd love a Google review:\n{review_url}\n\n"
        f"Louis Gosselin — Managing Partner\nGPR Surveys Inc.\nLG@gprsurveys.ca | (250) 896-7576"
    )
    return subject, html, plain


def _technician_credentials(payload: dict) -> tuple[str, str, str]:
    name         = payload.get("name", "")
    email        = payload.get("email", "")
    temp_password = payload.get("temp_password", "")
    login_url    = os.environ.get("SITE_URL", "https://gprsurveys.ca") + "/login"

    h_name  = _esc(name)
    h_email = _esc(email)

    subject = "Your GPR Surveys Portal Access"
    html = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto;background:#0a0a0a;color:#fff;padding:40px;">
      <div style="border-top:2px solid #FFD700;padding-top:24px;margin-bottom:32px;">
        <h1 style="font-size:13px;letter-spacing:0.2em;text-transform:uppercase;color:#FFD700;margin:0 0 4px;">GPR SURVEYS</h1>
      </div>
      <h2 style="font-size:22px;margin:0 0 8px;">Welcome, {h_name}</h2>
      <p style="color:#94a3b8;margin-bottom:32px;">Your admin portal account has been created. Use the credentials below to log in.</p>
      <table style="width:100%;border-collapse:collapse;margin-bottom:32px;">
        <tr><td style="padding:10px 0;color:#94a3b8;font-size:13px;border-bottom:1px solid #2a2a2a;">Login URL</td><td style="padding:10px 0;font-size:13px;border-bottom:1px solid #2a2a2a;"><a href="{login_url}" style="color:#FFD700;">{login_url}</a></td></tr>
        <tr><td style="padding:10px 0;color:#94a3b8;font-size:13px;border-bottom:1px solid #2a2a2a;">Email</td><td style="padding:10px 0;font-size:13px;border-bottom:1px solid #2a2a2a;">{h_email}</td></tr>
        <tr><td style="padding:10px 0;color:#94a3b8;font-size:13px;">Temp Password</td><td style="padding:10px 0;font-size:13px;font-weight:600;">{temp_password}</td></tr>
      </table>
      <p style="color:#94a3b8;font-size:13px;">
        Once you're logged in, go to <strong>Settings</strong> in the sidebar to set a new password.
      </p>
      <p style="font-size:12px;color:#3a3a3a;border-top:1px solid #2a2a2a;padding-top:24px;margin-top:24px;">
        If you did not expect this email, contact info@gprsurveys.ca.
      </p>
    </div>
    """
    plain = (
        f"Welcome {name},\n\n"
        f"Your GPR Surveys admin portal account has been created.\n\n"
        f"Login URL: {login_url}\n"
        f"Email: {email}\n"
        f"Temp Password: {temp_password}\n\n"
        f"Once logged in, go to Settings in the sidebar to set a new password.\n\n"
        f"Questions? Contact info@gprsurveys.ca"
    )
    return subject, html, plain


def _technician_assignment(payload: dict) -> tuple[str, str, str]:
    """Notify a technician they have been assigned to a job."""
    booking     = payload.get("booking") or {}
    tech_name   = payload.get("tech_name", "")
    portal_url  = payload.get("portal_url", "https://gprsurveys.ca/admin/job/" + booking.get("job_number", ""))

    job          = booking.get("job_number", "")
    service      = booking.get("service", "")
    date         = _fmt_date(booking.get("date", ""))
    booking_time = booking.get("booking_time", "")[:5]
    address      = f"{booking.get('site_address_line1', '')} {booking.get('site_city', '')} {booking.get('site_province', '')}".strip()
    customer     = booking.get("customers") or {}
    cust_name    = f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip()
    cust_phone   = customer.get("phone", "")
    site_contact = f"{booking.get('site_contact_first_name', '')} {booking.get('site_contact_last_name', '')}".strip()
    site_phone   = booking.get("site_contact_phone", "")
    notes        = booking.get("notes", "") or "—"

    h_tech_name   = _esc(tech_name)
    h_job         = _esc(job)
    h_service     = _esc(service)
    h_address     = _esc(address)
    h_cust_name   = _esc(cust_name)
    h_cust_phone  = _esc(cust_phone)
    h_site_contact = _esc(site_contact)
    h_site_phone  = _esc(site_phone)
    h_notes       = _esc(notes)

    subject = f"[JOB ASSIGNED] {job} — {service}"
    html = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto;background:#0a0a0a;color:#fff;padding:40px;">
      <div style="border-top:2px solid #FFD700;padding-top:24px;margin-bottom:32px;">
        <h1 style="font-size:13px;letter-spacing:0.2em;text-transform:uppercase;color:#FFD700;margin:0 0 4px;">GPR SURVEYS</h1>
      </div>
      <h2 style="font-size:20px;margin:0 0 8px;">Job Assigned — {h_job}</h2>
      <p style="color:#94a3b8;margin-bottom:28px;">Hi {h_tech_name}, you have been assigned to the following job.</p>
      <table style="width:100%;border-collapse:collapse;margin-bottom:28px;">
        <tr><td style="padding:10px 0;color:#94a3b8;font-size:13px;border-bottom:1px solid #1e1e1e;width:38%;">Job Number</td><td style="padding:10px 0;font-size:13px;font-weight:600;border-bottom:1px solid #1e1e1e;">{h_job}</td></tr>
        <tr><td style="padding:10px 0;color:#94a3b8;font-size:13px;border-bottom:1px solid #1e1e1e;">Service</td><td style="padding:10px 0;font-size:13px;border-bottom:1px solid #1e1e1e;">{h_service}</td></tr>
        <tr><td style="padding:10px 0;color:#94a3b8;font-size:13px;border-bottom:1px solid #1e1e1e;">Date</td><td style="padding:10px 0;font-size:13px;border-bottom:1px solid #1e1e1e;">{date}</td></tr>
        <tr><td style="padding:10px 0;color:#94a3b8;font-size:13px;border-bottom:1px solid #1e1e1e;">Time</td><td style="padding:10px 0;font-size:13px;border-bottom:1px solid #1e1e1e;">{booking_time}</td></tr>
        <tr><td style="padding:10px 0;color:#94a3b8;font-size:13px;border-bottom:1px solid #1e1e1e;">Site Address</td><td style="padding:10px 0;font-size:13px;border-bottom:1px solid #1e1e1e;">{h_address}</td></tr>
        <tr><td style="padding:10px 0;color:#94a3b8;font-size:13px;border-bottom:1px solid #1e1e1e;">Customer</td><td style="padding:10px 0;font-size:13px;border-bottom:1px solid #1e1e1e;">{h_cust_name}{(' — ' + h_cust_phone) if h_cust_phone else ''}</td></tr>
        <tr><td style="padding:10px 0;color:#94a3b8;font-size:13px;border-bottom:1px solid #1e1e1e;">Site Contact</td><td style="padding:10px 0;font-size:13px;border-bottom:1px solid #1e1e1e;">{h_site_contact}{(' — ' + h_site_phone) if h_site_phone else ''}</td></tr>
        <tr><td style="padding:10px 0;color:#94a3b8;font-size:13px;">Notes</td><td style="padding:10px 0;font-size:13px;">{h_notes}</td></tr>
      </table>
      <p style="margin-bottom:8px;">
        <a href="{portal_url}" style="display:inline-block;background:#FFD700;color:#0a0a0a;text-decoration:none;font-size:12px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;padding:12px 24px;">
          View Job in Portal
        </a>
      </p>
      <p style="font-size:12px;color:#3a3a3a;border-top:1px solid #1e1e1e;padding-top:24px;margin-top:24px;">
        Questions? Contact info@gprsurveys.ca
      </p>
    </div>
    """
    plain = (
        f"JOB ASSIGNED — {job}\n\n"
        f"Hi {tech_name}, you have been assigned to the following job.\n\n"
        f"Job: {job}\nService: {service}\nDate: {date} at {booking_time}\n"
        f"Site: {address}\nCustomer: {cust_name} {cust_phone}\n"
        f"Site Contact: {site_contact} {site_phone}\nNotes: {notes}\n\n"
        f"View in portal: {portal_url}"
    )
    return subject, html, plain


def _technician_unassignment(payload: dict) -> tuple[str, str, str]:
    """Notify a technician they have been removed from a job."""
    booking    = payload.get("booking") or {}
    tech_name  = payload.get("tech_name", "")
    portal_url = payload.get("portal_url", "https://gprsurveys.ca/admin/job/" + booking.get("job_number", ""))

    job     = booking.get("job_number", "")
    service = booking.get("service", "")
    date    = _fmt_date(booking.get("date", ""))
    time_s  = booking.get("booking_time", "")[:5]
    address = f"{booking.get('site_address_line1', '')} {booking.get('site_city', '')} {booking.get('site_province', '')}".strip()

    h_tech_name = _esc(tech_name)
    h_job       = _esc(job)
    h_service   = _esc(service)
    h_address   = _esc(address)

    subject = f"[JOB UNASSIGNED] {job} — {service}"
    html = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto;background:#0a0a0a;color:#fff;padding:40px;">
      <div style="border-top:2px solid #FFD700;padding-top:24px;margin-bottom:32px;">
        <h1 style="font-size:13px;letter-spacing:0.2em;text-transform:uppercase;color:#FFD700;margin:0 0 4px;">GPR SURVEYS</h1>
      </div>
      <h2 style="font-size:20px;margin:0 0 8px;">Job Unassigned — {h_job}</h2>
      <p style="color:#94a3b8;margin-bottom:28px;">Hi {h_tech_name}, you have been removed from the following job.</p>
      <table style="width:100%;border-collapse:collapse;margin-bottom:28px;">
        <tr><td style="padding:10px 0;color:#94a3b8;font-size:13px;border-bottom:1px solid #1e1e1e;width:38%;">Job Number</td><td style="padding:10px 0;font-size:13px;font-weight:600;border-bottom:1px solid #1e1e1e;">{h_job}</td></tr>
        <tr><td style="padding:10px 0;color:#94a3b8;font-size:13px;border-bottom:1px solid #1e1e1e;">Service</td><td style="padding:10px 0;font-size:13px;border-bottom:1px solid #1e1e1e;">{h_service}</td></tr>
        <tr><td style="padding:10px 0;color:#94a3b8;font-size:13px;border-bottom:1px solid #1e1e1e;">Date</td><td style="padding:10px 0;font-size:13px;border-bottom:1px solid #1e1e1e;">{date}</td></tr>
        <tr><td style="padding:10px 0;color:#94a3b8;font-size:13px;border-bottom:1px solid #1e1e1e;">Time</td><td style="padding:10px 0;font-size:13px;border-bottom:1px solid #1e1e1e;">{time_s}</td></tr>
        <tr><td style="padding:10px 0;color:#94a3b8;font-size:13px;">Site Address</td><td style="padding:10px 0;font-size:13px;">{h_address}</td></tr>
      </table>
      <p style="font-size:13px;color:#94a3b8;">If you believe this was an error, please contact info@gprsurveys.ca.</p>
    </div>
    """
    plain = (
        f"JOB UNASSIGNED — {job}\n\n"
        f"Hi {tech_name}, you have been removed from job {job}.\n\n"
        f"Service: {service}\nDate: {date} at {time_s}\nSite: {address}\n\n"
        f"Questions? Contact info@gprsurveys.ca"
    )
    return subject, html, plain


def _quote_followup(contact: dict, quote_number: str, days_ago: int) -> tuple[str, str, str]:
    first_name = contact.get("first_name", "")
    site_city  = contact.get("site_city", "")

    h_first_name   = _esc(first_name)
    h_quote_number = _esc(quote_number)
    h_site_city    = _esc(site_city)

    subject = f"Following Up — Proposal {quote_number} | GPR Surveys Inc."
    html = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto;background:#ffffff;color:#0a0a0a;padding:40px;">
      <div style="border-top:2px solid #1F4E79;padding-top:24px;margin-bottom:32px;">
        <h1 style="font-size:13px;letter-spacing:0.2em;text-transform:uppercase;color:#1F4E79;margin:0 0 4px;">GPR SURVEYS INC.</h1>
      </div>
      <h2 style="font-size:20px;margin:0 0 8px;">Following Up on Your Proposal</h2>
      <p style="color:#555555;margin-bottom:24px;">
        Dear {h_first_name},<br/><br/>
        I wanted to follow up on proposal <strong>{h_quote_number}</strong> that we sent {days_ago} days ago
        for your project in {h_site_city}. We would love to help and are happy to answer any questions
        you may have about the scope, pricing, or process.
      </p>
      <p style="color:#555555;margin-bottom:24px;">
        If you are still interested, please reply to this email or give us a call. If your project
        plans have changed, no problem at all — just let us know and we will update our records.
      </p>
      <p style="color:#555555;font-size:13px;border-top:1px solid #dddddd;padding-top:20px;margin-top:32px;">
        Louis Gosselin — Managing Partner<br/>
        GPR Surveys Inc.<br/>
        <a href="mailto:LG@gprsurveys.ca" style="color:#1F4E79;">LG@gprsurveys.ca</a> | (250) 896-7576
      </p>
    </div>
    """
    plain = (
        f"Dear {first_name},\n\n"
        f"Following up on proposal {quote_number} sent {days_ago} days ago for your project in {site_city}.\n\n"
        f"Please reply if you have questions or would like to proceed.\n\n"
        f"Louis Gosselin — Managing Partner\nGPR Surveys Inc.\nLG@gprsurveys.ca | (250) 896-7576"
    )
    return subject, html, plain


def _time_off_request(payload: dict) -> tuple[str, str, str]:
    from datetime import datetime
    tech_name  = payload.get("tech_name", "Unknown Technician")
    tech_email = payload.get("tech_email", "")
    dates      = payload.get("dates", [])
    notes      = payload.get("notes", "").strip()

    date_count = len(dates)

    def _fmt(d: str) -> str:
        try:
            return datetime.strptime(d, "%Y-%m-%d").strftime("%a, %b %-d, %Y")
        except Exception:
            return d

    formatted_dates = [_fmt(d) for d in sorted(dates)]
    submitted = datetime.now().strftime("%a, %b %-d, %Y")

    h_tech_name  = _esc(tech_name)
    h_tech_email = _esc(tech_email)
    h_notes      = _esc(notes)

    subject = f"[TIME OFF REQUEST] {tech_name} \u2014 {date_count} day{'s' if date_count != 1 else ''}"

    date_rows = "".join(
        f'<tr><td style="padding:4px 0;color:#333333;">{d}</td></tr>'
        for d in formatted_dates
    )
    notes_block = (
        f'<p style="margin:16px 0 0;"><strong>Notes:</strong></p>'
        f'<p style="color:#555555;font-style:italic;">&ldquo;{h_notes}&rdquo;</p>'
        if notes else ""
    )

    html = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto;background:#ffffff;color:#0a0a0a;padding:40px;">
      <div style="border-top:2px solid #1F4E79;padding-top:24px;margin-bottom:32px;">
        <h1 style="font-size:13px;letter-spacing:0.2em;text-transform:uppercase;color:#1F4E79;margin:0 0 4px;">GPR SURVEYS INC.</h1>
      </div>
      <h2 style="font-size:20px;margin:0 0 8px;">Time Off Request</h2>
      <table style="width:100%;border-collapse:collapse;margin-bottom:24px;">
        <tr><td style="padding:4px 0;color:#888888;width:120px;">Technician</td><td style="padding:4px 0;font-weight:600;">{h_tech_name}</td></tr>
        <tr><td style="padding:4px 0;color:#888888;">Email</td><td style="padding:4px 0;">{h_tech_email}</td></tr>
        <tr><td style="padding:4px 0;color:#888888;">Submitted</td><td style="padding:4px 0;">{submitted}</td></tr>
      </table>
      <p style="margin:0 0 8px;font-weight:600;">Requested Days Off ({date_count}):</p>
      <table style="border-collapse:collapse;margin-bottom:8px;">
        {date_rows}
      </table>
      {notes_block}
    </div>
    """

    date_list = "\n".join(f"  - {d}" for d in formatted_dates)
    plain = (
        f"TIME OFF REQUEST\n\n"
        f"Technician: {tech_name}\n"
        f"Email:      {tech_email}\n"
        f"Submitted:  {submitted}\n\n"
        f"Requested Days Off ({date_count}):\n{date_list}\n"
        + (f"\nNotes: {notes}" if notes else "")
    )
    return subject, html, plain


def _time_off_approval(payload: dict) -> tuple[str, str, str]:
    """
    Notify the technician that their time-off request has been approved.
    Payload: { tech_name, tech_email, start_date, end_date, dates: list[str] }
    Recipient: tech_email directly.
    """
    from datetime import datetime
    tech_name = payload.get("tech_name", "Technician")
    dates     = payload.get("dates", [])

    def _fmt(d: str) -> str:
        try:
            return datetime.strptime(d, "%Y-%m-%d").strftime("%a, %b %-d, %Y")
        except Exception:
            return d

    date_count      = len(dates)
    formatted_dates = [_fmt(d) for d in sorted(dates)]

    h_tech_name = _esc(tech_name)

    subject = f"[TIME OFF APPROVED] Your request has been approved — {date_count} day{'s' if date_count != 1 else ''}"

    date_rows = "".join(
        f'<tr><td style="padding:8px 0;color:#e2e8f0;font-size:13px;border-bottom:1px solid #2a2a2a;">{d}</td></tr>'
        for d in formatted_dates
    )

    html = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto;background:#0a0a0a;color:#fff;padding:40px;">
      <div style="border-top:2px solid #FFD700;padding-top:24px;margin-bottom:32px;">
        <h1 style="font-size:13px;letter-spacing:0.2em;text-transform:uppercase;color:#FFD700;margin:0 0 4px;">GPR SURVEYS — SCHEDULE UPDATE</h1>
      </div>
      <h2 style="font-size:22px;margin:0 0 8px;">Time Off Approved</h2>
      <p style="color:#94a3b8;margin-bottom:32px;">Hi {h_tech_name}, your time-off request has been approved for the following {date_count} day{'s' if date_count != 1 else ''}:</p>
      <table style="width:100%;border-collapse:collapse;margin-bottom:32px;">
        {date_rows}
      </table>
      <p style="font-size:12px;color:#3a3a3a;border-top:1px solid #2a2a2a;padding-top:24px;">
        This is an automated notification from GPR Surveys admin.
      </p>
    </div>
    """

    date_list = "\n".join(f"  - {d}" for d in formatted_dates)
    plain = (
        f"TIME OFF APPROVED\n\n"
        f"Hi {tech_name}, your time-off request has been approved.\n\n"
        f"Approved Days ({date_count}):\n{date_list}\n"
    )
    return subject, html, plain


def _tech_date_change(payload: dict) -> tuple[str, str, str]:
    """Notify the assigned technician that one of their jobs has been rescheduled."""
    booking     = payload.get("booking") or {}
    job_number  = booking.get("job_number", "")
    old_date    = _fmt_date(payload.get("old_date", ""))
    new_date    = _fmt_date(booking.get("date", ""))
    service     = booking.get("service", "")
    address     = f"{booking.get('site_address_line1', '')} {booking.get('site_city', '')} {booking.get('site_province', '')}".strip()

    h_job_number = _esc(job_number)
    h_service    = _esc(service)
    h_old_date   = _esc(old_date)
    h_new_date   = _esc(new_date)
    h_address    = _esc(address)

    subject = f"[JOB MOVED] {job_number} rescheduled to {new_date}"
    html = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto;background:#0a0a0a;color:#fff;padding:40px;">
      <div style="border-top:2px solid #FFD700;padding-top:24px;margin-bottom:32px;">
        <h1 style="font-size:13px;letter-spacing:0.2em;text-transform:uppercase;color:#FFD700;margin:0 0 4px;">GPR SURVEYS — TECH UPDATE</h1>
      </div>
      <h2 style="font-size:22px;margin:0 0 8px;">[JOB MOVED] {h_job_number}</h2>
      <p style="color:#94a3b8;margin-bottom:32px;">One of your assigned jobs has been rescheduled by the admin.</p>
      <table style="width:100%;border-collapse:collapse;margin-bottom:32px;">
        <tr><td style="padding:10px 0;color:#94a3b8;font-size:13px;border-bottom:1px solid #2a2a2a;">Job Number</td><td style="padding:10px 0;font-size:13px;font-weight:600;border-bottom:1px solid #2a2a2a;">{h_job_number}</td></tr>
        <tr><td style="padding:10px 0;color:#94a3b8;font-size:13px;border-bottom:1px solid #2a2a2a;">Service</td><td style="padding:10px 0;font-size:13px;border-bottom:1px solid #2a2a2a;">{h_service}</td></tr>
        <tr><td style="padding:10px 0;color:#94a3b8;font-size:13px;border-bottom:1px solid #2a2a2a;">Old Date</td><td style="padding:10px 0;font-size:13px;border-bottom:1px solid #2a2a2a;text-decoration:line-through;color:#94a3b8;">{h_old_date}</td></tr>
        <tr><td style="padding:10px 0;color:#FFD700;font-size:13px;font-weight:700;border-bottom:1px solid #2a2a2a;">New Date</td><td style="padding:10px 0;font-size:13px;font-weight:700;color:#FFD700;border-bottom:1px solid #2a2a2a;">{h_new_date}</td></tr>
        <tr><td style="padding:10px 0;color:#94a3b8;font-size:13px;">Site</td><td style="padding:10px 0;font-size:13px;">{h_address}</td></tr>
      </table>
      <p style="font-size:12px;color:#3a3a3a;border-top:1px solid #2a2a2a;padding-top:24px;">
        This is an automated notification. Please check the admin portal for full job details.
      </p>
    </div>
    """
    plain = (
        f"[JOB MOVED] {job_number}\n\n"
        f"Service:  {service}\n"
        f"Old Date: {old_date}\n"
        f"New Date: {new_date}\n"
        f"Site:     {address}\n\n"
        f"Please check the admin portal for full job details."
    )
    return subject, html, plain


def _billing_notification(payload: dict) -> tuple[str, str, str]:
    """Admin notification when a customer submits their billing info via the public billing page."""
    first_name = payload.get("first_name", "")
    last_name  = payload.get("last_name", "")
    email      = payload.get("email", "")
    phone      = payload.get("phone", "") or ""
    company    = payload.get("company", "") or ""

    billing_email    = payload.get("billing_email", "") or ""
    address_line1    = payload.get("billing_address_line1", "") or ""
    address_line2    = payload.get("billing_address_line2", "") or ""
    city             = payload.get("billing_city", "") or ""
    province         = payload.get("billing_province", "") or ""
    postal_code      = payload.get("billing_postal_code", "") or ""

    full_name = f"{first_name} {last_name}".strip() or email

    subject = f"[BILLING INFO] {full_name} submitted billing details"

    def _row(label: str, value: str) -> str:
        if not value:
            return ""
        return f'<tr><td style="padding:4px 0;color:#888888;width:140px;">{label}</td><td style="padding:4px 0;">{_esc(value)}</td></tr>'

    address_parts = [p for p in [address_line1, address_line2, city, province, postal_code] if p]
    address_display = ", ".join(address_parts)

    contact_rows = "".join([
        _row("Name", full_name),
        _row("Email", email),
        _row("Phone", phone),
        _row("Company", company),
    ])
    billing_rows = "".join([
        _row("Billing Email", billing_email),
        _row("Address", address_display),
    ])

    html = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto;background:#ffffff;color:#0a0a0a;padding:40px;">
      <div style="border-top:2px solid #1F4E79;padding-top:24px;margin-bottom:32px;">
        <h1 style="font-size:13px;letter-spacing:0.2em;text-transform:uppercase;color:#1F4E79;margin:0 0 4px;">GPR SURVEYS INC.</h1>
      </div>
      <h2 style="font-size:20px;margin:0 0 8px;">New Billing Submission</h2>
      <p style="color:#555555;margin:0 0 24px;">A customer submitted their billing information via the website.</p>
      <p style="margin:0 0 8px;font-weight:600;">Contact</p>
      <table style="width:100%;border-collapse:collapse;margin-bottom:24px;">{contact_rows}</table>
      <p style="margin:0 0 8px;font-weight:600;">Billing Details</p>
      <table style="width:100%;border-collapse:collapse;margin-bottom:24px;">{billing_rows}</table>
    </div>
    """

    plain_lines = [
        "NEW BILLING SUBMISSION\n",
        f"Name:    {full_name}",
        f"Email:   {email}",
    ]
    if phone:    plain_lines.append(f"Phone:   {phone}")
    if company:  plain_lines.append(f"Company: {company}")
    plain_lines.append("")
    if billing_email:  plain_lines.append(f"Billing Email: {billing_email}")
    if address_display: plain_lines.append(f"Address:       {address_display}")
    plain = "\n".join(plain_lines)

    return subject, html, plain


def _new_application(payload: dict) -> tuple[str, str, str]:
    """Admin notification when a new job application is received."""
    first_name   = payload.get("first_name", "")
    last_name    = payload.get("last_name", "")
    candidate_email = payload.get("email", "") or payload.get("candidate_email", "")
    phone        = payload.get("phone", "") or ""
    job_title    = payload.get("job_title", "the position")
    ai_score     = payload.get("ai_score")
    resume_url   = payload.get("resume_url", "")
    application_id = payload.get("application_id", "") or payload.get("id", "")

    full_name    = f"{first_name} {last_name}".strip() or "Unknown Candidate"
    portal_url   = (
        f"https://gprsurveys.ca/admin/careers/{application_id}"
        if application_id else "https://gprsurveys.ca/admin/recruiting"
    )

    score_display = f"{ai_score}/10" if ai_score is not None else "Pending"
    ai_score_summary = payload.get("ai_score_summary", "")
    recommendation   = payload.get("recommendation", "")

    def _row(label: str, value: str) -> str:
        if not value:
            return ""
        return (
            f"<tr>"
            f"<td style='padding:6px 0;color:#888888;font-size:13px;width:140px;'>{label}</td>"
            f"<td style='padding:6px 0;font-size:13px;'>{_esc(value)}</td>"
            f"</tr>"
        )

    rows_html = (
        _row("Candidate", full_name)
        + _row("Email", candidate_email)
        + _row("Phone", phone)
        + _row("Position", job_title)
        + _row("AI Score", score_display)
        + _row("Recommendation", recommendation)
    )

    resume_link = (
        f'<p style="margin-top:16px;"><a href="{resume_url}" style="color:#1F4E79;font-weight:600;">View Resume →</a></p>'
        if resume_url else ""
    )
    ai_block = (
        f'<p style="margin-top:16px;"><strong>AI Summary:</strong><br><span style="color:#555555;">{_esc(ai_score_summary)}</span></p>'
        if ai_score_summary else ""
    )

    subject = f"[NEW APPLICATION] {full_name} — {job_title}"
    html = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto;background:#ffffff;color:#0a0a0a;padding:40px;">
      <div style="border-top:2px solid #1F4E79;padding-top:24px;margin-bottom:32px;">
        <h1 style="font-size:13px;letter-spacing:0.2em;text-transform:uppercase;color:#1F4E79;margin:0 0 4px;">GPR SURVEYS INC. — RECRUITING</h1>
      </div>
      <h2 style="font-size:20px;margin:0 0 8px;">New Application Received</h2>
      <p style="color:#555555;margin:0 0 24px;">A new application has been submitted for <strong>{_esc(job_title)}</strong>.</p>
      <table style="width:100%;border-collapse:collapse;margin-bottom:16px;">{rows_html}</table>
      {ai_block}
      {resume_link}
      <p style="margin-top:24px;">
        <a href="{portal_url}" style="display:inline-block;background:#1F4E79;color:#ffffff;text-decoration:none;font-size:12px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;padding:12px 24px;">
          Review Application
        </a>
      </p>
    </div>
    """
    plain_lines = [
        f"NEW APPLICATION: {full_name} — {job_title}\n",
        f"Candidate: {full_name}",
        f"Email:     {candidate_email}",
    ]
    if phone:              plain_lines.append(f"Phone:     {phone}")
    plain_lines.append(f"Position:  {job_title}")
    plain_lines.append(f"AI Score:  {score_display}")
    if recommendation:     plain_lines.append(f"AI Recommendation: {recommendation}")
    if ai_score_summary:   plain_lines.append(f"\nAI Summary: {ai_score_summary}")
    if resume_url:         plain_lines.append(f"\nResume: {resume_url}")
    plain_lines.append(f"\nReview in admin: {portal_url}")
    plain = "\n".join(plain_lines)

    return subject, html, plain


def _application_received(payload: dict) -> tuple[str, str, str]:
    """Acknowledgment email sent to the candidate after they apply."""
    first_name = payload.get("first_name", "")
    job_title  = payload.get("job_title", "the position")

    h_first_name = _esc(first_name)
    h_job_title  = _esc(job_title)

    subject = f"We received your application — {job_title}"
    html = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto;background:#ffffff;color:#0a0a0a;padding:40px;">
      <div style="border-top:2px solid #1F4E79;padding-top:24px;margin-bottom:32px;">
        <h1 style="font-size:13px;letter-spacing:0.2em;text-transform:uppercase;color:#1F4E79;margin:0 0 4px;">GPR SURVEYS INC.</h1>
      </div>
      <h2 style="font-size:20px;margin:0 0 8px;">Application Received</h2>
      <p style="color:#555555;margin-bottom:24px;">
        Dear {h_first_name},<br/><br/>
        Thank you for applying for the <strong>{h_job_title}</strong> position at GPR Surveys Inc.
        We have received your application and our team will review it shortly.
      </p>
      <p style="color:#555555;margin-bottom:24px;">
        If your qualifications are a match, we will reach out within the next few business days
        to discuss next steps. We appreciate your interest in joining our team.
      </p>
      <p style="color:#555555;font-size:13px;border-top:1px solid #dddddd;padding-top:20px;margin-top:32px;">
        GPR Surveys Inc.<br/>
        <a href="mailto:info@gprsurveys.ca" style="color:#1F4E79;">info@gprsurveys.ca</a>
      </p>
    </div>
    """
    plain = (
        f"Dear {first_name},\n\n"
        f"Thank you for applying for the {job_title} position at GPR Surveys Inc. "
        f"We have received your application and our team will review it shortly.\n\n"
        f"If your qualifications are a match, we will reach out within the next few business days "
        f"to discuss next steps. We appreciate your interest in joining our team.\n\n"
        f"GPR Surveys Inc.\ninfo@gprsurveys.ca"
    )
    return subject, html, plain


def _interview_scheduled(payload: dict) -> tuple[str, str, str]:
    """Confirmation email sent to the candidate when an interview is scheduled."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    first_name       = payload.get("candidate_first_name", "") or payload.get("first_name", "")
    job_title        = payload.get("job_title", "the position")
    scheduled_at     = payload.get("scheduled_at", "")
    duration_minutes = int(payload.get("duration_minutes") or 60)
    location_or_link = payload.get("location_or_link", "") or payload.get("meet_link", "")
    notes            = payload.get("notes", "")

    # Format the date/time in Pacific time
    interview_datetime = "TBD"
    if scheduled_at:
        try:
            dt = datetime.fromisoformat(scheduled_at.replace("Z", "+00:00"))
            dt_pacific = dt.astimezone(ZoneInfo("America/Vancouver"))
            interview_datetime = dt_pacific.strftime("%A, %B %-d, %Y at %-I:%M %p %Z")
        except Exception:
            interview_datetime = scheduled_at

    def _row(label: str, value: str) -> str:
        if not value:
            return ""
        return (
            f"<tr>"
            f"<td style='padding:8px 0;color:#888888;font-size:13px;width:140px;border-bottom:1px solid #f0f0f0;'>{label}</td>"
            f"<td style='padding:8px 0;font-size:13px;border-bottom:1px solid #f0f0f0;'>{_esc(value)}</td>"
            f"</tr>"
        )

    rows_html = (
        _row("Position", job_title)
        + _row("Date & Time", interview_datetime)
        + _row("Duration", f"{duration_minutes} minutes")
        + _row("Location / Link", location_or_link)
    )

    notes_block = (
        f'<p style="margin-top:16px;color:#555555;"><strong>Additional Notes:</strong><br>{_esc(notes)}</p>'
        if notes else ""
    )

    h_first_name = _esc(first_name)
    h_job_title  = _esc(job_title)

    subject = f"Interview Scheduled — {job_title} at GPR Surveys"
    html = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto;background:#ffffff;color:#0a0a0a;padding:40px;">
      <div style="border-top:2px solid #1F4E79;padding-top:24px;margin-bottom:32px;">
        <h1 style="font-size:13px;letter-spacing:0.2em;text-transform:uppercase;color:#1F4E79;margin:0 0 4px;">GPR SURVEYS INC.</h1>
      </div>
      <h2 style="font-size:20px;margin:0 0 8px;">Your Interview is Confirmed</h2>
      <p style="color:#555555;margin-bottom:24px;">
        Dear {h_first_name},<br/><br/>
        We are pleased to invite you to interview for the <strong>{h_job_title}</strong> position
        at GPR Surveys Inc. Please find the details below.
      </p>
      <table style="width:100%;border-collapse:collapse;margin-bottom:24px;">{rows_html}</table>
      {notes_block}
      <p style="color:#555555;margin-top:24px;margin-bottom:24px;">
        Please come prepared to discuss your relevant experience and ask any questions you may have.
        If you need to reschedule or have any questions beforehand, please reply to this email.
      </p>
      <p style="color:#555555;font-size:13px;border-top:1px solid #dddddd;padding-top:20px;margin-top:32px;">
        GPR Surveys Inc.<br/>
        <a href="mailto:info@gprsurveys.ca" style="color:#1F4E79;">info@gprsurveys.ca</a>
      </p>
    </div>
    """
    plain_lines = [
        f"Dear {first_name},\n",
        f"Your interview for the {job_title} position at GPR Surveys Inc. has been confirmed.\n",
        f"Date & Time: {interview_datetime}",
        f"Duration:    {duration_minutes} minutes",
    ]
    if location_or_link:  plain_lines.append(f"Location:    {location_or_link}")
    if notes:             plain_lines.append(f"\nNotes: {notes}")
    plain_lines.append(
        "\nPlease come prepared to discuss your experience. "
        "Reply to this email if you need to reschedule.\n\n"
        "GPR Surveys Inc.\ninfo@gprsurveys.ca"
    )
    plain = "\n".join(plain_lines)

    return subject, html, plain


def _application_rejected(payload: dict) -> tuple[str, str, str]:
    """Polite rejection email sent to the candidate."""
    first_name = payload.get("candidate_first_name", "") or payload.get("first_name", "")
    job_title  = payload.get("job_title", "the position")

    h_first_name = _esc(first_name)
    h_job_title  = _esc(job_title)

    subject = f"Your Application — {job_title}"
    html = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto;background:#ffffff;color:#0a0a0a;padding:40px;">
      <div style="border-top:2px solid #1F4E79;padding-top:24px;margin-bottom:32px;">
        <h1 style="font-size:13px;letter-spacing:0.2em;text-transform:uppercase;color:#1F4E79;margin:0 0 4px;">GPR SURVEYS INC.</h1>
      </div>
      <h2 style="font-size:20px;margin:0 0 8px;">Thank You for Applying</h2>
      <p style="color:#555555;margin-bottom:24px;">
        Dear {h_first_name},<br/><br/>
        Thank you for taking the time to apply for the <strong>{h_job_title}</strong> position
        at GPR Surveys Inc. We appreciate your interest in our company.
      </p>
      <p style="color:#555555;margin-bottom:24px;">
        After careful consideration, we have decided to move forward with other candidates
        whose experience more closely matches our current needs. This was a competitive process
        and we encourage you to apply for future openings that align with your background.
      </p>
      <p style="color:#555555;margin-bottom:24px;">
        We wish you the best in your job search and career endeavours.
      </p>
      <p style="color:#555555;font-size:13px;border-top:1px solid #dddddd;padding-top:20px;margin-top:32px;">
        GPR Surveys Inc.<br/>
        <a href="mailto:info@gprsurveys.ca" style="color:#1F4E79;">info@gprsurveys.ca</a>
      </p>
    </div>
    """
    plain = (
        f"Dear {first_name},\n\n"
        f"Thank you for applying for the {job_title} position at GPR Surveys Inc. "
        f"We appreciate your interest in our company.\n\n"
        f"After careful consideration, we have decided to move forward with other candidates "
        f"whose experience more closely matches our current needs. "
        f"We encourage you to apply for future openings that align with your background.\n\n"
        f"We wish you the best in your job search and career endeavours.\n\n"
        f"GPR Surveys Inc.\ninfo@gprsurveys.ca"
    )
    return subject, html, plain


TEMPLATES = {
    "booking_received":         _booking_received,
    "customer_confirmation":    _customer_confirmation,
    "customer_modification":    _customer_modification,
    "customer_cancellation":    _customer_cancellation,
    "internal_notification":    _internal_notification,
    "internal_modification":    _internal_modification,
    "internal_cancellation":    _internal_cancellation,
    "booking_reminder":         _booking_reminder,
    "contact_notification":     _contact_notification,
    "quote_email":              _quote_email,
    "stale_contacts_alert":     _stale_contacts_alert,
    "quote_followup":           _quote_followup,
    "google_review_request":    _google_review_request,
    "technician_credentials":   _technician_credentials,
    "technician_assignment":    _technician_assignment,
    "technician_unassignment":  _technician_unassignment,
    "tech_date_change":         _tech_date_change,
    "time_off_request":         _time_off_request,
    "time_off_approval":        _time_off_approval,
    "billing_notification":     _billing_notification,
    "new_application":          _new_application,
    "application_received":     _application_received,
    "interview_scheduled":      _interview_scheduled,
    "application_rejected":     _application_rejected,
}

# Templates that receive the full payload (not just booking) because they need extra state
_FULL_PAYLOAD_TEMPLATES = {"internal_modification", "customer_modification"}

# Templates that use record (not booking) as their data source
_RECORD_TEMPLATES = {"contact_notification"}

# Templates that operate on contacts (not bookings)
_CONTACT_TEMPLATES = {"quote_email", "quote_followup"}

# Internal contact-related templates (no booking, no contact recipient)
_INTERNAL_CONTACT_TEMPLATES = {"stale_contacts_alert", "time_off_request", "billing_notification", "new_application"}

# Recruiting candidate-facing templates (send to payload["email"] or payload["candidate_email"])
_RECRUITING_CANDIDATE_TEMPLATES = {"application_received", "interview_scheduled", "application_rejected"}

# Templates that receive the full payload and send to payload["email"] or payload["tech_email"]
_DIRECT_PAYLOAD_TEMPLATES = {"technician_credentials"}

# Templates that receive the full payload and send to payload["tech_email"]
_TECH_NOTIFICATION_TEMPLATES = {"technician_assignment", "technician_unassignment", "tech_date_change", "time_off_approval"}


def run(payload: dict) -> dict:
    booking  = payload.get("booking")
    template = payload.get("template", "customer_confirmation")

    if template not in TEMPLATES:
        raise ValueError(f"send_email: unknown template '{template}'")

    # Conditional skips — keep workflow steps unconditional; skip logic lives here
    if template == "booking_received" and (payload.get("booking") or {}).get("source") == "admin":
        logger.info("[send_email] Skipping booking_received — admin-created booking")
        return {"customer_email_skipped": True}

    if template == "customer_modification" and payload.get("skip_customer_email"):
        logger.info("[send_email] Skipping customer_modification — skip_customer_email=True")
        return {"customer_email_skipped": True}

    if template == "tech_date_change" and not payload.get("tech_email"):
        logger.info("[send_email] Skipping tech_date_change — no tech_email in payload")
        return {"tech_email_skipped": True}

    # Require booking for booking templates only
    if template not in _RECORD_TEMPLATES and template not in _CONTACT_TEMPLATES and template not in _INTERNAL_CONTACT_TEMPLATES and template not in _DIRECT_PAYLOAD_TEMPLATES and template not in _TECH_NOTIFICATION_TEMPLATES and template not in _RECRUITING_CANDIDATE_TEMPLATES and not booking:
        raise ValueError("send_email: booking required")

    service = _get_service()

    # ── Build subject/html/plain ──────────────────────────────────────────────
    if template in _TECH_NOTIFICATION_TEMPLATES:
        subject, html, plain = TEMPLATES[template](payload)

    elif template in _FULL_PAYLOAD_TEMPLATES:
        subject, html, plain = TEMPLATES[template](payload)

    elif template in _RECORD_TEMPLATES:
        subject, html, plain = TEMPLATES[template](payload.get("record", {}))

    elif template == "quote_email":
        contact       = payload.get("contact", {})
        quote_number  = contact.get("quote_number") or payload.get("quote_number", "Q00001")
        template_type = payload.get("template_type") or payload.get("quote_data", {}).get("template_type", "locate_single")
        subject, html, plain = TEMPLATES[template](contact, quote_number, template_type)

    elif template == "quote_followup":
        contact      = payload.get("contact", {})
        quote_number = contact.get("quote_number") or payload.get("quote_number", "Q00001")
        days_ago     = payload.get("days_ago", 30)
        subject, html, plain = TEMPLATES[template](contact, quote_number, days_ago)

    elif template == "stale_contacts_alert":
        contacts = payload.get("contacts", [])
        subject, html, plain = TEMPLATES[template](contacts)

    elif template in ("time_off_request", "time_off_approval", "billing_notification", "new_application"):
        subject, html, plain = TEMPLATES[template](payload)

    elif template in _RECRUITING_CANDIDATE_TEMPLATES:
        subject, html, plain = TEMPLATES[template](payload)

    elif template in _DIRECT_PAYLOAD_TEMPLATES:
        subject, html, plain = TEMPLATES[template](payload)

    else:
        subject, html, plain = TEMPLATES[template](booking)

    # ── Determine recipient ───────────────────────────────────────────────────
    _internal_templates = (
        "internal_notification", "internal_modification",
        "internal_cancellation", "contact_notification",
        "stale_contacts_alert", "time_off_request", "billing_notification",
        "new_application",
    )
    if template in _TECH_NOTIFICATION_TEMPLATES:
        to = payload.get("tech_email", "")
    elif template in _DIRECT_PAYLOAD_TEMPLATES:
        to = payload.get("email", "")
    elif template in _RECRUITING_CANDIDATE_TEMPLATES:
        to = payload.get("candidate_email", "") or payload.get("email", "")
    elif template in _internal_templates:
        to = settings.gmail_internal_recipient
    elif template in _CONTACT_TEMPLATES:
        contact = payload.get("contact", {})
        to = contact.get("email", "")
    else:
        customer = booking.get("customers") or {}
        to = customer.get("email") or booking.get("billing_email") or ""

    if not to:
        raise ValueError("send_email: no recipient email found")

    # ── Build attachment if present ───────────────────────────────────────────
    attachment = None
    pdf_bytes_b64 = payload.get("pdf_bytes")
    pdf_filename  = payload.get("pdf_filename")
    if pdf_bytes_b64 and pdf_filename:
        import base64 as _b64
        attachment = {
            "filename":      pdf_filename,
            "content_bytes": _b64.b64decode(pdf_bytes_b64),
            "mime_type":     "application/pdf",
        }

    msg_id = _send(service, to, subject, html, plain, attachment=attachment)
    result = {f"email_{template}_id": msg_id}

    # For cancellations, also notify the assigned technician directly
    if template == "internal_cancellation":
        tech = booking.get("technicians") or {}
        tech_email = tech.get("email")
        if tech_email and tech_email != to:
            tech_msg_id = _send(service, tech_email, subject, html, plain)
            result[f"email_{template}_tech_id"] = tech_msg_id

    return result


if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv
    load_dotenv()
    payload = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {
        "booking": {
            "job_number": "TEST-001",
            "service": "Concrete Scanning",
            "date": "2026-04-01",
            "booking_time": "09:00:00",
            "site_city": "Edmonton",
            "site_address_line1": "123 Test St",
            "site_province": "AB",
            "site_contact_first_name": "Test",
            "site_contact_last_name": "Contact",
            "site_contact_phone": "780-555-0100",
            "notes": "Standalone test",
            "customers": {"first_name": "Test", "last_name": "Customer", "email": "info@gprsurveys.ca"},
        },
        "template": "internal_notification",
    }
    print(json.dumps(run(payload), indent=2))
