"""
Attach a PDF to a QuickBooks Online invoice using the Attachable API.

Input payload:
    {
        "invoice_id": str,
        "pdf_bytes":  str,   # base64-encoded
        "filename":   str    # e.g. "GPR-2601_Field_Report_2026-03-05.pdf"
    }

Returns: { "attachable_id": str }
"""

import base64

from quickbooks.objects.attachable import Attachable, AttachableRef
from tools.qb_client import get_qb_client


def run(payload: dict) -> dict:
    invoice_id = payload.get("invoice_id")
    pdf_bytes  = payload.get("pdf_bytes", "")
    filename   = payload.get("filename", "field_report.pdf")

    if not invoice_id:
        raise ValueError("attach_to_quickbooks_invoice: invoice_id is required")
    if not pdf_bytes:
        raise ValueError("attach_to_quickbooks_invoice: pdf_bytes is required")

    qb = get_qb_client()

    decoded = base64.b64decode(pdf_bytes)

    attachable = Attachable()
    attachable.FileName    = filename
    attachable.ContentType = "application/pdf"
    attachable._FileBytes  = decoded  # python-quickbooks uses this for binary upload

    ref = AttachableRef()
    ref.EntityRef = {"type": "Invoice", "value": invoice_id}
    attachable.AttachableRef = [ref]

    attachable.save(qb=qb)

    return {"attachable_id": attachable.Id}


if __name__ == "__main__":
    import sys, json
    from dotenv import load_dotenv
    load_dotenv()
    payload = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    print(json.dumps(run(payload), indent=2))
