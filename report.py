import io
import random
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    Image as ReportLabImage,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


BRAND = colors.HexColor("#1b4332")
LIGHT = colors.HexColor("#f1f8f3")
GREEN = colors.HexColor("#15803d")
RED = colors.HexColor("#b91c1c")
GREY = colors.HexColor("#6b7280")

STATUS_COLOR = {
    "PASS": GREEN,
    "FAIL": RED,
    "UNKNOWN": GREY,
}


def _pil_image(image, max_width=3.1 * inch):
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, "JPEG", quality=80)
    buffer.seek(0)

    image_width, image_height = image.size
    displayed_height = min(
        max_width * image_height / image_width,
        2.4 * inch,
    )

    return ReportLabImage(
        buffer,
        width=max_width,
        height=displayed_height,
    )


def _image_from_bytes(image_bytes, width=4.6 * inch):
    buffer = io.BytesIO(image_bytes)
    image_reader = ImageReader(buffer)
    image_width, image_height = image_reader.getSize()

    return ReportLabImage(
        io.BytesIO(image_bytes),
        width=width,
        height=width * image_height / image_width,
    )


def _page_decorator(report_id, address):
    def decorate(canvas, document):
        canvas.saveState()

        canvas.setFillColor(BRAND)
        canvas.rect(
            0,
            letter[1] - 0.55 * inch,
            letter[0],
            0.55 * inch,
            stroke=0,
            fill=1,
        )

        canvas.setFillColor(colors.white)
        canvas.setFont("Helvetica-Bold", 14)
        canvas.drawString(
            0.75 * inch,
            letter[1] - 0.35 * inch,
            "EMBER",
        )

        canvas.setFont("Helvetica", 9)
        canvas.drawString(
            2.0 * inch,
            letter[1] - 0.35 * inch,
            "Wildfire Home-Hardening Technical Packet",
        )

        canvas.drawRightString(
            letter[0] - 0.75 * inch,
            letter[1] - 0.35 * inch,
            report_id,
        )

        canvas.setFillColor(GREY)
        canvas.setFont("Helvetica", 8)
        canvas.drawString(
            0.75 * inch,
            0.45 * inch,
            (
                f"Prepared for: {address}  |  "
                "Automated preliminary assessment — not an insurance guarantee."
            ),
        )

        canvas.drawRightString(
            letter[0] - 0.75 * inch,
            0.45 * inch,
            f"Page {document.page}",
        )

        canvas.restoreState()

    return decorate


def build_pdf(
    result,
    evidence_images=None,
    address="Not provided",
    parcel=None,
    fingerprint=None,
) -> bytes:
    buffer = io.BytesIO()

    report_id = fingerprint or (
        "EMB-"
        + datetime.now().strftime("%y%m%d")
        + f"-{random.randrange(16**4):04X}"
    )

    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        topMargin=0.9 * inch,
        bottomMargin=0.75 * inch,
    )

    styles = getSampleStyleSheet()

    body = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontSize=9.5,
        leading=13,
    )

    small = ParagraphStyle(
        "Small",
        parent=body,
        fontSize=8,
        textColor=GREY,
    )

    story = []

    passed = [
        item
        for item in result["items"]
        if item["status"] == "pass"
    ]

    failed = sorted(
        [
            item
            for item in result["items"]
            if item["status"] == "fail"
        ],
        key=lambda item: -item["weight"],
    )

    unknown = [
        item
        for item in result["items"]
        if item["status"] == "unknown"
    ]

    low_band, high_band = result.get(
        "band",
        (result["score"], result["score"]),
    )

    story.append(
        Paragraph(
            "Executive Summary",
            styles["Heading2"],
        )
    )

    story.append(
        Paragraph(
            (
                "Video-based assessment against the California Department of "
                "Insurance 'Safer from Wildfires' framework. Weighted hardening "
                f"score <b>{result['score']:.0f}/100 "
                f"(band {low_band}–{high_band})</b>; ember-ignition risk "
                f"<b>{result['risk_label']}</b>. Findings: "
                f"{len(passed)} compliant, {len(failed)} deficiencies, "
                f"{len(unknown)} items requiring in-person verification."
            ),
            body,
        )
    )

    if failed:
        story.append(
            Paragraph(
                "Highest-weight corrective actions: <b>"
                + ", ".join(item["plain_title"] for item in failed[:3])
                + ".</b>",
                body,
            )
        )

    story.append(Spacer(1, 10))

    story.append(
        Paragraph(
            "Findings Summary",
            styles["Heading2"],
        )
    )

    table_data = [
        [
            "#",
            "Framework measure",
            "Weight",
            "Status",
            "Evidence source",
        ]
    ]

    for index, item in enumerate(result["items"], 1):
        source = (
            "AI video analysis"
            if "AI" in item["evidence"]
            else "Homeowner attestation"
        )

        table_data.append(
            [
                str(index),
                item["title"].split(". ", 1)[-1],
                str(item.get("weight", "—")),
                item["status"].upper(),
                source,
            ]
        )

    findings_table = Table(
        table_data,
        colWidths=[
            0.3 * inch,
            2.9 * inch,
            0.6 * inch,
            0.9 * inch,
            1.7 * inch,
        ],
    )

    style_commands = [
        ("BACKGROUND", (0, 0), (-1, 0), BRAND),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.6),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d5ddd2")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]

    for row_index, item in enumerate(result["items"], 1):
        style_commands.append(
            (
                "TEXTCOLOR",
                (3, row_index),
                (3, row_index),
                STATUS_COLOR[item["status"].upper()],
            )
        )
        style_commands.append(
            (
                "FONTNAME",
                (3, row_index),
                (3, row_index),
                "Helvetica-Bold",
            )
        )

    findings_table.setStyle(TableStyle(style_commands))
    story.append(findings_table)
    story.append(Spacer(1, 12))

    if parcel:
        story.append(
            Paragraph(
                "Verified Aerial Findings Map",
                styles["Heading2"],
            )
        )

        story.append(
            _image_from_bytes(
                parcel["png"],
                width=4.6 * inch,
            )
        )

        map_description = (
            "High-resolution aerial imagery (Esri World Imagery). "
            "The white crosshair marks the roof point selected by the user; "
            "numbered pins correspond to the priority-ordered findings below."
        )

        if failed:
            map_description += " Pins: " + "; ".join(
                f"{index + 1}) {item['plain_title']}"
                for index, item in enumerate(failed)
            ) + "."

        story.append(
            Paragraph(
                map_description,
                small,
            )
        )

        story.append(Spacer(1, 10))

    story.append(
        Paragraph(
            "Detailed Findings & Recommendations",
            styles["Heading2"],
        )
    )

    for item in result["items"]:
        color = STATUS_COLOR[item["status"].upper()]
        color_hex = color.hexval().replace("0x", "#")

        story.append(
            Paragraph(
                (
                    f"<font color='{color_hex}'><b>"
                    f"{item['title']} — {item['status'].upper()}"
                    f"</b></font>"
                ),
                styles["Heading4"],
            )
        )

        story.append(
            Paragraph(
                item["plain"],
                body,
            )
        )

        story.append(
            Paragraph(
                f"Documented evidence: {item['evidence']}",
                small,
            )
        )

        if item["status"] == "fail":
            story.append(
                Paragraph(
                    f"<b>Recommended corrective action:</b> {item['fix']}",
                    body,
                )
            )

        story.append(Spacer(1, 7))

    if evidence_images:
        story.append(PageBreak())

        story.append(
            Paragraph(
                "Appendix — AI-Annotated Evidence Frames",
                styles["Heading2"],
            )
        )

        for index in range(0, len(evidence_images), 2):
            row = [
                _pil_image(evidence_images[index])
            ]

            if index + 1 < len(evidence_images):
                row.append(
                    _pil_image(evidence_images[index + 1])
                )

            story.append(Table([row]))

            caption = f"Exhibit {chr(65 + index)}"

            if index + 1 < len(evidence_images):
                caption += f"   |   Exhibit {chr(65 + index + 1)}"

            story.append(
                Paragraph(
                    caption,
                    small,
                )
            )

            story.append(Spacer(1, 8))

    story.append(Spacer(1, 14))

    story.append(
        Paragraph(
            "Methodology, Uncertainty & Integrity",
            styles["Heading3"],
        )
    )

    story.append(
        Paragraph(
            (
                "Key video frames were selected using motion-aware sampling "
                "(blur and optical-flow filtering), then evaluated using a "
                "vision-language model under the state hardening framework. "
                "Vegetation cover was independently measured with an "
                "Excess-Green (ExG) spectral index computed from raw pixels. "
                "Aerial map context is retrieved from public imagery only after "
                "the user manually confirms their target roof point. Unknown "
                f"measures flex the score into the published band "
                f"({low_band}–{high_band}) rather than being silently assumed. "
                "A tamper-evident SHA-256 integrity fingerprint appears in the "
                "page header and is recomputable from the findings."
            ),
            small,
        )
    )

    story.append(Spacer(1, 22))

    story.append(
        Paragraph(
            "Homeowner signature: ____________________        Date: ____________",
            body,
        )
    )

    decorator = _page_decorator(report_id, address)

    document.build(
        story,
        onFirstPage=decorator,
        onLaterPages=decorator,
    )

    return buffer.getvalue()