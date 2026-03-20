# Workflow: Generate Quote PDF

## Objective
Generate a branded multi-page PDF quote and upload it to the Google Drive "Quotes" folder.

## Required Inputs
- `contact` — contact_submissions record (includes quote_number, name, company, email, phone)
- `quote_data` — JSONB object with client, project_description, project_name, project_overview_items, line_items, total, site_image_path, site_image_caption, template_type, custom_notes, is_blank
- `site_image_url` — (optional) signed URL for the site image; passed by the caller
- `template_type` — one of: `locate_single`, `dual_services`, `full_services`, `survey_single` (default: `locate_single`)

## Steps
1. Generate PDF from contact and quote_data → tools/generate_quote_pdf.py
2. Upload PDF to Google Drive Quotes folder → tools/upload_quote_to_drive.py
3. Upload PDF to Supabase Storage for inline preview → tools/upload_quote_to_supabase.py

## Output
- `pdf_bytes` — base64-encoded PDF bytes (from step 1)
- `drive_file_id` — Google Drive file ID of uploaded PDF
- `drive_url` — shareable Drive URL
- `supabase_pdf_path` — storage path in the `quote-pdfs` Supabase bucket (e.g. `Q00042.pdf`)

## Template Types

| template_type | Display Name | Pages | Description |
|---|---|---|---|
| `locate_single` | Locate Single Service | ~7 | GPR/EM subsurface utility locating only |
| `dual_services` | Dual Services | ~7 | GPR/EM locating + AutoCAD/Civil 3D deliverables |
| `full_services` | Full Services | ~9 | GPR/EM locating + topographic survey + full deliverables |
| `survey_single` | Survey Single Service | ~8 | Topographic survey only |

## Notes
- `template_type` is read from top-level payload first, then falls back to `quote_data.template_type`, then `"locate_single"`.
- If `site_image_url` is not provided, page 2 will show a placeholder box.
- If `project_overview_items` is not in `quote_data`, falls back to `[project_description]` as a single bullet.
- The Quotes folder is found or created automatically under GOOGLE_DRIVE_ROOT_FOLDER_ID.
- PDF filename format: `{quote_number}_{company_or_name}.pdf`
