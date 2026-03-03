"""
Shared Google API auth helper using a Service Account with Domain-Wide Delegation.

All tools import get_google_service() from here instead of managing credentials themselves.
The service account JSON is loaded from the SERVICE_ACCOUNT_JSON environment variable
(set as a Modal secret in production, or in .env locally).
"""

import json
import os

from google.oauth2 import service_account
from googleapiclient.discovery import build


def get_google_service(api: str, version: str, subject: str, scopes: list[str]):
    """Build a Google API service client impersonating `subject` (@gprsurveys.ca email).

    Args:
        api:     API name, e.g. "calendar", "drive", "gmail"
        version: API version, e.g. "v3", "v1"
        subject: The @gprsurveys.ca email to impersonate via DWD
        scopes:  OAuth scopes required by the API
    """
    raw = os.environ.get("SERVICE_ACCOUNT_JSON")
    if not raw:
        raise RuntimeError(
            "SERVICE_ACCOUNT_JSON env var is not set. "
            "Add it to .env locally or upload via: modal secret create gpr-service-account SERVICE_ACCOUNT_JSON='...'"
        )
    info = json.loads(raw)
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=scopes, subject=subject
    )
    return build(api, version, credentials=creds)
