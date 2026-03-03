"""
Send email via Gmail API.
Supports templates: customer_confirmation, internal_notification, customer_cancellation,
                    customer_modification, booking_reminder, contact_notification
"""

import base64
import json
import os
import time
import jwt
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
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


def _send(service, to: str, subject: str, html: str, plain: str) -> str:
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


def _customer_confirmation(booking: dict) -> tuple[str, str, str]:
    job = booking.get("job_number", "")
    service = booking.get("service", "")
    date = _fmt_date(booking.get("date", ""))
    booking_time = booking.get("booking_time", "")[:5]
    city = booking.get("site_city", "")
    customer = booking.get("customers") or {}
    first_name = customer.get("first_name", "")
    customer_email = customer.get("email", "")

    modify_token = _generate_modify_token(job, customer_email) if job and customer_email else ""
    modify_url = f"https://gprsurveys.ca/modify?token={modify_token}" if modify_token else "https://gprsurveys.ca/modify"

    subject = f"Booking Confirmed — {job} | GPR Surveys"
    html = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto;background:#0a0a0a;color:#fff;padding:40px;">
      <div style="border-top:2px solid #FFD700;padding-top:24px;margin-bottom:32px;">
        <h1 style="font-size:13px;letter-spacing:0.2em;text-transform:uppercase;color:#FFD700;margin:0 0 4px;">GPR SURVEYS</h1>
      </div>
      <h2 style="font-size:22px;margin:0 0 8px;">Booking Confirmed</h2>
      <p style="color:#94a3b8;margin-bottom:32px;">Hi {first_name}, your GPR survey has been confirmed.</p>
      <table style="width:100%;border-collapse:collapse;margin-bottom:32px;">
        <tr><td style="padding:10px 0;color:#94a3b8;font-size:13px;border-bottom:1px solid #2a2a2a;">Job Number</td><td style="padding:10px 0;font-size:13px;font-weight:600;border-bottom:1px solid #2a2a2a;">{job}</td></tr>
        <tr><td style="padding:10px 0;color:#94a3b8;font-size:13px;border-bottom:1px solid #2a2a2a;">Service</td><td style="padding:10px 0;font-size:13px;border-bottom:1px solid #2a2a2a;">{service}</td></tr>
        <tr><td style="padding:10px 0;color:#94a3b8;font-size:13px;border-bottom:1px solid #2a2a2a;">Date</td><td style="padding:10px 0;font-size:13px;border-bottom:1px solid #2a2a2a;">{date}</td></tr>
        <tr><td style="padding:10px 0;color:#94a3b8;font-size:13px;border-bottom:1px solid #2a2a2a;">Time</td><td style="padding:10px 0;font-size:13px;border-bottom:1px solid #2a2a2a;">{booking_time}</td></tr>
        <tr><td style="padding:10px 0;color:#94a3b8;font-size:13px;">Location</td><td style="padding:10px 0;font-size:13px;">{city}</td></tr>
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
    plain = f"Booking Confirmed — {job}\nService: {service}\nDate: {date} at {booking_time}\nLocation: {city}\n\nModify your booking: {modify_url}"
    return subject, html, plain


def _internal_notification(booking: dict) -> tuple[str, str, str]:
    job = booking.get("job_number", "")
    service = booking.get("service", "")
    date = _fmt_date(booking.get("date", ""))
    time = booking.get("booking_time", "")[:5]
    address = f"{booking.get('site_address_line1', '')} {booking.get('site_city', '')} {booking.get('site_province', '')}"
    customer = booking.get("customers") or {}
    customer_name = f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip()

    subject = f"[NEW BOOKING] {job} — {service} — {booking.get('site_city', '')}"
    html = f"""
    <div style="font-family:sans-serif;max-width:600px;">
      <h2>[NEW BOOKING] {job}</h2>
      <p><strong>Service:</strong> {service}<br>
      <strong>Date:</strong> {date} at {time}<br>
      <strong>Site:</strong> {address}<br>
      <strong>Customer:</strong> {customer_name} — {customer.get('email', '')}<br>
      <strong>Site Contact:</strong> {booking.get('site_contact_first_name', '')} {booking.get('site_contact_last_name', '')} {booking.get('site_contact_phone', '')}</p>
      <p><strong>Notes:</strong> {booking.get('notes', '—')}</p>
    </div>
    """
    plain = f"NEW BOOKING: {job}\nService: {service}\nDate: {date} at {time}\nSite: {address}\nCustomer: {customer_name}"
    return subject, html, plain


def _booking_reminder(booking: dict) -> tuple[str, str, str]:
    job = booking.get("job_number", "")
    date = _fmt_date(booking.get("date", ""))
    time = booking.get("booking_time", "")[:5]
    customer = booking.get("customers") or {}
    first_name = customer.get("first_name", "")

    subject = f"Reminder: Your GPR Survey is Tomorrow — {job}"
    html = f"""
    <div style="font-family:sans-serif;max-width:600px;background:#0a0a0a;color:#fff;padding:40px;">
      <h2>Survey Reminder</h2>
      <p>Hi {first_name}, this is a reminder that your GPR survey is scheduled for tomorrow.</p>
      <p><strong>Job:</strong> {job}<br><strong>Date:</strong> {date} at {time}</p>
      <p style="color:#94a3b8;font-size:12px;">Questions? Reply to this email or call 1-800-555-0199.</p>
    </div>
    """
    plain = f"Reminder: GPR Survey {job} is tomorrow, {date} at {time}."
    return subject, html, plain


def _customer_modification(booking: dict) -> tuple[str, str, str]:
    job = booking.get("job_number", "")
    service = booking.get("service", "")
    date = _fmt_date(booking.get("date", ""))
    booking_time = booking.get("booking_time", "")[:5]
    city = booking.get("site_city", "")
    customer = booking.get("customers") or {}
    first_name = customer.get("first_name", "")
    customer_email = customer.get("email", "")

    modify_token = _generate_modify_token(job, customer_email) if job and customer_email else ""
    modify_url = f"https://gprsurveys.ca/modify?token={modify_token}" if modify_token else "https://gprsurveys.ca/modify"

    subject = f"Booking Updated — {job} | GPR Surveys"
    html = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto;background:#0a0a0a;color:#fff;padding:40px;">
      <div style="border-top:2px solid #FFD700;padding-top:24px;margin-bottom:32px;">
        <h1 style="font-size:13px;letter-spacing:0.2em;text-transform:uppercase;color:#FFD700;margin:0 0 4px;">GPR SURVEYS</h1>
      </div>
      <h2 style="font-size:22px;margin:0 0 8px;">Booking Updated</h2>
      <p style="color:#94a3b8;margin-bottom:32px;">Hi {first_name}, your booking has been updated. Here are the current details:</p>
      <table style="width:100%;border-collapse:collapse;margin-bottom:32px;">
        <tr><td style="padding:10px 0;color:#94a3b8;font-size:13px;border-bottom:1px solid #2a2a2a;">Job Number</td><td style="padding:10px 0;font-size:13px;font-weight:600;border-bottom:1px solid #2a2a2a;">{job}</td></tr>
        <tr><td style="padding:10px 0;color:#94a3b8;font-size:13px;border-bottom:1px solid #2a2a2a;">Service</td><td style="padding:10px 0;font-size:13px;border-bottom:1px solid #2a2a2a;">{service}</td></tr>
        <tr><td style="padding:10px 0;color:#94a3b8;font-size:13px;border-bottom:1px solid #2a2a2a;">Date</td><td style="padding:10px 0;font-size:13px;border-bottom:1px solid #2a2a2a;">{date}</td></tr>
        <tr><td style="padding:10px 0;color:#94a3b8;font-size:13px;border-bottom:1px solid #2a2a2a;">Time</td><td style="padding:10px 0;font-size:13px;border-bottom:1px solid #2a2a2a;">{booking_time}</td></tr>
        <tr><td style="padding:10px 0;color:#94a3b8;font-size:13px;">Location</td><td style="padding:10px 0;font-size:13px;">{city}</td></tr>
      </table>
      <p style="margin-bottom:8px;">
        <a href="{modify_url}" style="display:inline-block;background:#FFD700;color:#0a0a0a;text-decoration:none;font-size:12px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;padding:12px 24px;">
          Modify My Booking
        </a>
      </p>
      <p style="font-size:12px;color:#3a3a3a;border-top:1px solid #2a2a2a;padding-top:24px;">
        If you did not request this change, please contact us at info@gprsurveys.ca.
      </p>
    </div>
    """
    plain = f"Booking Updated — {job}\nService: {service}\nDate: {date} at {booking_time}\nLocation: {city}\n\nModify your booking: {modify_url}"
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

    subject = f"[UPDATED BOOKING] {job} — {service} — {booking.get('site_city', '')}"
    html = f"""
    <div style="font-family:sans-serif;max-width:600px;">
      <h2>[UPDATED BOOKING] {job}</h2>
      <p><strong>Service:</strong> {service}<br>
      <strong>Site:</strong> {address}<br>
      <strong>Customer:</strong> {customer_name} — {customer.get('email', '')}<br>
      <strong>Site Contact:</strong> {booking.get('site_contact_first_name', '')} {booking.get('site_contact_last_name', '')} {booking.get('site_contact_phone', '')}</p>
      <table style="border-collapse:collapse;margin:16px 0;">
        <tr>
          <th style="text-align:left;padding:6px 16px 6px 0;color:#666;font-weight:normal;">Field</th>
          <th style="text-align:left;padding:6px 16px 6px 0;color:#666;font-weight:normal;">Before</th>
          <th style="text-align:left;padding:6px 0;color:#666;font-weight:normal;">After</th>
        </tr>
        <tr>
          <td style="padding:6px 16px 6px 0;"><strong>Date</strong></td>
          <td style="padding:6px 16px 6px 0;">{old_date}</td>
          <td style="padding:6px 0;"><strong>{new_date}</strong></td>
        </tr>
        <tr>
          <td style="padding:6px 16px 6px 0;"><strong>Time</strong></td>
          <td style="padding:6px 16px 6px 0;">{old_time}</td>
          <td style="padding:6px 0;"><strong>{new_time}</strong></td>
        </tr>
      </table>
      <p><strong>Notes:</strong> {booking.get('notes', '—')}</p>
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

    subject = f"[CANCELLED BOOKING] {job} — {service} — {booking.get('site_city', '')}"
    html = f"""
    <div style="font-family:sans-serif;max-width:600px;">
      <h2>[CANCELLED BOOKING] {job}</h2>
      <p><strong>Service:</strong> {service}<br>
      <strong>Date:</strong> {date} at {time_str}<br>
      <strong>Site:</strong> {address}<br>
      <strong>Customer:</strong> {customer_name} — {customer.get('email', '')}<br>
      <strong>Site Contact:</strong> {booking.get('site_contact_first_name', '')} {booking.get('site_contact_last_name', '')} {booking.get('site_contact_phone', '')}<br>
      <strong>Assigned Tech:</strong> {tech_name}</p>
      <p><strong>Notes:</strong> {booking.get('notes', '—')}</p>
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

    subject = f"Booking Cancelled — {job} | GPR Surveys"
    html = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto;background:#0a0a0a;color:#fff;padding:40px;">
      <div style="border-top:2px solid #FFD700;padding-top:24px;margin-bottom:32px;">
        <h1 style="font-size:13px;letter-spacing:0.2em;text-transform:uppercase;color:#FFD700;margin:0 0 4px;">GPR SURVEYS</h1>
      </div>
      <h2 style="font-size:22px;margin:0 0 8px;">Booking Cancelled</h2>
      <p style="color:#94a3b8;margin-bottom:32px;">Hi {first_name}, your booking has been cancelled.</p>
      <table style="width:100%;border-collapse:collapse;margin-bottom:32px;">
        <tr><td style="padding:10px 0;color:#94a3b8;font-size:13px;border-bottom:1px solid #2a2a2a;">Job Number</td><td style="padding:10px 0;font-size:13px;font-weight:600;border-bottom:1px solid #2a2a2a;">{job}</td></tr>
        <tr><td style="padding:10px 0;color:#94a3b8;font-size:13px;border-bottom:1px solid #2a2a2a;">Service</td><td style="padding:10px 0;font-size:13px;border-bottom:1px solid #2a2a2a;">{service}</td></tr>
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
    name = record.get("name", "Unknown")
    email = record.get("email", "")
    message = record.get("message", "")
    subject = f"[NEW CONTACT] {name} — via gprsurveys.ca"
    html = f"""
    <div style="font-family:sans-serif;max-width:600px;">
      <h2>[NEW CONTACT] {name}</h2>
      <p style="color:#666;font-size:13px;">Someone filled out the contact form on gprsurveys.ca.</p>
      <p><strong>Name:</strong> {name}<br>
      <strong>Email:</strong> {email}</p>
      <p><strong>Message:</strong><br>{message}</p>
    </div>
    """
    plain = f"New contact form submission from gprsurveys.ca\n\nName: {name}\nEmail: {email}\n\nMessage:\n{message}"
    return subject, html, plain


TEMPLATES = {
    "customer_confirmation": _customer_confirmation,
    "customer_modification": _customer_modification,
    "customer_cancellation": _customer_cancellation,
    "internal_notification": _internal_notification,
    "internal_modification": _internal_modification,
    "internal_cancellation": _internal_cancellation,
    "booking_reminder": _booking_reminder,
    "contact_notification": _contact_notification,
}

# Templates that receive the full payload (not just booking) because they need extra state
_FULL_PAYLOAD_TEMPLATES = {"internal_modification"}

# Templates that use record (not booking) as their data source
_RECORD_TEMPLATES = {"contact_notification"}


def run(payload: dict) -> dict:
    booking = payload.get("booking")
    template = payload.get("template", "customer_confirmation")

    if template not in TEMPLATES:
        raise ValueError(f"send_email: unknown template '{template}'")
    if template not in _RECORD_TEMPLATES and not booking:
        raise ValueError("send_email: booking required")

    service = _get_service()
    if template in _FULL_PAYLOAD_TEMPLATES:
        subject, html, plain = TEMPLATES[template](payload)
    elif template in _RECORD_TEMPLATES:
        subject, html, plain = TEMPLATES[template](payload.get("record", {}))
    else:
        subject, html, plain = TEMPLATES[template](booking)

    if template in ("internal_notification", "internal_modification", "internal_cancellation", "contact_notification"):
        to = settings.gmail_internal_recipient
    else:
        customer = booking.get("customers") or {}
        to = customer.get("email") or booking.get("billing_email") or ""

    if not to:
        raise ValueError("send_email: no recipient email found")

    msg_id = _send(service, to, subject, html, plain)
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
