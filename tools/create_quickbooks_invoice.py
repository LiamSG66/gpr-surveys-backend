"""
Create a QuickBooks Online invoice for a completed job.

- Finds or creates the customer by email
- Creates an invoice with billing address, custom fields (Job#, PO#), CC emails
- No line items (entered manually in QBO)

Input payload:
    {
        "invoice_data": {
            "customer_display_name": str,
            "billing_email":         str,
            "billing_address": {
                "line1":    str,
                "line2":    str,
                "city":     str,
                "province": str,
                "postal":   str
            },
            "invoice_date": str,   # "YYYY-MM-DD"
            "job_number":   str,
            "po_number":    str,
            "cc_emails":    str    # comma-separated
        }
    }

Returns:
    { "invoice_id": str, "invoice_number": str, "invoice_url": str }
"""

import os
from datetime import datetime

from quickbooks import QuickBooks
from quickbooks.objects.customer import Customer
from quickbooks.objects.invoice import Invoice
from quickbooks.objects.detailline import SalesItemLine, SalesItemLineDetail
from quickbooks.objects.base import Ref, EmailAddress, Address as BillAddr, CustomField
from tools.qb_client import get_qb_client

# Custom field DefinitionIds — set in QBO Settings > Custom Fields, in this order:
# 1 = P.O. Number, 2 = Job Number, 3 = Service
QB_CF_PO_NUMBER_ID  = "1"
QB_CF_JOB_NUMBER_ID = "2"


# ─── Customer helpers ─────────────────────────────────────────────────────────

def _escape_qb_value(val: str) -> str:
    """Escape single quotes for QuickBooks query language."""
    return val.replace("\\", "\\\\").replace("'", "\\'")


def _find_customer(qb: QuickBooks, display_name: str, email: str) -> Customer | None:
    """Look up customer by DisplayName first (QBO enforces uniqueness on it), then by email."""
    try:
        safe_name = _escape_qb_value(display_name)
        results = Customer.query(
            f"SELECT * FROM Customer WHERE DisplayName = '{safe_name}'",
            qb=qb,
        )
        if results:
            return results[0]
    except Exception:
        pass
    try:
        safe_email = _escape_qb_value(email)
        results = Customer.query(
            f"SELECT * FROM Customer WHERE PrimaryEmailAddr = '{safe_email}'",
            qb=qb,
        )
        if results:
            return results[0]
    except Exception:
        pass
    return None


def _create_customer(qb: QuickBooks, display_name: str, email: str, billing_addr: dict) -> Customer:
    customer = Customer()
    customer.DisplayName = display_name
    customer.PrimaryEmailAddr = EmailAddress()
    customer.PrimaryEmailAddr.Address = email

    addr = BillAddr()
    addr.Line1   = billing_addr.get("line1", "")
    addr.Line2   = billing_addr.get("line2", "")
    addr.City    = billing_addr.get("city", "")
    addr.CountrySubDivisionCode = billing_addr.get("province", "BC")
    addr.PostalCode = billing_addr.get("postal", "")
    addr.Country = "Canada"
    customer.BillAddr = addr

    customer.save(qb=qb)
    return customer


def _ensure_customer(qb: QuickBooks, display_name: str, email: str, billing_addr: dict) -> str:
    """Find existing customer or create a new one. Returns customer ID."""
    existing = _find_customer(qb, display_name, email)
    if existing:
        return existing.Id
    new_cust = _create_customer(qb, display_name, email, billing_addr)
    return new_cust.Id


# ─── Invoice creation ─────────────────────────────────────────────────────────

def run(payload: dict) -> dict:
    inv = payload.get("invoice_data", {})

    customer_display_name = inv.get("customer_display_name", "")
    billing_email         = inv.get("billing_email", "")
    billing_addr          = inv.get("billing_address", {})
    invoice_date          = inv.get("invoice_date", datetime.today().strftime("%Y-%m-%d"))
    job_number            = inv.get("job_number", "")
    po_number             = inv.get("po_number", "")
    cc_emails             = inv.get("cc_emails", "")


    qb = get_qb_client()

    customer_id = _ensure_customer(qb, customer_display_name, billing_email, billing_addr)

    invoice = Invoice()
    invoice.GlobalTaxCalculation = "NotApplicable"

    # Customer ref
    invoice.CustomerRef = Ref()
    invoice.CustomerRef.value = customer_id
    invoice.CustomerRef.name  = customer_display_name

    # Date
    invoice.TxnDate = invoice_date

    # Billing email
    invoice.BillEmail = EmailAddress()
    invoice.BillEmail.Address = billing_email

    # CC emails
    if cc_emails:
        invoice.BillEmailCc = EmailAddress()
        invoice.BillEmailCc.Address = cc_emails

    # Billing address
    bill_addr = BillAddr()
    bill_addr.Line1   = billing_addr.get("line1", "")
    bill_addr.Line2   = billing_addr.get("line2", "")
    bill_addr.City    = billing_addr.get("city", "")
    bill_addr.CountrySubDivisionCode = billing_addr.get("province", "BC")
    bill_addr.PostalCode = billing_addr.get("postal", "")
    bill_addr.Country = "Canada"
    invoice.BillAddr = bill_addr

    # Custom fields — print on invoice PDF (DefinitionIds match QBO Settings > Custom Fields order)
    print(f"[qb_invoice] po_number={po_number!r} job_number={job_number!r}")
    custom_fields = []
    if po_number:
        cf = CustomField()
        cf.DefinitionId = QB_CF_PO_NUMBER_ID
        cf.Name = "P.O. Number"
        cf.Type = "StringType"
        cf.StringValue = po_number
        custom_fields.append(cf)
    if job_number:
        cf = CustomField()
        cf.DefinitionId = QB_CF_JOB_NUMBER_ID
        cf.Name = "Job Number"
        cf.Type = "StringType"
        cf.StringValue = job_number
        custom_fields.append(cf)
    print(f"[qb_invoice] custom_fields payload={[cf.to_dict() for cf in custom_fields]}")
    if custom_fields:
        invoice.CustomField = custom_fields

    # QBO requires at least one line item even if empty
    # Add a placeholder description line
    line = SalesItemLine()
    line.Amount = 0
    line.Description = f"Job {job_number} — GPR Surveys Inc. (Line items to be added)"
    line.SalesItemLineDetail = SalesItemLineDetail()
    invoice.Line = [line]

    invoice.save(qb=qb)

    # Diagnostic: read back the invoice to verify custom fields and confirm real DefinitionIds
    try:
        saved = Invoice.get(invoice.Id, qb=qb)
        print(f"[qb_invoice] saved CustomField response={[cf.to_dict() if hasattr(cf, 'to_dict') else cf for cf in (saved.CustomField or [])]}")
    except Exception as e:
        print(f"[qb_invoice] could not read back invoice: {e}")

    realm_id    = os.environ.get("QB_REALM_ID", "")
    invoice_id  = invoice.Id
    invoice_num = invoice.DocNumber or invoice_id
    invoice_url = f"https://app.qbo.intuit.com/app/invoice?txnId={invoice_id}"
    if os.environ.get("QB_ENVIRONMENT", "sandbox") == "sandbox":
        invoice_url = f"https://app.sandbox.qbo.intuit.com/app/invoice?txnId={invoice_id}"

    return {
        "invoice_id":     invoice_id,
        "invoice_number": invoice_num,
        "invoice_url":    invoice_url,
    }


if __name__ == "__main__":
    import sys, json
    from dotenv import load_dotenv
    load_dotenv()
    payload = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    print(json.dumps(run(payload), indent=2))
