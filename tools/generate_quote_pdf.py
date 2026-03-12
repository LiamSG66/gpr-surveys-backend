"""
Generate a branded PDF quote using reportlab.
Supports 4 template types: locate_single, dual_services, full_services, survey_single.

Input:  { contact: dict, quote_data: dict, site_image_url: str|None, template_type: str }
Output: { pdf_bytes: str }  — base64-encoded PDF bytes

Document structure (all templates):
  Cover page  — header + intro paragraph for template type
  Page 2      — Project Overview + Site Plan
  Scope       — flows naturally, content varies by template type
  Pricing     — table + deliverables (varies by template)
  Methodology / Qualifications / Billing / General Specs
  Authorization page
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
MARGIN_T = 1.2 * inch            # leaves room for larger header drawn in onPage
MARGIN_B = 0.9 * inch            # leaves room for footer

BLUE       = HexColor("#1F4E79")   # bold heading color
TEAL       = HexColor("#1F4E79")   # subheading color (matches BLUE for consistency)
ACCENT     = HexColor("#EBF2FA")   # light blue accent
DARK       = HexColor("#0a0a0a")
MID_GRAY   = HexColor("#555555")
LIGHT_GRAY = HexColor("#DDDDDD")

FONT_BOLD   = "Helvetica-Bold"
FONT_NORMAL = "Helvetica"

ASSETS_DIR     = os.path.join(os.path.dirname(__file__), "assets")
LOGO_PATH      = os.path.join(ASSETS_DIR, "gpr_logo.png")
CERT_CCGA_PATH = os.path.join(ASSETS_DIR, "CCGALogo.jpg")
CERT_BC1C_PATH = os.path.join(ASSETS_DIR, "BC1C-logo-300w-2.webp")
CERT_WSBC_PATH = os.path.join(ASSETS_DIR, "3-worksafebc-logo-col.jpg")

PREPARED_BY = {
    "name":    "Louis Gosselin",
    "title":   "Managing Partner",
    "email":   "lg@gprsurveys.ca",
    "phone":   "(250) 896-7576",
    "website": "www.gprsurveys.ca",
    "company": "GPR Surveys Inc.",
}


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


# ─── Styles ───────────────────────────────────────────────────────────────────

def _build_styles():
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        "SectionHeading",
        fontName=FONT_BOLD,
        fontSize=10,
        textColor=BLUE,
        spaceAfter=6,
        spaceBefore=12,
        leading=13,
    ))
    styles.add(ParagraphStyle(
        "SubHeading",
        fontName=FONT_BOLD,
        fontSize=9,
        textColor=TEAL,
        spaceAfter=3,
        spaceBefore=8,
        leading=13,
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
    # "Bullet" exists in reportlab's default stylesheet — remove before overriding
    if "Bullet" in styles.byName:
        del styles.byName["Bullet"]
    styles.add(ParagraphStyle(
        "Bullet",
        fontName=FONT_NORMAL,
        fontSize=9,
        textColor=black,
        leading=13,
        spaceAfter=2,
        leftIndent=12,
    ))
    styles.add(ParagraphStyle(
        "RomanItem",
        fontName=FONT_NORMAL,
        fontSize=9,
        textColor=black,
        leading=13,
        spaceAfter=4,
        leftIndent=28,
        firstLineIndent=-28,
        alignment=TA_JUSTIFY,
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
    styles.add(ParagraphStyle(
        "AuthTitle",
        fontName=FONT_BOLD,
        fontSize=14,
        textColor=BLUE,
        alignment=TA_CENTER,
        spaceAfter=10,
        spaceBefore=6,
        leading=18,
    ))
    styles.add(ParagraphStyle(
        "TealLabel",
        fontName=FONT_BOLD,
        fontSize=9,
        textColor=TEAL,
        leading=13,
        spaceAfter=4,
    ))
    return styles


# ─── Header / Footer (drawn per page via canvas callback) ─────────────────────

def _on_page(canvas, doc):
    canvas.saveState()
    page_num = doc.page
    total    = getattr(doc, "_total_pages", 99)
    is_cover = page_num == 1

    # ── Top accent strip on all pages ──
    canvas.setFillColor(BLUE)
    canvas.rect(0, PAGE_H - 0.055 * inch, PAGE_W, 0.055 * inch, fill=1, stroke=0)

    # ── Logo dimensions — square bounding box matches actual square logo image ──
    # Using logo_w = logo_h prevents ReportLab from centering the image inside a
    # wider box, which was causing logos to appear ~1.3" from the edge instead of
    # flush with the page margin.
    logo_h = 0.81 * inch if is_cover else 0.76 * inch
    logo_w = logo_h                                                  # logo is square
    logo_y = PAGE_H - (1.04 * inch if is_cover else 0.95 * inch)   # y = bottom of logo

    logo_margin = 0.25 * inch

    # ── Logo left ──
    if os.path.exists(LOGO_PATH):
        try:
            canvas.drawImage(
                LOGO_PATH,
                logo_margin, logo_y,
                width=logo_w, height=logo_h,
                preserveAspectRatio=True, mask="auto",
            )
        except Exception:
            pass

    # ── Company name centred ──
    canvas.setFont(FONT_BOLD, 15 if is_cover else 11)
    canvas.setFillColor(BLUE)
    canvas.drawCentredString(PAGE_W / 2, PAGE_H - 0.52 * inch, "GPR SURVEYS INC")

    # ── Cover: PROFESSIONAL SERVICES PROPOSAL subtitle ──
    if is_cover:
        canvas.setFont(FONT_BOLD, 16)
        canvas.setFillColor(TEAL)
        canvas.drawCentredString(PAGE_W / 2, PAGE_H - 0.86 * inch, "PROFESSIONAL SERVICES PROPOSAL")

    # ── Logo right ──
    if os.path.exists(LOGO_PATH):
        try:
            canvas.drawImage(
                LOGO_PATH,
                PAGE_W - logo_margin - logo_w, logo_y,
                width=logo_w, height=logo_h,
                preserveAspectRatio=True, mask="auto",
            )
        except Exception:
            pass

    # ── Header separator line — non-cover only, placed BELOW logos ──
    if not is_cover:
        canvas.setStrokeColor(BLUE)
        canvas.setLineWidth(2.0)
        canvas.line(MARGIN_L, PAGE_H - 1.08 * inch, PAGE_W - MARGIN_R, PAGE_H - 1.08 * inch)

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
    for cert_path, lw in cert_logos:
        img_src = _load_image_path_or_bytes(cert_path)
        if img_src is not None:
            try:
                canvas.drawImage(
                    img_src,
                    x_pos, 0.1 * inch,
                    width=lw, height=0.45 * inch,
                    preserveAspectRatio=True, mask="auto",
                )
                x_pos += lw + spacing
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


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _section(title, styles):
    """Bold black section heading (SCOPE, PRICING DETAILS, etc.)."""
    return Paragraph(f"<b>{title.upper()}</b>", styles["SectionHeading"])


def _subheading(title, styles):
    """Blue/teal subheading (Geophysical Utility Locating, etc.)."""
    return Paragraph(f"<b>{title}</b>", styles["SubHeading"])


def _body(text, styles):
    return Paragraph(text, styles["Body"])


def _bullet(text, styles):
    return Paragraph(f"&#x25CF; {text}", styles["Bullet"])


def _roman(numeral, text, styles):
    return Paragraph(f"{numeral}. {text}", styles["RomanItem"])


def _hr():
    return HRFlowable(width="100%", thickness=0.5, color=LIGHT_GRAY, spaceAfter=6, spaceBefore=4)


def _fmt_date(date_str: str) -> str:
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%B %d, %Y")
    except Exception:
        return date_str or datetime.today().strftime("%B %d, %Y")


# ─── Intro paragraphs by template type ───────────────────────────────────────

_INTRO = {
    "locate_single": (
        "GPR Surveys Inc. will perform a subsurface utility investigation utilizing Ground Penetrating Radar "
        "(GPR) and electromagnetic (EM) locating technologies to identify and designate underground "
        "infrastructure within the project limits. Utilities will be surveyed and labelled according to "
        "ASCE 38-02 Quality Level B (QL-B) standards. This estimate has been prepared based on the project "
        "information currently available and reflects the anticipated scope of work and site conditions. "
        "The site location and survey limits are illustrated on the attached site plan(s)."
    ),
    "dual_services": (
        "GPR Surveys Inc. will perform a subsurface utility investigation utilizing Ground Penetrating Radar "
        "(GPR) and electromagnetic (EM) locating technologies to identify and designate underground "
        "infrastructure within the project limits. Located utilities will be marked on site and digitally "
        "recorded. Survey data will be compiled and delivered in AutoCAD, Civil 3D (DWG), and PDF formats. "
        "This estimate has been prepared based on the project information currently available and reflects "
        "the anticipated scope of work and site conditions. The site location and survey limits are "
        "illustrated on the attached site plan(s)."
    ),
    "full_services": (
        "GPR Surveys Inc. will perform a subsurface utility investigation utilizing Ground Penetrating Radar "
        "(GPR) and electromagnetic (EM) locating technologies to identify and designate underground "
        "infrastructure within the project limits. Located utilities will be marked on site and digitally "
        "recorded for integration with the associated topographical survey. Survey data will be compiled and "
        "delivered in AutoCAD, Civil 3D (DWG), and PDF formats. This estimate has been prepared based on "
        "the project information currently available and reflects the anticipated scope of work and site "
        "conditions. The site location and survey limits are illustrated on the attached site plan(s)."
    ),
    "survey_single": (
        "GPR Surveys Inc. will perform a topographical survey using a robotic total station and/or GNSS RTK "
        "equipment with SmartNet network corrections. Survey data will be compiled and delivered in AutoCAD, "
        "Civil 3D (DWG), and PDF formats. This estimate has been prepared based on the project information "
        "currently available and reflects the anticipated scope of work and site conditions. The site "
        "location and survey limits are illustrated on the attached site plan(s)."
    ),
}

_SCOPE_OPENING = {
    "locate_single": (
        "Where relevant utilities or surface features are located slightly outside the project limits but "
        "are considered important to the work, they may also be collected and documented. Examples include "
        "manholes, culverts (inlets/outlets), utility vaults, and other features supporting the design."
    ),
    "dual_services": (
        "Where relevant utilities or surface features are located slightly outside the project limits but "
        "are considered important to the work, they may also be collected and documented. Examples include "
        "manholes, culverts (inlets/outlets), utility vaults, and other features supporting the design."
    ),
    "full_services": (
        "Where relevant utilities or surface features are located slightly outside the project limits but "
        "are considered important to the work, they may also be collected and documented. Examples include "
        "manholes, culverts (inlets/outlets), utility vaults, and other features supporting the design."
    ),
    "survey_single": (
        "Where relevant surface features are located slightly outside the project limits but are considered "
        "important to the work, they may also be collected and documented. Examples include manholes, "
        "culverts (inlets/outlets), utility vaults, and other features supporting the design."
    ),
}

_SCOPE_INTRO_SENTENCE = {
    "locate_single": "The subsurface survey will include:",
    "dual_services":  "The subsurface utility survey will include:",
    "full_services":  "The subsurface and topographical survey will include:",
    "survey_single":  "The topographical survey will include:",
}


# ─── Bullet data ──────────────────────────────────────────────────────────────

_SUBSURFACE_BULLETS = [
    (
        "SUBSURFACE UTILITY INFORMATION",
        None,  # top-level heading with no bullets of its own
    ),
    (
        "Geophysical Utility Locating",
        [
            "Ground Penetrating Radar (GPR) utility locating",
            "Electromagnetic (EM) utility locating",
            "Detection of metallic and non-metallic underground utilities",
            "Identification of abandoned or unknown underground utilities where detectable",
        ],
    ),
    (
        "Pipe Tracing & Internal Inspection",
        [
            "Detectable duct rodder deployment to trace non-conductive utilities.",
            "Video inspection camera deployment where accessible to verify pipe alignments. (TBC)",
            "Confirmation of pipe direction and utility routing through accessible infrastructure",
        ],
    ),
    (
        "Utility Alignment & Position",
        [
            "Horizontal alignment of underground utilities",
            "Verification of utility crossings and intersections where identifiable",
            "Identification of utility corridors within the project limits",
        ],
    ),
    (
        "Utility Depth & Physical Characteristics",
        [
            "Utility depth measurements with corresponding ground surface elevations",
            "Pipe invert elevations where accessible",
            "Pipe diameters and material types where identifiable",
            "EM and GPR Depth where conditions permit detection",
        ],
    ),
    (
        "Surface Features Associated with Utilities",
        [
            "Fire hydrants",
            "Manholes and maintenance holes",
            "Catch basins and storm inlets",
            "Valve boxes and gate valves",
            "Utility vaults and access chambers",
            "Cleanouts and service connections",
            "Overhead service drop",
        ],
    ),
]

_SURVEY_INTEGRATION_BULLETS = [
    "Utility designation markings referenced to surveyed control points",
    "Correlation of located utilities with visible surface infrastructure",
]

_TOPOGRAPHIC_BULLETS = [
    (
        "Ground Surface & Terrain",
        [
            "Ground elevations",
            "Terrain breaklines",
            "Top and toe of slopes",
            "Ditches and drainage swales",
            "Culverts and drainage structures",
        ],
    ),
    (
        "Roadway & Transportation Features",
        [
            "Edge of pavement",
            "Edge of gravel or travelled surface",
            "Road crown alignment",
            "Driveway crossings",
            "Curb and gutter, back of curb",
            "Sidewalk edges & accessible ramps",
        ],
    ),
    (
        "Pavement Markings",
        [
            "Centerline and directional arrows",
            "Bike lane markings",
            "Stop lines and pedestrian crossings",
            "Parking stall delineation",
            "Accessible parking",
            "EV charging station",
        ],
    ),
    (
        "Surface Infrastructure",
        [
            "Buildings",
            "Road signage & street furniture",
            "Guardrails, fences, retaining walls",
            "Light standards and poles",
            "Bollards and barriers",
        ],
    ),
    (
        "Vegetation",
        [
            "Trees (species where identifiable)",
            "Tree canopy extent",
            "Diameter at breast height (DBH)",
            "Shrubs and significant vegetation",
            "Protected species such as Garry oak and arbutus.",
        ],
    ),
    (
        "Drainage & Utility Surface Features",
        [
            "Catch basins and storm inlets",
            "Manholes and utility lids",
            "Valve boxes and gate valves",
            "Fire hydrants",
            "Cleanouts and access chambers",
            "Utility pedestals and cabinets",
        ],
    ),
]

_DELIVERABLES_I_TO_V = [
    (
        "I",
        "Existing utility records obtained through BC One Call notifications and available GIS datasets "
        "will be reviewed prior to field deployment.",
    ),
    (
        "II",
        "Ground Penetrating Radar (GPR) scanning and electromagnetic (EM) locating will be performed to "
        "identify and designate underground utilities within the project limits, including municipal, "
        "third-party, private, and potentially abandoned or unknown services.",
    ),
    (
        "III",
        "Utility depths will be recorded at strategic locations, with pipe inverts, diameters, and material "
        "types documented where accessible to support design and profile development.",
    ),
    (
        "IV",
        "Field markings will meet ASCE 38-02 Quality Level B (QL-B) standards, designating underground "
        "utilities through surface geophysical methods such as Ground Penetrating Radar (GPR) and "
        "electromagnetic (EM) locating.",
    ),
    (
        "V",
        "Site findings will be labeled using the CSA / ANSI standardized utility color-coding system and "
        "identified using non-permanent surface markings such as spray paint, pin flags, whiskers, or "
        "offset stakes, as appropriate for site conditions.",
    ),
]

_DELIVERABLE_VI_A = (
    "VI",
    "Subsurface findings will be surveyed and incorporated into the project dataset, allowing utilities to "
    "be mapped and delivered in digital formats compatible with engineering and design workflows.",
)

_DELIVERABLE_VI_B = (
    "VI",
    "Subsurface findings will be surveyed and incorporated into the project topographic dataset, allowing "
    "utilities to be mapped and delivered in digital formats compatible with engineering and design workflows.",
)

_AUTOCAD_DELIVERABLES = [
    (
        "VII",
        "Survey point files provided in UTM Zone 10N (NAD83) coordinates, referenced to established project "
        "control points and/or local Geodetic Control Monuments (GCMs), with elevations referenced to CGVD28.",
    ),
    (
        "VIII",
        "Project control points established during the survey will be provided and may remain available on "
        "site, where practical, to allow future survey work to tie into the same control network.",
    ),
    (
        "IX",
        "AutoCAD drawing showing all identified subsurface utilities and surveyed surface features, using "
        "standard engineering layers, line types, symbols, and labeling conventions.",
    ),
    (
        "X",
        "Utility attributes and elevations, including available depth information, surface elevations, and "
        "surveyed feature points associated with located infrastructure.",
    ),
    (
        "XI",
        "CSV point file containing point number, northing, easting, elevation, and feature codes.",
    ),
    (
        "XII",
        "Digital deliverables compatible with AutoCAD and Civil 3D formats for integration into engineering "
        "design workflows.",
    ),
    (
        "XIII",
        "PDF drawing package illustrating all subsurface findings and surveyed features, overlaid on current "
        "aerial imagery for spatial reference.",
    ),
]


# ─── Cover page ───────────────────────────────────────────────────────────────

def _cover_page(contact, quote_data, template_type, styles):
    story = []

    quote_number = contact.get("quote_number", "Q00001")
    date_str     = _fmt_date(datetime.today().strftime("%Y-%m-%d"))

    client   = quote_data.get("client", {})
    is_blank = quote_data.get("is_blank", False)

    proj_name = quote_data.get("project_name") or quote_data.get("project_description") or "[PROJECT NAME]"

    story.append(Spacer(1, 0.1 * inch))

    # Date + Ref line
    story.append(Paragraph(
        f"<b>Date:</b> {date_str}&nbsp;&nbsp;&nbsp;&nbsp;<b>Ref:</b> {quote_number}",
        styles["Label"],
    ))
    story.append(_hr())

    # PREPARED FOR
    story.append(Spacer(1, 0.06 * inch))
    story.append(Paragraph("<b>PREPARED FOR</b>", styles["SectionHeading"]))

    if is_blank:
        prepared_lines = ["[CLIENT NAME]", "[TITLE]", "[COMPANY]", "[EMAIL]", "[PHONE]"]
    else:
        name = (
            client.get("name")
            or f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip()
        )
        prepared_lines = [
            name,
            client.get("title", contact.get("contact_title", "")),
            client.get("company", contact.get("company", "")),
            client.get("email", contact.get("email", "")),
            client.get("phone", contact.get("phone", "")),
        ]

    for line in prepared_lines:
        if line:
            story.append(Paragraph(line, styles["PreparedFor"]))

    story.append(Spacer(1, 0.12 * inch))

    # RE: field — admin-provided or falls back to project name
    re_text = quote_data.get("re_field") or proj_name
    story.append(Paragraph(f"<b>RE:</b> {re_text}", styles["Body"]))
    story.append(_hr())

    # Template-specific intro paragraph
    intro = _INTRO.get(template_type, _INTRO["locate_single"])
    story.append(_body(intro, styles))
    story.append(_hr())

    story.append(_hr())
    story.append(Spacer(1, 0.06 * inch))
    story.append(Paragraph("<b>PROPOSAL PREPARED BY</b>", styles["SectionHeading"]))
    by_lines = [
        f"{PREPARED_BY['name']} | {PREPARED_BY['title']}",
        PREPARED_BY["company"],
        PREPARED_BY["email"],
        PREPARED_BY["phone"],
        PREPARED_BY["website"],
    ]
    for line in by_lines:
        story.append(Paragraph(line, styles["PreparedFor"]))

    story.append(PageBreak())
    return story


# ─── Project overview page ────────────────────────────────────────────────────

def _project_overview_page(quote_data, site_image_data, styles):
    story = []

    # PROJECT OVERVIEW
    story.append(_section("Project Overview", styles))

    overview_items = quote_data.get("project_overview_items") or [
        quote_data.get("project_description", "[Project description not provided.]")
    ]
    for item in overview_items:
        if item:
            story.append(_body(item, styles))

    story.append(Spacer(1, 0.2 * inch))

    # SITE PLAN
    story.append(_section("Site Plan", styles))

    site_img_loaded = False
    if site_image_data:
        try:
            tmp = io.BytesIO(site_image_data)
            img = RLImage(tmp, width=6.5 * inch, height=5.5 * inch, kind="proportional")
            story.append(img)
            site_img_loaded = True
        except Exception:
            pass

    if not site_img_loaded:
        story.append(Paragraph("[SITE IMAGE — attach satellite/plan view]", styles["CaptionItalic"]))
        story.append(Spacer(1, 0.1 * inch))

    caption = quote_data.get("site_image_caption", "")
    if caption:
        story.append(Paragraph(f"<i>{caption}</i>", styles["CaptionItalic"]))

    story.append(PageBreak())
    return story


# ─── Scope section ────────────────────────────────────────────────────────────

def _scope_section(template_type, styles):
    story = []

    story.append(_section("Scope", styles))

    # Opening paragraph
    opening = _SCOPE_OPENING.get(template_type, _SCOPE_OPENING["locate_single"])
    story.append(_body(opening, styles))
    story.append(Spacer(1, 0.06 * inch))

    # Scope intro sentence
    intro_sentence = _SCOPE_INTRO_SENTENCE.get(template_type, _SCOPE_INTRO_SENTENCE["locate_single"])
    story.append(_body(intro_sentence, styles))
    story.append(Spacer(1, 0.06 * inch))

    if template_type in ("locate_single", "dual_services", "full_services"):
        # SUBSURFACE UTILITY INFORMATION
        for heading, bullets in _SUBSURFACE_BULLETS:
            if bullets is None:
                # Top-level colored heading
                story.append(_subheading(heading, styles))
            else:
                story.append(_subheading(heading, styles))
                for b in bullets:
                    story.append(_bullet(b, styles))

        # Survey Integration — full_services only
        if template_type == "full_services":
            story.append(_subheading("Survey Integration & Data Deliverables", styles))
            for b in _SURVEY_INTEGRATION_BULLETS:
                story.append(_bullet(b, styles))

    if template_type in ("full_services", "survey_single"):
        # TOPOGRAPHIC SURVEY FEATURES
        story.append(Spacer(1, 0.08 * inch))
        story.append(_subheading("TOPOGRAPHIC SURVEY FEATURES", styles))
        for heading, bullets in _TOPOGRAPHIC_BULLETS:
            story.append(_subheading(heading, styles))
            for b in bullets:
                story.append(_bullet(b, styles))

    elif template_type == "survey_single":
        # survey_single: scope intro + topographic only (already handled above)
        pass

    story.append(PageBreak())
    return story


# ─── Pricing + Deliverables ───────────────────────────────────────────────────

def _pricing_section(quote_data, template_type, styles):
    story = []

    story.append(_hr())
    story.append(_section("Pricing Details", styles))

    line_items = quote_data.get("line_items", [])

    # Fixed columns: Line | Description | Unit | Qty | Amount
    col_widths = [0.45 * inch, 3.55 * inch, 0.75 * inch, 0.75 * inch, 1.0 * inch]

    header = [
        Paragraph("Line",        styles["TableHeader"]),
        Paragraph("Description", styles["TableHeader"]),
        Paragraph("Unit",        styles["TableHeader"]),
        Paragraph("Qty",         styles["TableHeader"]),
        Paragraph("Amount",      styles["TableHeader"]),
    ]
    table_data = [header]

    total = 0.0
    for i, item in enumerate(line_items):
        desc_parts = item.get("description_parts")
        if desc_parts:
            desc_text = "<br/>".join(
                f"{chr(96 + j + 1)}) {part}" for j, part in enumerate(desc_parts)
            )
        else:
            desc_text = item.get("description", "")

        amount = item.get("amount", 0)
        total += amount

        row = [
            Paragraph(str(i + 1),         styles["TableCell"]),
            Paragraph(desc_text,           styles["TableCell"]),
            Paragraph(item.get("unit", "LS"), styles["TableCell"]),
            Paragraph(str(item.get("quantity", 1)), styles["TableCell"]),
            Paragraph(f"${amount:,.2f}",   styles["TableCellRight"]),
        ]
        table_data.append(row)

    # Total row — spans cols 0-3 with right-aligned label, col 4 amount
    total_label = Paragraph("Total excluding GST", styles["TableCellBold"])
    total_amt   = Paragraph(f"${total:,.2f}", styles["TableCellBold"])
    table_data.append(["", "", "", total_label, total_amt])

    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0),  (-1, 0),  BLUE),
        ("TEXTCOLOR",     (0, 0),  (-1, 0),  white),
        ("ROWBACKGROUNDS",(0, 1),  (-1, -2), [HexColor("#F5F5F5"), white]),
        ("BACKGROUND",    (0, -1), (-1, -1), HexColor("#EAF0F8")),
        ("GRID",          (0, 0),  (-1, -1), 0.25, LIGHT_GRAY),
        ("VALIGN",        (0, 0),  (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0),  (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0),  (-1, -1), 5),
        ("LEFTPADDING",   (0, 0),  (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0),  (-1, -1), 6),
        ("LINEBELOW",     (0, -2), (-1, -2), 1.5, BLUE),
        # Span label cell across cols 0-3 in total row
        ("SPAN",          (0, -1), (3, -1)),
        ("ALIGN",         (0, -1), (3, -1), "RIGHT"),
    ]))
    story.append(t)

    custom_notes = quote_data.get("custom_notes", "")
    if custom_notes:
        story.append(Spacer(1, 0.1 * inch))
        story.append(_body(custom_notes, styles))

    story.append(Spacer(1, 0.15 * inch))

    # SUBSURFACE DELIVERABLES
    story.append(_section("Subsurface Deliverables", styles))
    for num, text in _DELIVERABLES_I_TO_V:
        story.append(_roman(num, text, styles))

    # Item VI — version depends on template
    if template_type in ("locate_single", "dual_services"):
        num, text = _DELIVERABLE_VI_A
    else:
        num, text = _DELIVERABLE_VI_B
    story.append(_roman(num, text, styles))

    # AUTOCAD DELIVERABLES — dual_services, full_services, survey_single
    if template_type in ("dual_services", "full_services", "survey_single"):
        story.append(Spacer(1, 0.1 * inch))
        story.append(_section("AutoCAD Deliverables", styles))
        for num, text in _AUTOCAD_DELIVERABLES:
            story.append(_roman(num, text, styles))
        story.append(Spacer(1, 0.06 * inch))
        story.append(_body(
            "<b>Note:</b> Any property lines shown are for contextual purposes only and do not represent "
            "a legal boundary determination.",
            styles,
        ))

    story.append(PageBreak())
    return story


# ─── Methodology + Qualifications + Billing + General Specs ──────────────────

def _boilerplate_sections(styles):
    story = []

    # SURVEY METHODOLOGY
    story.append(_section("Survey Methodology", styles))
    story.append(_body(
        "GPR Surveys Inc. employs a multi-technology approach to subsurface investigations and "
        "infrastructure mapping. Our methodology combines Ground Penetrating Radar (GPR), electromagnetic "
        "(EM) locating equipment, detectable duct rodders, and ferromagnetic locating tools to identify "
        "and designate underground utilities.",
        styles,
    ))
    story.append(_body(
        "Field survey operations utilize a combination of high-precision robotic total stations and GNSS "
        "RTK positioning with access to SmartNet network correction services. This integrated approach "
        "allows survey-grade data collection in both open environments and locations where satellite "
        "reception may be limited, including dense urban corridors, construction sites, parkades, and "
        "heavily canopied areas.",
        styles,
    ))

    # PROFESSIONAL QUALIFICATIONS
    story.append(_section("Professional Qualifications", styles))
    story.append(_body(
        "All surveys, utility locating, and GPR services are conducted under the direction of geomatics "
        "professionals and certified locating and GPR technicians registered with the Applied Science "
        "Technologists and Technicians of British Columbia (ASTTBC). GPR Surveys Inc. utilizes calibrated, "
        "current-generation, high-precision equipment and applies a consultative approach to each project, "
        "from desktop review through to post-delivery support.",
        styles,
    ))

    # BILLING
    story.append(_section("Billing", styles))
    story.append(_body(
        "A detailed, itemized invoice referencing applicable project codes or purchase order numbers will "
        "be issued alongside the summary report, typically on the same day services are completed. Invoices "
        "will include secure payment options such as e-transfer, credit card, or ACH, with applicable taxes. "
        "Unless otherwise agreed upon in writing, standard payment terms are Net 30 from the date of invoice.",
        styles,
    ))

    # GENERAL SPECIFICATIONS
    story.append(_section("General Specifications", styles))

    story.append(_subheading("Access Requirements & Client Responsibilities", styles))
    story.append(_body(
        "The client is responsible for ensuring that all utility vaults, chambers, gas meter cages and "
        "access points are unlocked and accessible to GPR Surveys Inc.'s field crews at the time of survey.",
        styles,
    ))

    story.append(_subheading("Working Hours & Rate Conditions", styles))
    story.append(_body(
        "Unless agreed otherwise, this proposal is based on regular weekday daytime working hours. Work "
        "conducted outside of these hours, including evenings, weekends, or statutory holidays, will be "
        "subject to applicable after-hours or night shift rates in accordance with British Columbia "
        "Employment Standards. Additional charges may apply in the event of on-site delays, change orders, "
        "or scope modifications.",
        styles,
    ))

    story.append(_subheading("Liability & Health & Safety", styles))
    story.append(_body(
        "GPR Surveys Inc. certifies full compliance with WorkSafeBC regulations and maintains the following "
        "insurance coverage: $5 million in Commercial General Liability, $5 million in Professional "
        "Liability, and Cyber Liability.",
        styles,
    ))
    story.append(Spacer(1, 0.08 * inch))
    story.append(_body(
        "Our field operations follow strict industry safety protocols and regulatory guidelines to ensure "
        "the protection of our team, clients, and the public. This includes the implementation of safe "
        "work procedures, pre-site hazard assessments, and full adherence to BC One Call protocols, traffic "
        "control standards, and all relevant municipal and provincial regulations.",
        styles,
    ))

    return story


# ─── Authorization page ───────────────────────────────────────────────────────

def _authorization_page(contact, quote_data, styles):
    story = []

    story.append(PageBreak())

    # Large centered title
    story.append(Paragraph(
        "Client Authorization &amp; Quote Approval",
        styles["AuthTitle"],
    ))

    # Body paragraph
    story.append(_body(
        "By signing below, the client confirms acceptance of the quotation and authorizes GPR Surveys Inc. "
        "to proceed with the services as outlined in the attached proposal. This approval includes "
        "agreement to the scope of work, estimated costs, and terms and conditions provided.",
        styles,
    ))
    story.append(Spacer(1, 0.2 * inch))

    client   = quote_data.get("client", {})
    is_blank = quote_data.get("is_blank", False)

    client_name    = (client.get("name", "")    if not is_blank else "")
    client_title   = (client.get("title", "")   if not is_blank else "")
    client_company = (client.get("company", "") if not is_blank else "")

    def _sig_line(label, value=""):
        row = [[
            Paragraph(f"<b>{label}:</b>", styles["Label"]),
            Paragraph(value, styles["Value"]),
        ]]
        t = Table(row, colWidths=[1.8 * inch, 4.6 * inch])
        t.setStyle(TableStyle([
            ("LINEBELOW",     (1, 0), (1, 0), 0.5, LIGHT_GRAY),
            ("TOPPADDING",    (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        return t

    # Client representative
    story.append(Paragraph("Authorized Client Representative:", styles["TealLabel"]))
    story.append(_sig_line("Full Name",       client_name))
    story.append(_sig_line("Title/Position",  client_title))
    story.append(_sig_line("Company Name",    client_company))
    story.append(_sig_line("PO Number",       ""))
    story.append(_sig_line("Accounting Email",""))
    story.append(_sig_line("Signature",       ""))
    story.append(_sig_line("Date",            ""))

    story.append(Spacer(1, 0.25 * inch))
    story.append(_hr())
    story.append(Spacer(1, 0.15 * inch))

    # GPR Surveys Inc. section
    story.append(Paragraph("For GPR Surveys Inc.:", styles["TealLabel"]))
    story.append(_sig_line("Authorized Representative", PREPARED_BY["name"]))
    story.append(_sig_line("Title",     PREPARED_BY["title"]))
    story.append(_sig_line("Signature", ""))
    story.append(_sig_line("Date",      ""))

    story.append(Spacer(1, 0.25 * inch))
    story.append(_body(
        "GPR Surveys Inc. appreciates the opportunity to support this project. Should you have any "
        "questions regarding this proposal, or require further clarification, we would be pleased to "
        "review the scope, schedule, or deliverables with you in more detail.",
        styles,
    ))

    return story


# ─── Story builder ────────────────────────────────────────────────────────────

def _build_story(contact, quote_data, template_type, styles, site_image_data):
    story = []
    story += _cover_page(contact, quote_data, template_type, styles)
    story += _project_overview_page(quote_data, site_image_data, styles)
    story += _scope_section(template_type, styles)
    story += _pricing_section(quote_data, template_type, styles)
    story += _boilerplate_sections(styles)
    story += _authorization_page(contact, quote_data, styles)
    return story


# ─── Main entry point ─────────────────────────────────────────────────────────

def run(payload: dict) -> dict:
    try:
        template_type = (
            payload.get("template_type")
            or payload.get("quote_data", {}).get("template_type", "locate_single")
        )
        contact        = payload.get("contact", {})
        quote_data     = payload.get("quote_data", {})
        site_image_url = payload.get("site_image_url")

        # Pre-download site image once — reused in both passes
        site_image_data = None
        if site_image_url:
            import urllib.request
            try:
                with urllib.request.urlopen(site_image_url, timeout=10) as resp:
                    site_image_data = resp.read()
            except Exception:
                pass

        styles = _build_styles()

        def make_doc(buf):
            return SimpleDocTemplate(
                buf,
                pagesize=LETTER,
                leftMargin=MARGIN_L,
                rightMargin=MARGIN_R,
                topMargin=MARGIN_T,
                bottomMargin=MARGIN_B,
            )

        # Pass 1: get actual page count
        buf1 = io.BytesIO()
        doc1 = make_doc(buf1)
        doc1._total_pages = 99
        doc1.build(
            _build_story(contact, quote_data, template_type, styles, site_image_data),
            onFirstPage=_on_page,
            onLaterPages=_on_page,
        )
        total_pages = doc1.page

        # Pass 2: render with correct total
        buf2 = io.BytesIO()
        doc2 = make_doc(buf2)
        doc2._total_pages = total_pages
        doc2.build(
            _build_story(contact, quote_data, template_type, styles, site_image_data),
            onFirstPage=_on_page,
            onLaterPages=_on_page,
        )

        return {"pdf_bytes": base64.b64encode(buf2.getvalue()).decode("utf-8")}

    except Exception as exc:
        raise


# ─── CLI test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv
    load_dotenv()

    payload = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {
        "template_type": "locate_single",
        "contact": {
            "quote_number": "Q26001",
            "first_name":   "John",
            "last_name":    "Smith",
            "company":      "Stantec Consulting",
            "email":        "jsmith@stantec.com",
            "phone":        "(604) 555-0100",
        },
        "quote_data": {
            "client": {
                "name":    "John Smith",
                "title":   "Project Manager",
                "company": "Stantec Consulting",
                "email":   "jsmith@stantec.com",
                "phone":   "(604) 555-0100",
            },
            "project_name":        "Subsurface Utility Survey — 123 Main St, Vancouver BC",
            "project_description": "A subsurface utility survey will be conducted on or near 123 Main St, Vancouver BC.",
            "project_overview_items": [
                "Subsurface utility survey at 123 Main St, Vancouver BC.",
                "Survey limits: approximately 150 m of roadway and adjacent boulevard.",
                "Work is required to support upcoming watermain replacement design.",
            ],
            "site_image_caption": "Figure 1 — Project site location, 123 Main St, Vancouver BC.",
            "line_items": [
                {
                    "description": "Subsurface Utility Investigation — GPR & EM Locating",
                    "unit": "LS",
                    "quantity": 1,
                    "amount": 2800.00,
                },
                {
                    "description": "Field Report & Stamped Summary",
                    "unit": "LS",
                    "quantity": 1,
                    "amount": 350.00,
                },
            ],
            "custom_notes": "",
            "is_blank": False,
        },
        "site_image_url": None,
    }

    result = run(payload)
    if "error" in result:
        print(f"ERROR: {result['error']}")
        sys.exit(1)
    out_path = "/tmp/test_quote.pdf"
    with open(out_path, "wb") as f:
        f.write(base64.b64decode(result["pdf_bytes"]))
    print(f"PDF written to {out_path}")
