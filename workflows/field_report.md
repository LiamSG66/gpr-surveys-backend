# Workflow: field_report

## Objective
Generate a field report PDF for a completed job, upload it to the booking's Google Drive
Reports/ folder, optionally create a QuickBooks Online invoice and attach the PDF to it,
and optionally send a Google Review request email to the customer.

## Trigger
Called directly by the `field_report_endpoint` in `main.py`, which is invoked by the
Next.js API route `POST /api/admin/field-report`.

## Required Inputs (from payload)
- `report_data` (dict) — full report fields (see generate_field_report_pdf.py for schema)
- `photos` (list) — `[{url, caption}]` — signed Supabase URLs
- `booking` (dict) — booking record with `job_number`, `google_drive_folder_id`, `customers`, etc.
- `create_invoice` (bool) — whether to create a QB invoice
- `invoice_data` (dict) — QB invoice fields (if create_invoice=True)
- `review_email` (bool) — whether to send Google Review request
- `report_date` (str) — "YYYY-MM-DD"

## Steps

### Step 1 — Generate field report PDF
Tool: `tools/generate_field_report_pdf.py`
Input:
```json
{
  "report_data": { ...report fields... },
  "photos": [{"url": "...", "caption": "..."}]
}
```
Output: `{ "pdf_bytes": "<base64>" }`

### Step 2 — Upload PDF to Google Drive Reports/ folder
Tool: `tools/upload_field_report_to_drive.py`
Input:
```json
{
  "booking": { "job_number": "...", "google_drive_folder_id": "..." },
  "pdf_bytes": "<base64>",
  "report_date": "YYYY-MM-DD"
}
```
Output: `{ "drive_file_id": "...", "drive_file_url": "https://drive.google.com/file/d/..." }`

### Step 3 — [if create_invoice] Create QuickBooks invoice
Tool: `tools/create_quickbooks_invoice.py`
Input:
```json
{
  "invoice_data": {
    "customer_display_name": "...",
    "billing_email": "...",
    "billing_address": { "line1": "...", "city": "...", "province": "BC", "postal": "..." },
    "invoice_date": "YYYY-MM-DD",
    "job_number": "...",
    "po_number": "...",
    "cc_emails": "..."
  }
}
```
Output: `{ "invoice_id": "...", "invoice_number": "...", "invoice_url": "https://app.qbo..." }`

### Step 4 — [if create_invoice] Attach PDF to QB invoice
Tool: `tools/attach_to_quickbooks_invoice.py`
Input:
```json
{
  "invoice_id": "...",
  "pdf_bytes":  "<base64>",
  "filename":   "GPR-2601_Field_Report_2026-03-05.pdf"
}
```
Output: `{ "attachable_id": "..." }`

### Step 5 — [if review_email] Send Google Review request
Tool: `tools/send_email.py`
Input:
```json
{
  "booking": { ...full booking with customers nested... },
  "template": "google_review_request"
}
```
Output: `{ "email_google_review_request_id": "..." }`

## Output (returned to Next.js)
```json
{
  "drive_file_id":  "...",
  "drive_file_url": "https://drive.google.com/file/d/.../view",
  "invoice_id":     "...",  // null if create_invoice=false
  "invoice_url":    "..."   // null if create_invoice=false
}
```

## Notes
- `booking.google_drive_folder_id` must be set (created by new_booking workflow)
- QB credentials must be in .env / Modal secrets: QB_CLIENT_ID, QB_CLIENT_SECRET, QB_REFRESH_TOKEN, QB_REALM_ID
- QB custom field IDs: QB_CUSTOM_FIELD_JOB_NUM_ID, QB_CUSTOM_FIELD_PO_ID
- Google Review URL env var: GOOGLE_REVIEW_URL
- QB_ENVIRONMENT defaults to "sandbox" — change to "production" for live
- The `field_reports` table row is inserted by the Next.js API route (not this workflow)

## Error handling
- If Drive upload fails, raise exception — do not continue to QB step
- If QB invoice creation fails, log error but still return drive_file_url
- If review email fails, log error — do not fail the whole workflow
