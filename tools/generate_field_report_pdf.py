"""
Generate a branded GPR field report PDF using reportlab.

Input payload:
  {
    "report_data": { ... },   # see plan for full schema
    "photos":      [{"url": str, "caption": str}]
  }

Output: { "pdf_bytes": "<base64>" }

Page structure:
  1  — Cover
  2  — Site Info & Equipment
  3  — Utilities Located Matrix + Depths Matrix
  4  — Recommendations & Findings (embeds type_of_facilty.png + Certification_stamp.jpg)
  5  — Disclaimer, Equipment Specs, Prior to Breaking Ground
  6+ — Site Photos (one per page)
  N  — Technician Sign-off
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
from reportlab.lib import colors


# ─── Constants ────────────────────────────────────────────────────────────────

PAGE_W, PAGE_H = LETTER
MARGIN_L = 0.75 * inch
MARGIN_R = 0.75 * inch
MARGIN_T = 1.1 * inch
MARGIN_B = 0.9 * inch

BLUE       = HexColor("#1F4E79")
GOLD       = HexColor("#C9A84C")
DARK       = HexColor("#0a0a0a")
MID_GRAY   = HexColor("#555555")
LIGHT_GRAY = HexColor("#DDDDDD")
ROW_ALT    = HexColor("#F5F5F5")

FONT_BOLD   = "Helvetica-Bold"
FONT_NORMAL = "Helvetica"

ASSETS_DIR       = os.path.join(os.path.dirname(__file__), "assets")
LOGO_PATH        = os.path.join(ASSETS_DIR, "gpr_logo.png")
CERT_CCGA_PATH   = os.path.join(ASSETS_DIR, "CCGALogo.jpg")
CERT_BC1C_PATH   = os.path.join(ASSETS_DIR, "BC1C-logo-300w-2.webp")
CERT_WSBC_PATH   = os.path.join(ASSETS_DIR, "3-worksafebc-logo-col.jpg")
CERT_STAMP_PATH  = os.path.join(ASSETS_DIR, "Certification_stamp.jpg")
FACILITY_PATH    = os.path.join(ASSETS_DIR, "type_of_facilty.png")

UTILITY_ROWS = [
    "GAS", "Communication", "Electrical", "Water",
    "Storm", "Sanitary", "Street Lights", "Unknowns", "Other Anomalies",
]

SIGNAL_COLS = ["Strong Signal", "Average Signal", "Poor Signal", "Not Found", "Out of Scope"]
DEPTH_COLS  = ["0-0.3m", "0.3-0.6m", "0.6-1.0m", "1.0-1.4m", "1.4-1.8m", "1.8-2.2m", "≥2.2m"]


# ─── Image helpers ────────────────────────────────────────────────────────────

def _load_image(path: str):
    """Return ImageReader for reportlab, converting WebP to PNG if needed."""
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


def _load_image_from_url(url: str):
    """Download an image from URL, normalize to PNG via PIL, return BytesIO (for RLImage)."""
    import logging
    logger = logging.getLogger(__name__)
    try:
        import httpx
        resp = httpx.get(url, timeout=30, follow_redirects=True)
        resp.raise_for_status()
        raw = io.BytesIO(resp.content)
    except Exception as e:
        print(f"[field_report] photo download FAILED: {e}")
        logger.error(f"[field_report] photo download failed: {e}")
        return None

    try:
        from PIL import Image as PILImage
        raw.seek(0)
        pil_img = PILImage.open(raw)
        pil_img.load()  # Force full decode before closing source buffer

        # Resize to max 1600px on the longest side — keeps PDF file size reasonable
        MAX_PX = 1600
        w, h = pil_img.size
        if max(w, h) > MAX_PX:
            scale = MAX_PX / max(w, h)
            pil_img = pil_img.resize((int(w * scale), int(h * scale)), PILImage.LANCZOS)

        # Convert to RGB for JPEG (RGBA, palette modes, etc. → RGB)
        if pil_img.mode != "RGB":
            pil_img = pil_img.convert("RGB")

        out = io.BytesIO()
        pil_img.save(out, format="JPEG", quality=82, optimize=True)
        out.seek(0)
        return out  # BytesIO — RLImage accepts file-like objects
    except Exception as e:
        print(f"[field_report] photo PIL conversion FAILED: {e}")
        logger.error(f"[field_report] photo PIL conversion failed: {e}")
        return None


# ─── Styles ───────────────────────────────────────────────────────────────────

def _build_styles():
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle("Section", fontName=FONT_BOLD, fontSize=10,
        textColor=BLUE, spaceAfter=4, spaceBefore=10, leading=13, underline=1))
    styles.add(ParagraphStyle("Body", fontName=FONT_NORMAL, fontSize=9,
        textColor=black, leading=13, spaceAfter=4, alignment=TA_JUSTIFY))
    styles.add(ParagraphStyle("BodySmall", fontName=FONT_NORMAL, fontSize=8,
        textColor=MID_GRAY, leading=11, spaceAfter=3))
    styles.add(ParagraphStyle("Label", fontName=FONT_BOLD, fontSize=9,
        textColor=MID_GRAY, leading=12))
    styles.add(ParagraphStyle("Value", fontName=FONT_NORMAL, fontSize=9,
        textColor=black, leading=12))
    styles.add(ParagraphStyle("CoverTitle", fontName=FONT_BOLD, fontSize=20,
        leading=26, textColor=BLUE, alignment=TA_CENTER, spaceAfter=4))
    styles.add(ParagraphStyle("CoverSub", fontName=FONT_NORMAL, fontSize=12,
        textColor=MID_GRAY, alignment=TA_CENTER, spaceAfter=6))
    styles.add(ParagraphStyle("CaptionItalic", fontName="Helvetica-Oblique",
        fontSize=8, textColor=MID_GRAY, alignment=TA_CENTER, spaceAfter=6))
    styles.add(ParagraphStyle("TableHeader", fontName=FONT_BOLD, fontSize=8,
        textColor=white, alignment=TA_CENTER))
    styles.add(ParagraphStyle("TableCell", fontName=FONT_NORMAL, fontSize=8,
        textColor=black, alignment=TA_LEFT))
    styles.add(ParagraphStyle("TableCellCenter", fontName=FONT_NORMAL, fontSize=8,
        textColor=black, alignment=TA_CENTER))
    styles.add(ParagraphStyle("TableCellBold", fontName=FONT_BOLD, fontSize=8,
        textColor=black, alignment=TA_LEFT))
    styles.add(ParagraphStyle("PhotoCaption", fontName="Helvetica-Oblique",
        fontSize=9, textColor=MID_GRAY, alignment=TA_CENTER, spaceAfter=4))
    return styles


# ─── Header / Footer ──────────────────────────────────────────────────────────

def _on_page(canvas, doc):
    canvas.saveState()
    page_num = doc.page
    total    = getattr(doc, "_total_pages", 6)
    is_cover = page_num == 1

    if not is_cover:
        canvas.setStrokeColor(BLUE)
        canvas.setLineWidth(1.5)
        canvas.line(MARGIN_L, PAGE_H - 0.55 * inch, PAGE_W - MARGIN_R, PAGE_H - 0.55 * inch)

    logo_w = 1.96 * inch if is_cover else 1.4 * inch
    logo_h = 0.53 * inch if is_cover else 0.38 * inch

    if os.path.exists(LOGO_PATH):
        try:
            canvas.drawImage(LOGO_PATH, MARGIN_L, PAGE_H - 0.95 * inch,
                width=logo_w, height=logo_h, preserveAspectRatio=True, mask="auto")
        except Exception:
            pass

    canvas.setFont(FONT_BOLD, 10)
    canvas.setFillColor(BLUE)
    canvas.drawCentredString(PAGE_W / 2, PAGE_H - 0.45 * inch, "GPR SURVEYS INC")

    if os.path.exists(LOGO_PATH):
        try:
            canvas.drawImage(LOGO_PATH, PAGE_W - MARGIN_R - logo_w, PAGE_H - 0.95 * inch,
                width=logo_w, height=logo_h, preserveAspectRatio=True, mask="auto")
        except Exception:
            pass

    canvas.setStrokeColor(LIGHT_GRAY)
    canvas.setLineWidth(0.5)
    canvas.line(MARGIN_L, MARGIN_B - 0.12 * inch, PAGE_W - MARGIN_R, MARGIN_B - 0.12 * inch)

    cert_logos = [(CERT_CCGA_PATH, 0.9*inch), (CERT_BC1C_PATH, 0.9*inch), (CERT_WSBC_PATH, 1.1*inch)]
    spacing = 0.15 * inch
    total_logos_w = sum(w for _, w in cert_logos) + spacing * (len(cert_logos) - 1)
    x_pos = (PAGE_W - total_logos_w) / 2
    for cert_path, lw in cert_logos:
        img_src = _load_image(cert_path)
        if img_src is not None:
            try:
                canvas.drawImage(img_src, x_pos, 0.1*inch, width=lw, height=0.45*inch,
                    preserveAspectRatio=True, mask="auto")
                x_pos += lw + spacing
            except Exception:
                pass

    canvas.setFont(FONT_NORMAL, 8)
    canvas.setFillColor(MID_GRAY)
    canvas.drawRightString(PAGE_W - MARGIN_R, 0.3*inch, f"Page {page_num} of {total}")
    canvas.restoreState()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _section(title, styles):
    return Paragraph(f"<u><b>{title.upper()}</b></u>", styles["Section"])


def _body(text, styles):
    return Paragraph(text, styles["Body"])


def _hr():
    return HRFlowable(width="100%", thickness=0.5, color=LIGHT_GRAY, spaceAfter=6, spaceBefore=2)


def _fmt_date(date_str: str) -> str:
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%B %d, %Y")
    except Exception:
        return date_str or datetime.today().strftime("%B %d, %Y")


def _checkmark(value) -> str:
    if value is True or value == "Yes" or value == "yes":
        return "✓"
    if value is False or value == "No" or value == "no":
        return "✗"
    return "N/A"


def _yna_display(value: str) -> str:
    mapping = {"Yes": "Yes", "No": "No", "N/A": "N/A", "yes": "Yes", "no": "No", "n/a": "N/A"}
    return mapping.get(value, value or "N/A")


def _info_table(rows: list[tuple[str, str]], styles, col_w=(1.8*inch, 4.5*inch)):
    data = [[Paragraph(f"<b>{lbl}</b>", styles["Label"]),
             Paragraph(val or "—", styles["Value"])] for lbl, val in rows]
    t = Table(data, colWidths=list(col_w))
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.25, LIGHT_GRAY),
        ("BACKGROUND", (0, 0), (0, -1), HexColor("#EAF0F8")),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t


# ─── Page 1 — Cover ───────────────────────────────────────────────────────────

def _job_info_rows(rd: dict) -> list:
    """Return the 10-row job info list used on the cover/page 2."""
    return [
        ("Job Number",    rd.get("job_number", "")),
        ("Report Date",   _fmt_date(rd.get("report_date", ""))),
        ("Service",       rd.get("service", "")),
        ("Customer",      rd.get("customer_name", "")),
        ("Company",       rd.get("company", "")),
        ("Site Address",  rd.get("site_address", "")),
        ("PO Number",     rd.get("po_number", "")),
        ("BC1 Call #",    rd.get("bc1_call_number", "")),
        ("Technician",    rd.get("technician_name", "")),
        ("Time on Site",  rd.get("time_on_site", "")),
    ]


def _page1(rd: dict, styles, cover_photo: dict | None = None) -> list:
    """
    Page 1 — Cover.
    - With cover photo: title + subtitle + HR + large cover photo (fills most of page).
      Info table moves to top of page 2 (_page2 receives include_info_table=True).
    - Without cover photo: title + subtitle + HR + info table (original layout).
    """
    import logging
    story = []
    story.append(Spacer(1, 0.3*inch))
    story.append(Paragraph("FIELD SURVEY &amp; SUMMARY REPORT", styles["CoverTitle"]))
    story.append(Paragraph("Utility Locating &amp; Scanning", styles["CoverSub"]))
    story.append(HRFlowable(width="100%", thickness=2, color=BLUE, spaceAfter=12))

    if cover_photo:
        url = cover_photo.get("url", "")
        print(f"[cover_photo] url present: {bool(url)}, url prefix: {url[:80] if url else 'N/A'}")
        if url:
            img_src = _load_image_from_url(url)
            print(f"[cover_photo] img_src result: {type(img_src).__name__ if img_src is not None else 'None'}")
            if img_src:
                try:
                    # Large cover photo — fills most of the page (6.5 × 5.5 in)
                    img = RLImage(img_src, width=6.5*inch, height=5.5*inch, kind="bound")
                    story.append(img)
                    print(f"[cover_photo] RLImage created and appended OK")
                    cap = cover_photo.get("caption", "")
                    if cap:
                        story.append(Spacer(1, 0.1*inch))
                        story.append(Paragraph(cap, styles["PhotoCaption"]))
                except Exception as e:
                    print(f"[cover_photo] RLImage FAILED: {e}")
                    logging.getLogger(__name__).error(f"[field_report] cover photo RLImage failed: {e}")
        # Info table is NOT included here — it will appear at top of page 2
    else:
        print("[cover_photo] cover_photo is None/falsy — using no-cover layout")
        # No cover photo — include info table on page 1 (original behaviour)
        rows = _job_info_rows(rd)
        story.append(_info_table(rows, styles, col_w=(1.6*inch, 4.7*inch)))

    return story


# ─── Page 2 — Site Info & Equipment ───────────────────────────────────────────

def _page2(rd: dict, styles, include_info_table: bool = False) -> list:
    story = []

    if include_info_table:
        # Cover photo was on page 1 — prepend job info table here
        story.append(_section("Job Information", styles))
        rows = _job_info_rows(rd)
        story.append(_info_table(rows, styles, col_w=(1.6*inch, 4.7*inch)))
        story.append(Spacer(1, 0.12*inch))

    story.append(_section("Site Information", styles))
    rows = [
        ("Site Contact",    rd.get("site_contact_name", "")),
        ("Phone",           rd.get("site_contact_phone", "")),
        ("Traffic Control", _yna_display(rd.get("traffic_control", ""))),
    ]
    story.append(_info_table(rows, styles))
    story.append(Spacer(1, 0.08*inch))

    site_notes = rd.get("site_notes", "")
    if site_notes:
        story.append(_section("Site-Specific Notes", styles))
        story.append(_body(site_notes, styles))

    story.append(_section("Project Description & Scope", styles))
    story.append(_body(rd.get("project_scope", "Subsurface utility survey conducted on site."), styles))

    # Equipment deployed
    eq = rd.get("equipment_deployed", {})
    eq_map = [
        ("gpr",           "Ground Penetrating Radar (GPR)"),
        ("em",            "Electromagnetic Induction (EM)"),
        ("ferromagnetic", "Ferromagnetic Locator"),
        ("ductRodders",   "Detectable Duct Rodders"),
        ("videoCamera",   "Video Camera Inspection"),
    ]
    eq_items = [label for key, label in eq_map if eq.get(key)]
    other = (eq.get("other") or "").strip()
    if other:
        eq_items.append(f"Other: {other}")

    if eq_items:
        story.append(_section("Equipment Deployed", styles))
        for item in eq_items:
            story.append(Paragraph(f"• {item}", styles["Body"]))
        story.append(Spacer(1, 0.08*inch))

    return story


# ─── Page 3 — Utilities Located + Depths ──────────────────────────────────────

def _page3(rd: dict, styles) -> list:
    story = []

    utilities_signal = rd.get("utilities_signal", {})
    utilities_depth  = rd.get("utilities_depth", {})

    # Signal quality matrix
    story.append(_section("Utilities Located — Signal Quality", styles))
    header = [Paragraph("Utility", styles["TableHeader"])] + [
        Paragraph(c, styles["TableHeader"]) for c in SIGNAL_COLS
    ]
    sig_data = [header]
    for util in UTILITY_ROWS:
        val = utilities_signal.get(util, "")
        row = [Paragraph(util, styles["TableCell"])]
        for col in SIGNAL_COLS:
            row.append(Paragraph("✓" if val == col else "", styles["TableCellCenter"]))
        sig_data.append(row)

    col_w_sig = [1.5*inch] + [1.0*inch] * len(SIGNAL_COLS)
    t = Table(sig_data, colWidths=col_w_sig)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BLUE),
        ("TEXTCOLOR",  (0, 0), (-1, 0), white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [ROW_ALT, white]),
        ("GRID", (0, 0), (-1, -1), 0.25, LIGHT_GRAY),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
        ("ALIGN",  (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(t)

    signal_quality_remarks = rd.get("signal_quality_remarks", "")
    if signal_quality_remarks:
        story.append(Spacer(1, 0.1*inch))
        story.append(_section("Signal Quality Remarks", styles))
        story.append(_body(signal_quality_remarks, styles))

    story.append(Spacer(1, 0.15*inch))

    # Depth matrix — utilities_depth values may be list (multi-select) or str (legacy)
    story.append(_section("Average Utility Depths", styles))
    header2 = [Paragraph("Utility", styles["TableHeader"])] + [
        Paragraph(c, styles["TableHeader"]) for c in DEPTH_COLS
    ]
    dep_data = [header2]
    for util in UTILITY_ROWS:
        raw = utilities_depth.get(util, [])
        selected = raw if isinstance(raw, list) else ([raw] if raw else [])
        row = [Paragraph(util, styles["TableCell"])]
        for col in DEPTH_COLS:
            row.append(Paragraph("✓" if col in selected else "", styles["TableCellCenter"]))
        dep_data.append(row)

    col_w_dep = [1.5*inch] + [0.79*inch] * len(DEPTH_COLS)
    t2 = Table(dep_data, colWidths=col_w_dep)
    t2.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BLUE),
        ("TEXTCOLOR",  (0, 0), (-1, 0), white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [ROW_ALT, white]),
        ("GRID", (0, 0), (-1, -1), 0.25, LIGHT_GRAY),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 3),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 3),
        ("ALIGN",  (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTSIZE", (0, 0), (-1, 0), 7),
    ]))
    story.append(t2)

    depth_remarks = rd.get("depth_remarks", "")
    if depth_remarks:
        story.append(Spacer(1, 0.1*inch))
        story.append(_section("Remarks on Utilities Located and/or Anomalies", styles))
        story.append(_body(depth_remarks, styles))

    return story


# ─── Page 4 — Recommendations & Findings ──────────────────────────────────────

def _page4(rd: dict, styles) -> list:
    story = []

    story.append(_section("Recommendations & Findings", styles))

    rows = [
        ("Hydro Vacuum Recommended",         _yna_display(rd.get("hydro_vacuum", ""))),
        ("Areas Obstructed for GPR Scanning", _yna_display(rd.get("obstructed_areas", ""))),
    ]
    if rd.get("obstructed_areas") == "Yes" and rd.get("obstructed_notes"):
        rows.append(("Obstructed Area Notes", rd.get("obstructed_notes", "")))
    story.append(_info_table(rows, styles))
    story.append(Spacer(1, 0.08*inch))

    excavation = rd.get("excavation_recommendations", "")
    if excavation:
        story.append(_section("Excavation Recommendations", styles))
        story.append(_body(excavation, styles))

    conclusion = rd.get("project_conclusion", "")
    if conclusion:
        story.append(_section("Project Conclusion / Remarks", styles))
        story.append(_body(conclusion, styles))

    # Utility color legend
    if os.path.exists(FACILITY_PATH):
        story.append(Spacer(1, 0.15*inch))
        story.append(_section("Utility Color Legend", styles))
        try:
            img = RLImage(FACILITY_PATH, width=5.5*inch, height=2.5*inch, kind="proportional")
            story.append(img)
        except Exception:
            pass

    # Certification stamp
    if os.path.exists(CERT_STAMP_PATH):
        story.append(Spacer(1, 0.15*inch))
        try:
            img = RLImage(CERT_STAMP_PATH, width=2.5*inch, height=2.5*inch, kind="proportional")
            story.append(img)
        except Exception:
            pass

    return story


# ─── Page 5 — Disclaimer & Limitations (hardcoded) ───────────────────────────

def _page5(rd: dict, styles) -> list:
    story = []

    story.append(_section("Disclaimer & Limitations", styles))
    story.append(Spacer(1, 0.06*inch))

    # ── GPR Limitations ──
    story.append(Paragraph("<b>Ground Penetrating Radar (GPR) Limitations</b>", styles["Body"]))
    for bullet in [
        "GPR accuracy can be affected by soil composition, moisture levels, and subsurface conditions",
        "Depth estimates are approximate; GPR signals may be distorted by varying subsurface materials",
        "Non-metallic utilities (PVC, fiber optic, clay pipes) may not be detected unless backfilled "
        "materials support quality GPR data or accessible entry points (e.g., manholes) allow detection "
        "of duct rods/pigging",
        "Obstructions (e.g., packed vehicles, steel decks, metal frame, curbs, fence lines, walls, "
        "proximity to buildings) can reduce grid coverage and signal accuracy. We recommend removing "
        "obstacles wherever possible or accepting limited coverage and potential undetected areas.",
    ]:
        story.append(Paragraph(f"• {bullet}", styles["BodySmall"]))
    story.append(Spacer(1, 0.1*inch))

    # ── EM Limitations ──
    story.append(Paragraph("<b>Electromagnetic (EM) Locating Limitations</b>", styles["Body"]))
    for bullet in [
        "EM locators cannot detect non-conductive materials (e.g., plastic or clay pipes) unless "
        "accessible entry points are available for detectable rod/pigging",
        "Depth readings may be affected by stray interference, power lines, and soil conductivity variations",
        "Depth readings are estimates and should be confirmed with non-destructive methods",
    ]:
        story.append(Paragraph(f"• {bullet}", styles["BodySmall"]))
    story.append(Spacer(1, 0.14*inch))

    # ── Field Equipment Specifications ──
    story.append(_section("Field Equipment Specifications", styles))
    story.append(Spacer(1, 0.06*inch))

    # GPR System
    story.append(Paragraph("<b>Ground Penetrating Radar (GPR) System</b>", styles["Body"]))
    for line in [
        "• Model: GSSI SIR-4000",
        "• Antenna: 400 MHz shielded antenna (center frequency)",
        "• Depth Range: 2–3 meters (depending on soil conditions, conductivity, and moisture)",
        "• Applications: Mid-depth subsurface imaging for locating underground storage tanks (USTs), "
        "buried utilities, voids, and structural features",
        "• Key Features: Advanced digital signal processing, real-time data acquisition, GPS integration, "
        "and exportable georeferenced data",
    ]:
        story.append(Paragraph(line, styles["BodySmall"]))
    story.append(Spacer(1, 0.09*inch))

    # EM Locator
    story.append(Paragraph("<b>Electromagnetic (EM) Locator</b>", styles["Body"]))
    for line in [
        "• Model: Radio detection RD7200 (or similar)",
        "• Capabilities: Detection of conductive underground utilities, including metallic pipes, cables, "
        "and tracer wires",
        "• Operating Frequencies: Multiple active frequencies, passive power detection, and radio modes",
        "• Key Features: Precision locate mode, depth estimation, signal strength indication, and "
        "interference rejection",
    ]:
        story.append(Paragraph(line, styles["BodySmall"]))
    story.append(Spacer(1, 0.09*inch))

    # Ferromagnetic Locator
    story.append(Paragraph("<b>Ferromagnetic (FM) Locator</b>", styles["Body"]))
    for line in [
        "• Model: Schonstedt Maggie Magnetic Locator with Visual Display",
        "• Capabilities: Detects buried ferrous objects such as underground storage tanks (USTs), "
        "steel drums, valve boxes, manhole covers, and other iron or steel items",
        "• Depth Range: Up to ~4–5 meters, depending on object size and soil conditions",
        "• Key Features:",
        "    – High-sensitivity detection of ferrous materials",
        "    – Visual display with signal strength indicators",
    ]:
        story.append(Paragraph(line, styles["BodySmall"]))
    story.append(Spacer(1, 0.2*inch))

    # Certification logos (reuse footer logo rendering logic)
    cert_logos = [(CERT_CCGA_PATH, 0.9*inch), (CERT_BC1C_PATH, 0.9*inch), (CERT_WSBC_PATH, 1.1*inch)]
    logo_data = []
    for cert_path, lw in cert_logos:
        img_src = _load_image(cert_path)
        if img_src is not None:
            try:
                logo_data.append(RLImage(img_src, width=lw, height=0.5*inch, kind="proportional"))
            except Exception:
                pass
    if logo_data:
        row = Table([logo_data], colWidths=[1.2*inch, 1.2*inch, 1.4*inch])
        row.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(row)

    return story


# ─── Photo pages ──────────────────────────────────────────────────────────────

def _photo_pages(photos: list, styles) -> list:
    story = []
    for i, photo in enumerate(photos):
        url     = photo.get("url", "")
        caption = photo.get("caption", "")
        n       = i + 1
        total   = len(photos)

        story.append(_section(f"Site Photo {n} of {total}", styles))

        img_src = None
        if url:
            img_src = _load_image_from_url(url)

        if img_src:
            try:
                # Large — fills most of the portrait page (content area ~7.0 × 9.0 in)
                img = RLImage(img_src, width=6.8*inch, height=8.0*inch, kind="bound")
                story.append(img)
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"[field_report] RLImage failed: {e}")
                story.append(Paragraph("[Photo could not be loaded]", styles["CaptionItalic"]))
        else:
            story.append(Paragraph("[Photo not available]", styles["CaptionItalic"]))

        if caption:
            story.append(Paragraph(caption, styles["PhotoCaption"]))

        if i < total - 1:
            story.append(PageBreak())

    return story


# ─── Sign-off page ────────────────────────────────────────────────────────────

def _signoff_page(rd: dict, styles) -> list:
    story = []

    story.append(_section("Technician Sign-off", styles))
    story.append(_body(
        "The undersigned certifies that the information contained in this report is accurate and "
        "that the survey was performed in accordance with the applicable standards and site conditions "
        "described herein. This report is intended for the exclusive use of the named client and "
        "project, and should not be relied upon by any third party without written consent.",
        styles,
    ))
    story.append(Spacer(1, 0.25*inch))

    tech_name = rd.get("technician_name", "")
    report_date = _fmt_date(rd.get("report_date", ""))

    def _sig_line(label, value=""):
        data = [[Paragraph(f"<b>{label}:</b>", styles["Label"]),
                 Paragraph(value, styles["Value"])]]
        t = Table(data, colWidths=[1.8*inch, 4.5*inch])
        t.setStyle(TableStyle([
            ("LINEBELOW", (1, 0), (1, 0), 0.5, LIGHT_GRAY),
            ("TOPPADDING", (0, 0), (-1, -1), 12),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        return t

    story.append(_sig_line("Technician Name", tech_name))
    story.append(_sig_line("Signature", ""))
    story.append(_sig_line("Date", report_date))

    story.append(Spacer(1, 0.3*inch))
    story.append(_body(
        "Thank you for choosing GPR Surveys Inc. for your subsurface investigation needs. "
        "Please contact us at info@gprsurveys.ca or (250) 896-7576 with any questions.",
        styles,
    ))
    return story


# ─── Main entry point ─────────────────────────────────────────────────────────

def run(payload: dict) -> dict:
    rd          = payload.get("report_data", {})
    photos      = payload.get("photos", [])
    cover_photo = payload.get("cover_photo", None)  # {url, caption} | None
    print(f"[field_report] run() called — cover_photo present: {cover_photo is not None}, photos count: {len(photos)}")

    styles = _build_styles()
    buf    = io.BytesIO()

    # 5 fixed pages + 1 sign-off + N site photo pages (cover is on page 1, not a separate page)
    total_pages = 6 + len(photos)

    doc = SimpleDocTemplate(
        buf,
        pagesize=LETTER,
        leftMargin=MARGIN_L,
        rightMargin=MARGIN_R,
        topMargin=MARGIN_T,
        bottomMargin=MARGIN_B,
    )
    doc._total_pages = total_pages

    has_cover = bool(cover_photo and cover_photo.get("url"))

    story = []
    story += _page1(rd, styles, cover_photo=cover_photo)
    story.append(PageBreak())
    story += _page2(rd, styles, include_info_table=has_cover)
    story.append(PageBreak())
    story += _page3(rd, styles)
    story.append(PageBreak())
    story += _page4(rd, styles)
    story.append(PageBreak())
    story += _page5(rd, styles)
    story.append(PageBreak())
    story += _signoff_page(rd, styles)  # sign-off before site photos

    if photos:
        story.append(PageBreak())
        story += _photo_pages(photos, styles)  # site photos always last

    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)

    pdf_bytes = buf.getvalue()
    return {"pdf_bytes": base64.b64encode(pdf_bytes).decode("utf-8")}


if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv
    load_dotenv()

    payload = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {
        "report_data": {
            "job_number": "GPR-2601",
            "report_date": "2026-03-05",
            "service": "Utility Locating",
            "customer_name": "John Smith",
            "company": "Stantec Consulting",
            "site_address": "123 Main St, Victoria BC",
            "po_number": "PO-12345",
            "bc1_call_number": "BC1-000000",
            "technician_name": "Louis Gosselin",
            "time_on_site": "7:00 AM - 12:00 PM",
            "site_contact_name": "Jane Doe",
            "site_contact_phone": "(250) 555-0100",
            "project_scope": "Subsurface utility survey at 123 Main St.",
            "scan_method": "Combined GPR + EM",
            "surface_types": ["Concrete", "Asphalt"],
            "depth_of_investigation": "600mm, 150mm antenna",
            "traffic_control": "Yes",
            "confined_space": "No",
            "prior_to_breaking": "Yes",
            "site_notes": "Site was wet from overnight rain.",
            "gpr_equipment": {"GSSI StructureScan Mini XT": True},
            "em_equipment": {"Radiodetection RD8200 / RD7200": True},
            "frequencies": "400MHz, 900MHz",
            "work_performed": {
                "site_assessment": True, "bc1_confirmed": True, "safety_ppe": True,
                "equipment_calibrated": True, "scan_grid": True, "utilities_marked": True,
                "photos_taken": True, "reinspection": True, "area_safe": True,
            },
            "utilities_signal": {"GAS": "Strong Signal", "Electrical": "Average Signal", "Water": "Not Found"},
            "utilities_depth": {"GAS": "0.6-1.0m", "Electrical": "0.3-0.6m"},
            "depth_remarks": "Gas line at approximately 800mm depth.",
            "hydro_vacuum": "No",
            "obstructed_areas": "N/A",
            "obstructed_notes": "",
            "excavation_recommendations": "Hand-dig within 1m of all marked utilities.",
            "project_conclusion": "All accessible utilities located and marked.",
        },
        "photos": [],
    }

    result = run(payload)
    out_path = "/tmp/test_field_report.pdf"
    with open(out_path, "wb") as f:
        f.write(base64.b64decode(result["pdf_bytes"]))
    print(f"PDF written to {out_path}")
