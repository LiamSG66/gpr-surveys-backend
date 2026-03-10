"""
Generate a 5-page branded PDF quote using reportlab.
Input:  { contact: dict, quote_data: dict, site_image_url: str|None }
Output: { pdf_bytes: str }  — base64-encoded PDF bytes

Page structure:
  1 — Cover (logos, title, date, Prepared For, Project Description, Prepared By)
  2 — Project Location (site image) + Pricing Details table
  3 — Boilerplate: Overview, Professional Qualifications, Reporting, Billing, Safety & Liability
  4 — Provisions: Access Requirements, Traffic Management, Working Hours
  5 — Client Authorization & Quote Approval
"""

import base64
import io
import os
import json
from datetime import datetime

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.lib.colors import HexColor, black, white
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image as RLImage, PageBreak, HRFlowable,
)
from reportlab.platypus.flowables import Flowable
from reportlab.lib import colors


# ─── Constants ────────────────────────────────────────────────────────────────

PAGE_W, PAGE_H = LETTER          # 612 × 792 pts
MARGIN_L = 0.75 * inch
MARGIN_R = 0.75 * inch
MARGIN_T = 1.1 * inch            # leaves room for header drawn in onPage
MARGIN_B = 0.9 * inch            # leaves room for footer

BLUE     = HexColor("#1F4E79")
GOLD     = HexColor("#C9A84C")   # warm gold close to GPR brand
DARK     = HexColor("#0a0a0a")
MID_GRAY = HexColor("#555555")
LIGHT_GRAY = HexColor("#DDDDDD")

FONT_BOLD   = "Helvetica-Bold"
FONT_NORMAL = "Helvetica"

ASSETS_DIR       = os.path.join(os.path.dirname(__file__), "assets")
LOGO_PATH        = os.path.join(ASSETS_DIR, "gpr_logo.png")
CERT_CCGA_PATH   = os.path.join(ASSETS_DIR, "CCGALogo.jpg")
CERT_BC1C_PATH   = os.path.join(ASSETS_DIR, "BC1C-logo-300w-2.webp")
CERT_WSBC_PATH   = os.path.join(ASSETS_DIR, "3-worksafebc-logo-col.jpg")


def _load_image_path_or_bytes(path: str):
    """Return a path or ImageReader for reportlab drawImage. Converts WebP to PNG in-memory."""
    from reportlab.lib.utils import ImageReader
    if not os.path.exists(path):
        return None
    if path.lower().endswith(".webp"):
        try:
            from PIL import Image as PILImage
            buf = io.BytesIO()
            PILImage.open(path).convert("RGBA").save(buf, format="PNG")
            buf.seek(0)
            return ImageReader(buf)
        except Exception:
            return None
    return path

PREPARED_BY = {
    "name":    "Louis Gosselin",
    "title":   "Managing Partner",
    "email":   "LG@gprsurveys.ca",
    "address": "550-2950 Douglas St, Victoria BC",
    "phone":   "(250) 896-7576",
}


# ─── Styles ───────────────────────────────────────────────────────────────────

def _build_styles():
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        "Section",
        fontName=FONT_BOLD,
        fontSize=10,
        textColor=BLUE,
        spaceAfter=4,
        spaceBefore=10,
        leading=13,
        underline=1,
    ))
    styles.add(ParagraphStyle(
        "Body",
        fontName=FONT_NORMAL,
        fontSize=9,
        textColor=black,
        leading=13,
        spaceAfter=4,
        alignment=TA_JUSTIFY,
    ))
    styles.add(ParagraphStyle(
        "BodySmall",
        fontName=FONT_NORMAL,
        fontSize=8,
        textColor=MID_GRAY,
        leading=11,
        spaceAfter=3,
    ))
    styles.add(ParagraphStyle(
        "Label",
        fontName=FONT_BOLD,
        fontSize=9,
        textColor=MID_GRAY,
        leading=12,
    ))
    styles.add(ParagraphStyle(
        "Value",
        fontName=FONT_NORMAL,
        fontSize=9,
        textColor=black,
        leading=12,
    ))
    styles.add(ParagraphStyle(
        "CoverTitle",
        fontName=FONT_BOLD,
        fontSize=20,
        leading=26,
        textColor=BLUE,
        alignment=TA_CENTER,
        spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        "CoverSub",
        fontName=FONT_NORMAL,
        fontSize=10,
        textColor=MID_GRAY,
        alignment=TA_LEFT,
    ))
    styles.add(ParagraphStyle(
        "PreparedFor",
        fontName=FONT_BOLD,
        fontSize=9,
        textColor=black,
        leading=14,
    ))
    styles.add(ParagraphStyle(
        "CaptionItalic",
        fontName="Helvetica-Oblique",
        fontSize=8,
        textColor=MID_GRAY,
        alignment=TA_CENTER,
        spaceAfter=6,
    ))
    styles.add(ParagraphStyle(
        "TableHeader",
        fontName=FONT_BOLD,
        fontSize=9,
        textColor=white,
        alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        "TableCell",
        fontName=FONT_NORMAL,
        fontSize=9,
        textColor=black,
        alignment=TA_LEFT,
    ))
    styles.add(ParagraphStyle(
        "TableCellRight",
        fontName=FONT_NORMAL,
        fontSize=9,
        textColor=black,
        alignment=TA_RIGHT,
    ))
    styles.add(ParagraphStyle(
        "TableCellBold",
        fontName=FONT_BOLD,
        fontSize=9,
        textColor=black,
        alignment=TA_RIGHT,
    ))
    return styles


# ─── Header / Footer (drawn per page via canvas callback) ─────────────────────

def _on_page(canvas, doc):
    canvas.saveState()
    page_num = doc.page
    total    = getattr(doc, "_total_pages", 5)
    is_cover = page_num == 1

    # ── Header line — skip on cover page ──
    if not is_cover:
        canvas.setStrokeColor(BLUE)
        canvas.setLineWidth(1.5)
        canvas.line(MARGIN_L, PAGE_H - 0.55 * inch, PAGE_W - MARGIN_R, PAGE_H - 0.55 * inch)

    # Logo dimensions — 40% larger on cover
    logo_w = 1.96 * inch if is_cover else 1.4 * inch
    logo_h = 0.53 * inch if is_cover else 0.38 * inch

    # Logo left
    if os.path.exists(LOGO_PATH):
        try:
            canvas.drawImage(
                LOGO_PATH,
                MARGIN_L, PAGE_H - 0.95 * inch,
                width=logo_w, height=logo_h,
                preserveAspectRatio=True, mask="auto",
            )
        except Exception:
            pass

    # Company name centred
    canvas.setFont(FONT_BOLD, 10)
    canvas.setFillColor(BLUE)
    canvas.drawCentredString(PAGE_W / 2, PAGE_H - 0.45 * inch, "GPR SURVEYS INC")

    # Logo right (same image, mirrored position)
    if os.path.exists(LOGO_PATH):
        try:
            canvas.drawImage(
                LOGO_PATH,
                PAGE_W - MARGIN_R - logo_w, PAGE_H - 0.95 * inch,
                width=logo_w, height=logo_h,
                preserveAspectRatio=True, mask="auto",
            )
        except Exception:
            pass

    # ── Footer line ──
    canvas.setStrokeColor(LIGHT_GRAY)
    canvas.setLineWidth(0.5)
    canvas.line(MARGIN_L, MARGIN_B - 0.12 * inch, PAGE_W - MARGIN_R, MARGIN_B - 0.12 * inch)

    # Footer certification logos — centered
    cert_logos = [
        (CERT_CCGA_PATH, 0.9 * inch),
        (CERT_BC1C_PATH, 0.9 * inch),
        (CERT_WSBC_PATH, 1.1 * inch),
    ]
    spacing = 0.15 * inch
    total_logos_w = sum(w for _, w in cert_logos) + spacing * (len(cert_logos) - 1)
    x_pos = (PAGE_W - total_logos_w) / 2
    for cert_path, logo_w in cert_logos:
        img_src = _load_image_path_or_bytes(cert_path)
        if img_src is not None:
            try:
                canvas.drawImage(
                    img_src,
                    x_pos, 0.1 * inch,
                    width=logo_w, height=0.45 * inch,
                    preserveAspectRatio=True, mask="auto",
                )
                x_pos += logo_w + spacing
            except Exception:
                pass

    # Page number right
    canvas.setFont(FONT_NORMAL, 8)
    canvas.setFillColor(MID_GRAY)
    canvas.drawRightString(
        PAGE_W - MARGIN_R,
        0.3 * inch,
        f"Page {page_num} of {total}",
    )

    canvas.restoreState()


# ─── Section helpers ──────────────────────────────────────────────────────────

def _section(title, styles):
    return Paragraph(f"<u><b>{title.upper()}</b></u>", styles["Section"])


def _body(text, styles, **kwargs):
    return Paragraph(text, styles["Body"], **kwargs)


def _hr():
    return HRFlowable(width="100%", thickness=0.5, color=LIGHT_GRAY, spaceAfter=6, spaceBefore=2)


def _fmt_date(date_str: str) -> str:
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%B %d, %Y")
    except Exception:
        return date_str or datetime.today().strftime("%B %d, %Y")


# ─── Pages ────────────────────────────────────────────────────────────────────

def _page1(contact, quote_data, styles):
    """Cover page."""
    story = []

    quote_number = contact.get("quote_number", "Q00001")
    date_str = _fmt_date(datetime.today().strftime("%Y-%m-%d"))

    client = quote_data.get("client", {})
    is_blank = quote_data.get("is_blank", False)

    # Title — centered, 26pt
    story.append(Paragraph("PROFESSIONAL SERVICES PROPOSAL", styles["CoverTitle"]))
    story.append(Spacer(1, 0.1 * inch))
    story.append(HRFlowable(width="100%", thickness=2, color=BLUE, spaceAfter=8))

    # Date + Ref below the horizontal rule
    story.append(Paragraph(
        f"<b>Date:</b> {date_str}&nbsp;&nbsp;&nbsp;&nbsp;<b>Ref:</b> {quote_number}",
        styles["Label"],
    ))
    story.append(Spacer(1, 0.2 * inch))

    # PREPARED FOR
    story.append(_section("Prepared For", styles))
    if is_blank:
        prepared_for_lines = [
            "[CLIENT NAME]",
            "[TITLE]",
            "[COMPANY]",
            "[EMAIL]",
            "[PHONE]",
        ]
    else:
        prepared_for_lines = [
            client.get("name", contact.get("first_name", "") + " " + contact.get("last_name", "")).strip(),
            client.get("title", contact.get("contact_title", "")),
            client.get("company", contact.get("company", "")),
            client.get("email", contact.get("email", "")),
            client.get("phone", contact.get("phone", "")),
        ]

    for line in prepared_for_lines:
        if line:
            story.append(Paragraph(line, styles["PreparedFor"]))
    story.append(Spacer(1, 0.15 * inch))

    # PROJECT DESCRIPTION
    story.append(_section("Project Description", styles))
    proj_desc = quote_data.get("project_description") or "[PROJECT DESCRIPTION]"
    story.append(_body(proj_desc, styles))
    story.append(Spacer(1, 0.2 * inch))

    # PREPARED BY
    story.append(_section("Proposal Prepared By", styles))
    by_lines = [
        PREPARED_BY["name"],
        PREPARED_BY["title"],
        PREPARED_BY["email"],
        PREPARED_BY["address"],
        PREPARED_BY["phone"],
        "gprsurveys.ca",
    ]
    for line in by_lines:
        story.append(Paragraph(line, styles["PreparedFor"]))

    return story


def _page2(quote_data, site_image_url, styles):
    """Project Location + Pricing Details."""
    story = []

    # PROJECT LOCATION
    story.append(_section("Project Location", styles))

    site_img_loaded = False
    if site_image_url:
        try:
            import urllib.request
            tmp = io.BytesIO()
            with urllib.request.urlopen(site_image_url, timeout=10) as resp:
                tmp.write(resp.read())
            tmp.seek(0)
            img = RLImage(tmp, width=5.5 * inch, height=3.5 * inch, kind="proportional")
            story.append(img)
            site_img_loaded = True
        except Exception:
            pass

    if not site_img_loaded:
        # Placeholder box
        story.append(Paragraph("[SITE IMAGE — attach satellite/plan view]", styles["CaptionItalic"]))
        story.append(Spacer(1, 0.1 * inch))

    caption = quote_data.get("site_image_caption", "")
    if caption:
        story.append(Paragraph(f"<i>{caption}</i>", styles["CaptionItalic"]))

    story.append(Spacer(1, 0.2 * inch))

    # PRICING DETAILS
    story.append(_section("Pricing Details", styles))

    line_items     = quote_data.get("line_items", [])
    custom_columns = quote_data.get("custom_columns", [])
    n_custom       = len(custom_columns)

    # Dynamic column widths
    if n_custom == 0:
        desc_w, amount_w, custom_ws = 3.2 * inch, 2.0 * inch, []
    elif n_custom == 1:
        desc_w, amount_w, custom_ws = 2.8 * inch, 1.4 * inch, [1.0 * inch]
    elif n_custom == 2:
        desc_w, amount_w, custom_ws = 2.4 * inch, 1.2 * inch, [0.8 * inch, 0.8 * inch]
    else:
        desc_w, amount_w, custom_ws = 2.0 * inch, 1.2 * inch, [0.67 * inch, 0.67 * inch, 0.67 * inch]

    # Column order: Item | Desc | Unit | Qty | [custom cols] | Amount (always rightmost)
    col_widths = [0.4 * inch, desc_w, 0.7 * inch, 0.7 * inch] + custom_ws + [amount_w]

    # Table header — custom cols before Amount
    header = [
        Paragraph("Item", styles["TableHeader"]),
        Paragraph("Description", styles["TableHeader"]),
        Paragraph("Unit", styles["TableHeader"]),
        Paragraph("Qty", styles["TableHeader"]),
    ]
    for col in custom_columns:
        header.append(Paragraph(col.get("name", ""), styles["TableHeader"]))
    header.append(Paragraph("Amount", styles["TableHeader"]))
    table_data = [header]

    for i, item in enumerate(line_items):
        custom_vals = item.get("customValues", {})
        row = [
            Paragraph(str(i + 1), styles["TableCell"]),
            Paragraph(item.get("description", ""), styles["TableCell"]),
            Paragraph(item.get("unit", "LS"), styles["TableCell"]),
            Paragraph(str(item.get("quantity", 1)), styles["TableCell"]),
        ]
        for col in custom_columns:
            val = custom_vals.get(col["id"], 0)
            row.append(Paragraph(f"${val:,.2f}", styles["TableCellRight"]))
        row.append(Paragraph(f"${item.get('amount', 0):,.2f}", styles["TableCellRight"]))
        table_data.append(row)

    # Total row — custom cols show per-col subtotals; Amount (rightmost) shows grand total
    amount_total = sum(
        item.get("quantity", 1) * item.get("amount", 0) for item in line_items
    )
    custom_col_totals = []
    for col in custom_columns:
        col_total = sum(
            item.get("quantity", 1) * item.get("customValues", {}).get(col["id"], 0)
            for item in line_items
        )
        custom_col_totals.append(col_total)
    grand_total = amount_total + sum(custom_col_totals)

    total_row = [
        Paragraph("", styles["TableCell"]),
        Paragraph("", styles["TableCell"]),
        Paragraph("", styles["TableCell"]),
        Paragraph("TOTAL", styles["TableCellBold"]),
    ]
    for col_total in custom_col_totals:
        total_row.append(Paragraph(f"${col_total:,.2f}", styles["TableCellBold"]))
    total_row.append(Paragraph(f"${grand_total:,.2f}", styles["TableCellBold"]))
    table_data.append(total_row)

    pricing_table = Table(table_data, colWidths=col_widths)
    pricing_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BLUE),
        ("TEXTCOLOR",  (0, 0), (-1, 0), white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [HexColor("#F5F5F5"), white]),
        ("BACKGROUND", (0, -1), (-1, -1), HexColor("#EAF0F8")),
        ("GRID", (0, 0), (-1, -1), 0.25, LIGHT_GRAY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, -2), (-1, -2), 1.5, BLUE),
    ]))
    story.append(pricing_table)

    story.append(Spacer(1, 0.08 * inch))
    story.append(Paragraph("All prices are in Canadian dollars. Total excluding GST.", styles["BodySmall"]))

    custom_notes = quote_data.get("custom_notes", "")
    if custom_notes:
        story.append(Spacer(1, 0.1 * inch))
        story.append(_body(custom_notes, styles))

    return story


def _page3(styles):
    """Boilerplate — Overview, Qualifications, Reporting, Billing, Safety & Liability."""
    story = []

    story.append(_section("Overview", styles))
    story.append(_body(
        "GPR Surveys Inc. provides professional ground penetrating radar (GPR) and subsurface utility "
        "locating services. Our technicians are CGSB-certified and experienced in a wide range of subsurface "
        "investigation methods including GPR scanning, electromagnetic (EM) locating, and utility designation. "
        "All work is performed in compliance with applicable standards and client requirements.",
        styles,
    ))

    story.append(_section("Professional Qualifications", styles))
    story.append(_body(
        "GPR Surveys Inc. technicians hold certifications from the Canadian General Standards Board (CGSB) "
        "under CAN/CGSB-158.1 (Ground Penetrating Radar). Our team is trained and insured to work in a "
        "variety of site conditions including traffic control environments, confined spaces, and sensitive "
        "infrastructure zones. GPR Surveys Inc. is a member of the BC Common Ground Alliance (BCCGA) and "
        "registered with BC One Call (BC1C).",
        styles,
    ))

    story.append(_section("Reporting", styles))
    story.append(_body(
        "Upon completion of fieldwork, GPR Surveys Inc. will provide a stamped and certified summary report "
        "outlining all subsurface findings, utility designations, and scan results. Reports are delivered "
        "electronically in PDF format within 3–5 business days of site completion unless otherwise agreed. "
        "CAD drawings of utility designations can be provided as an optional deliverable upon request.",
        styles,
    ))

    story.append(_section("Billing", styles))
    story.append(_body(
        "A purchase order (PO) number is required prior to mobilization unless prior arrangements have been "
        "made. Invoices will be issued upon project completion and are payable within 30 days of receipt. "
        "Projects requiring mobilization from Victoria, BC may be subject to travel and accommodation costs "
        "not included in this proposal.",
        styles,
    ))

    story.append(_section("Safety & Liability", styles))
    story.append(_body(
        "GPR Surveys Inc. carries comprehensive general liability insurance (minimum $2,000,000 per "
        "occurrence) and WorkSafeBC coverage for all field personnel. Clients are responsible for ensuring "
        "site access, locating all private utilities, and maintaining a safe work environment. GPR Surveys "
        "Inc. is not liable for damages resulting from undisclosed or previously unlocated utilities. All "
        "field personnel complete site-specific orientations as required.",
        styles,
    ))

    return story


def _page4(styles):
    """Provisions — Access, Traffic, Working Hours."""
    story = []

    story.append(_section("Provisions", styles))
    story.append(Spacer(1, 0.06 * inch))

    story.append(Paragraph("<b>Access Requirements</b>", styles["Label"]))
    story.append(_body(
        "The client or site manager is responsible for providing safe and unobstructed access to all areas "
        "identified for GPR scanning or utility locating. Vehicle access to within 50 m of the work zone is "
        "preferred. Site personnel should be notified of the GPR survey in advance. Locked gates, restricted "
        "areas, or permit requirements must be disclosed and arranged by the client prior to mobilization.",
        styles,
    ))

    story.append(Paragraph("<b>Traffic Management</b>", styles["Label"]))
    story.append(_body(
        "If work is to be performed in or adjacent to active traffic lanes, the client is responsible for "
        "providing a traffic management plan (TMP) and flagging personnel in accordance with WorkSafeBC "
        "regulations and the Manual of Standard Traffic Signs and Pavement Markings (MOTI). GPR Surveys Inc. "
        "technicians will not work in traffic without adequate traffic control in place. Additional costs "
        "associated with traffic management are not included in this proposal unless explicitly stated.",
        styles,
    ))

    story.append(Paragraph("<b>Working Hours</b>", styles["Label"]))
    story.append(_body(
        "This proposal assumes standard working hours of 7:00 AM to 5:00 PM, Monday through Friday. Work "
        "performed outside these hours, including weekends, holidays, or overnight shifts, may be subject to "
        "overtime rates. Any deviation from standard hours must be agreed upon in writing prior to "
        "mobilization. GPR Surveys Inc. reserves the right to reschedule fieldwork due to unsafe site "
        "conditions, weather, or client-related delays.",
        styles,
    ))

    story.append(Spacer(1, 0.15 * inch))
    story.append(_body(
        "This proposal is valid for 30 days from the date of issue. Should you have any questions or "
        "require clarification on any items contained herein, please do not hesitate to contact us.",
        styles,
    ))

    return story


def _page5(contact, quote_data, styles):
    """Client Authorization & Quote Approval."""
    story = []

    story.append(_section("Client Authorization & Quote Approval", styles))
    story.append(_body(
        "By signing below, the Client acknowledges that they have read, understood, and accepted the terms "
        "and conditions outlined in this proposal. The undersigned authorizes GPR Surveys Inc. to proceed "
        "with the described scope of work at the quoted price.",
        styles,
    ))
    story.append(Spacer(1, 0.25 * inch))

    client = quote_data.get("client", {})
    is_blank = quote_data.get("is_blank", False)

    client_name    = client.get("name", "")   if not is_blank else ""
    client_title   = client.get("title", "")  if not is_blank else ""
    client_company = client.get("company", "") if not is_blank else ""

    def _sig_line(label, value=""):
        line_data = [
            [
                Paragraph(f"<b>{label}:</b>", styles["Label"]),
                Paragraph(value, styles["Value"]),
            ]
        ]
        t = Table(line_data, colWidths=[1.6 * inch, 4.8 * inch])
        t.setStyle(TableStyle([
            ("LINEBELOW", (1, 0), (1, 0), 0.5, LIGHT_GRAY),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        return t

    story.append(Paragraph("<b>CLIENT</b>", styles["Label"]))
    story.append(Spacer(1, 0.06 * inch))
    story.append(_sig_line("Full Name", client_name))
    story.append(_sig_line("Title", client_title))
    story.append(_sig_line("Company", client_company))
    story.append(_sig_line("PO Number", ""))
    story.append(_sig_line("Signature", ""))
    story.append(_sig_line("Date", ""))

    story.append(Spacer(1, 0.35 * inch))
    story.append(HRFlowable(width="100%", thickness=0.5, color=LIGHT_GRAY))
    story.append(Spacer(1, 0.2 * inch))

    story.append(Paragraph("<b>GPR SURVEYS INC.</b>", styles["Label"]))
    story.append(Spacer(1, 0.06 * inch))
    story.append(_sig_line("Authorized By", PREPARED_BY["name"]))
    story.append(_sig_line("Title", PREPARED_BY["title"]))
    story.append(_sig_line("Date", ""))

    story.append(Spacer(1, 0.25 * inch))
    story.append(_body(
        "Thank you for considering GPR Surveys Inc. for your subsurface investigation needs. "
        "We look forward to the opportunity to work with you.",
        styles,
    ))

    return story


# ─── Main entry point ─────────────────────────────────────────────────────────

def run(payload: dict) -> dict:
    contact        = payload.get("contact", {})
    quote_data     = payload.get("quote_data", {})
    site_image_url = payload.get("site_image_url")

    styles = _build_styles()
    buf    = io.BytesIO()

    doc = SimpleDocTemplate(
        buf,
        pagesize=LETTER,
        leftMargin=MARGIN_L,
        rightMargin=MARGIN_R,
        topMargin=MARGIN_T,
        bottomMargin=MARGIN_B,
    )
    doc._total_pages = 5

    story = []
    story += _page1(contact, quote_data, styles)
    story.append(PageBreak())
    story += _page2(quote_data, site_image_url, styles)
    story.append(PageBreak())
    story += _page3(styles)
    story.append(PageBreak())
    story += _page4(styles)
    story.append(PageBreak())
    story += _page5(contact, quote_data, styles)

    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)

    pdf_bytes = buf.getvalue()
    return {"pdf_bytes": base64.b64encode(pdf_bytes).decode("utf-8")}


if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv
    load_dotenv()

    payload = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {
        "contact": {
            "quote_number": "Q26001",
            "first_name": "John",
            "last_name": "Smith",
            "company": "Stantec Consulting",
            "email": "jsmith@stantec.com",
            "phone": "(604) 555-0100",
        },
        "quote_data": {
            "client": {
                "name": "John Smith",
                "title": "Project Manager",
                "company": "Stantec Consulting",
                "email": "jsmith@stantec.com",
                "phone": "(604) 555-0100",
            },
            "project_description": "A subsurface utility survey will be conducted on or near 123 Main St, Vancouver BC.",
            "line_items": [
                {"description": "Utility Locates & GPR Scanning", "unit": "LS", "quantity": 1, "amount": 575.00},
                {"description": "Report & Stamp", "unit": "LS", "quantity": 1, "amount": 150.00},
            ],
            "total": 725.00,
            "show_gst": True,
            "is_blank": False,
        },
        "site_image_url": None,
    }

    result = run(payload)
    out_path = "/tmp/test_quote.pdf"
    with open(out_path, "wb") as f:
        f.write(base64.b64decode(result["pdf_bytes"]))
    print(f"PDF written to {out_path}")
