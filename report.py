import io
import random
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
                                Image as RLImage, PageBreak)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

BRAND = colors.HexColor("#7c2d12")      # deep ember
LIGHT = colors.HexColor("#fff7ed")
GREEN = colors.HexColor("#15803d")
RED = colors.HexColor("#b91c1c")
GREY = colors.HexColor("#6b7280")

STATUS_COLOR = {"PASS": GREEN, "FAIL": RED, "UNKNOWN": GREY}

def _pil_to_rlimage(pil_img, max_w=3.1 * inch):
    buf = io.BytesIO()
    pil_img.convert("RGB").save(buf, format="JPEG", quality=80)
    buf.seek(0)
    w, h = pil_img.size
    return RLImage(buf, width=max_w, height=min(max_w * h / w, 2.4 * inch))

def _header_footer(report_id, address):
    def deco(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(BRAND)
        canvas.rect(0, letter[1] - 0.55 * inch, letter[0], 0.55 * inch, stroke=0, fill=1)
        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 14)
        canvas.drawString(0.75 * inch, letter[1] - 0.35 * inch, "EMBERCERT")
        canvas.setFont("Helvetica", 9)
        canvas.drawString(2.5 * inch, letter[1] - 0.35 * inch, "Wildfire Home-Hardening Assessment")
        canvas.drawRightString(letter[0] - 0.75 * inch, letter[1] - 0.35 * inch, report_id)
        canvas.setFillColor(GREY)
        canvas.setFont("Helvetica", 8)
        canvas.drawString(0.75 * inch, 0.45 * inch,
                          "Prepared for: " + address +
                          "    |    Automated preliminary assessment — not an insurance guarantee.")
        canvas.drawRightString(letter[0] - 0.75 * inch, 0.45 * inch, f"Page {doc.page}")
        canvas.restoreState()
    return deco

def build_pdf(result: dict, evidence_images=None, address="Not provided") -> bytes:
    buf = io.BytesIO()
    report_id = "EC-" + datetime.now().strftime("%Y%m%d-") + f"{random.randrange(16**4):04X}"
    deco = _header_footer(report_id, address)
    doc = SimpleDocTemplate(buf, pagesize=letter, topMargin=0.9 * inch,
                            bottomMargin=0.75 * inch)
    styles = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=styles["Normal"], fontSize=9.5, leading=13)
    small = ParagraphStyle("small", parent=body, fontSize=8, textColor=GREY)
    story = []

    passes = [i for i in result["items"] if i["status"] == "pass"]
    fails = [i for i in result["items"] if i["status"] == "fail"]
    unknowns = [i for i in result["items"] if i["status"] == "unknown"]
    fails_sorted = sorted(fails, key=lambda i: i["priority"])

    story.append(Paragraph("Executive Summary", styles["Heading2"]))
    story.append(Paragraph(
        f"This automated video-based assessment evaluated the subject property against the "
        f"California Department of Insurance 'Safer from Wildfires' framework. "
        f"Result: <b>{result['score']:.0f}/100</b> hardening score, "
        f"<b>{result['risk_label']}</b> ember-ignition risk — "
        f"{len(passes)} measures compliant, {len(fails)} deficiencies identified, "
        f"{len(unknowns)} items requiring in-person verification.", body))
    if fails_sorted:
        top = ", ".join(f"{i['title'].split('. ', 1)[-1]}" for i in fails_sorted[:3])
        story.append(Paragraph(
            f"Highest-priority corrective actions: <b>{top}</b>. Wind-blown embers — not the "
            f"flame front — are responsible for the majority of structure ignitions in "
            f"California wildfires; every measure below directly addresses ember pathways.", body))
    story.append(Spacer(1, 12))

    # ---- Findings summary table ----
    story.append(Paragraph("Findings Summary", styles["Heading2"]))
    data = [["#", "Framework measure", "Status", "Evidence source"]]
    for n, item in enumerate(result["items"], 1):
        source = ("AI video analysis" if "AI" in item["evidence"]
                  else "Homeowner attestation")
        data.append([str(n), item["title"].split(". ", 1)[-1],
                     item["status"].upper(), source])
    tbl = Table(data, colWidths=[0.35 * inch, 3.2 * inch, 1.05 * inch, 1.9 * inch])
    tstyle = [("BACKGROUND", (0, 0), (-1, 0), BRAND),
              ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
              ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
              ("FONTSIZE", (0, 0), (-1, -1), 9),
              ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
              ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
              ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
              ("LEFTPADDING", (0, 0), (-1, -1), 6),
              ("TOPPADDING", (0, 0), (-1, -1), 5),
              ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]
    for r, item in enumerate(result["items"], 1):
        tstyle.append(("TEXTCOLOR", (2, r), (2, r),
                       STATUS_COLOR[item["status"].upper()]))
        tstyle.append(("FONTNAME", (2, r), (2, r), "Helvetica-Bold"))
    tbl.setStyle(TableStyle(tstyle))
    story.append(tbl)
    story.append(Spacer(1, 14))

    # ---- Detailed findings ----
    story.append(Paragraph("Detailed Findings & Recommendations", styles["Heading2"]))
    for item in result["items"]:
        col = STATUS_COLOR[item["status"].upper()]
        story.append(Paragraph(
            f"<font color='{col.hexval().replace('0x','#')}'><b>{item['title']} — "
            f"{item['status'].upper()}</b></font>", styles["Heading4"]))
        story.append(Paragraph(item["plain"], body))
        story.append(Paragraph(f"Documented evidence: {item['evidence']}", small))
        if item["status"] == "fail":
            story.append(Paragraph(
                f"<b>Recommended corrective action:</b> {item['fix']}", body))
        story.append(Spacer(1, 8))

    # ---- Photo appendix ----
    if evidence_images:
        story.append(PageBreak())
        story.append(Paragraph("Appendix — AI-Annotated Evidence Frames", styles["Heading2"]))
        story.append(Paragraph(
            "Frames extracted from the submitted walk-around video. Regions marked by the "
            "analysis model are boxed in red.", body))
        story.append(Spacer(1, 8))
        letters = "ABCDEFGHIJ"
        for i in range(0, len(evidence_images), 2):
            row = [_pil_to_rlimage(evidence_images[i])]
            if i + 1 < len(evidence_images):
                row.append(_pil_to_rlimage(evidence_images[i + 1]))
            story.append(Table([row]))
            cap = Paragraph(
                f"Exhibit {letters[i]}" + (f"    |    Exhibit {letters[i+1]}"
                                           if i + 1 < len(evidence_images) else ""),
                small)
            story.append(cap)
            story.append(Spacer(1, 10))

    # ---- Methodology + attestation ----
    story.append(Spacer(1, 16))
    story.append(Paragraph("Methodology & Limitations", styles["Heading3"]))
    story.append(Paragraph(
        "Key frames were extracted from the submitted video (blur and duplicate filtering), "
        "then evaluated by a vision-language AI model for observable risk features under the "
        "10-measure state framework. Camera-invisible measures are reported by homeowner "
        "attestation. This document is a preliminary screening aid; insurers may require "
        "in-person verification before applying premium discounts.", small))
    story.append(Spacer(1, 24))
    story.append(Paragraph(
        "Homeowner signature: ____________________        Date: ____________", body))

    doc.build(story, onFirstPage=deco, onLaterPages=deco)
    return buf.getvalue()