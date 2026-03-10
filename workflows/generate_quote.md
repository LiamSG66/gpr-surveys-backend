# Workflow: Generate Quote PDF

## Objective
Generate a branded 5-page PDF quote and upload it to the Google Drive "Quotes" folder.

## Required Inputs
- `contact` — contact_submissions record (includes quote_number, name, company, email, phone)
- `quote_data` — JSONB object with client, project_description, line_items, total, site_image_path, etc.
- `site_image_url` — (optional) signed URL for the site image; passed by the caller

## Steps
1. Generate 5-page PDF from contact and quote_data → tools/generate_quote_pdf.py
2. Upload PDF to Google Drive Quotes folder → tools/upload_quote_to_drive.py

## Output
- `pdf_bytes` — base64-encoded PDF bytes (from step 1)
- `drive_file_id` — Google Drive file ID of uploaded PDF
- `drive_url` — shareable Drive URL

## Notes
- If `site_image_url` is not provided, page 2 will show a placeholder box.
- The Quotes folder is found or created automatically under GOOGLE_DRIVE_ROOT_FOLDER_ID.
- PDF filename format: `{quote_number}_{company_or_name}.pdf`
