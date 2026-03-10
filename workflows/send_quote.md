# Workflow: Send Quote Email

## Objective
Download a quote PDF from Drive and send it to the customer as an email attachment.

## Required Inputs
- `contact` — contact_submissions record (email, name, quote_number)
- `drive_file_id` — Google Drive file ID of the quote PDF
- `pdf_filename` — filename for the email attachment (e.g., "Q26001_Stantec.pdf")

## Steps
1. Download PDF bytes from Google Drive → tools/fetch_quote_pdf_from_drive.py
2. Send quote email with PDF attachment to customer → tools/send_email.py (template: quote_email)

## Output
- `email_quote_email_id` — Gmail message ID

## Notes
- The `pdf_bytes` (base64) output from step 1 is automatically picked up by send_email.py.
- After this workflow completes, the Next.js API route updates quote_status to 'quoted' and records quote_sent_at.
