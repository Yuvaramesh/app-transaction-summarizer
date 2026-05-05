import calendar
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

AJEER_GREEN = colors.HexColor("#0F6E56")
AJEER_LIGHT = colors.HexColor("#E1F5EE")
AJEER_TEAL = colors.HexColor("#1D9E75")
GRAY_TEXT = colors.HexColor("#6B7280")
GRAY_BORDER = colors.HexColor("#E5E7EB")
AMBER = colors.HexColor("#854F0B")
AMBER_BG = colors.HexColor("#FAEEDA")

MONTH_NAMES = {
    1: "January",
    2: "February",
    3: "March",
    4: "April",
    5: "May",
    6: "June",
    7: "July",
    8: "August",
    9: "September",
    10: "October",
    11: "November",
    12: "December",
}


class PDFGenerator:
    def generate(
        self,
        user: dict,
        transactions: list[dict],
        summary: dict,
        month: int,
        year: int,
    ) -> bytes:
        buf = BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=A4,
            leftMargin=18 * mm,
            rightMargin=18 * mm,
            topMargin=12 * mm,
            bottomMargin=16 * mm,
        )

        styles = getSampleStyleSheet()
        story = []

        # ── Header bar ──────────────────────────────────────────────────
        header_data = [
            [
                Paragraph(
                    '<font color="white" size="16"><b>Ajeer</b></font>',
                    styles["Normal"],
                ),
                Paragraph(
                    f'<font color="#9FE1CB" size="9">Monthly Transfer Statement · {MONTH_NAMES[month]} {year}</font>',
                    ParagraphStyle("r", alignment=TA_RIGHT),
                ),
            ]
        ]
        header_table = Table(header_data, colWidths=["40%", "60%"])
        header_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), AJEER_GREEN),
                    ("TOPPADDING", (0, 0), (-1, -1), 10),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                    ("LEFTPADDING", (0, 0), (-1, -1), 14),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 14),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )
        story.append(header_table)
        story.append(Spacer(1, 6 * mm))

        # ── Section helper ───────────────────────────────────────────────
        def section_title(text):
            story.append(
                Paragraph(
                    f'<font color="#0F6E56" size="8"><b>{text.upper()}</b></font>',
                    styles["Normal"],
                )
            )
            story.append(
                HRFlowable(width="100%", thickness=0.5, color=GRAY_BORDER, spaceAfter=4)
            )

        def kv_table(rows):
            data = [
                [
                    Paragraph(
                        f'<font color="#6B7280" size="9">{k}</font>', styles["Normal"]
                    ),
                    Paragraph(
                        f'<font size="9"><b>{v}</b></font>',
                        ParagraphStyle("rv", alignment=TA_RIGHT),
                    ),
                ]
                for k, v in rows
            ]
            t = Table(data, colWidths=["55%", "45%"])
            t.setStyle(
                TableStyle(
                    [
                        ("TOPPADDING", (0, 0), (-1, -1), 3),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ]
                )
            )
            story.append(t)
            story.append(Spacer(1, 4 * mm))

        metrics = summary["metrics"]

        # ── Account holder ───────────────────────────────────────────────
        section_title("Account Holder")
        kv_table(
            [
                ("Name", user["name"]),
                ("Email", user["email"]),
                ("Phone", user.get("phone", "—")),
                ("Account type", "Personal · KYC Approved"),
                (
                    "Statement period",
                    f"1 {MONTH_NAMES[month]} {year} – {calendar.monthrange(year, month)[1]} {MONTH_NAMES[month]} {year}",
                ),
            ]
        )

        # ── Summary ──────────────────────────────────────────────────────
        section_title("Summary")
        received_str = "  |  ".join(
            f"{v:,.2f} {ccy}" for ccy, v in metrics["received_by_currency"].items()
        )
        kv_table(
            [
                ("Total transferred (GBP)", f"£{metrics['total_gbp']:,.2f}"),
                (
                    "Total fees paid",
                    f"£{metrics['total_fees']:,.2f}  ({metrics['fee_rate_pct']}%)",
                ),
                ("Total received by recipients", received_str),
                ("Average LKR exchange rate", f"{metrics['avg_rate_lkr']} per GBP"),
                ("Number of transfers", str(metrics["transfer_count"])),
            ]
        )

        # ── AI narrative ─────────────────────────────────────────────────
        section_title("AI Insight")
        ai_data = [
            [
                Paragraph(
                    f'<font size="9" color="#085041">{summary["narrative"]}</font>',
                    ParagraphStyle("ai", leading=14),
                )
            ]
        ]
        ai_table = Table(ai_data, colWidths=["100%"])
        ai_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), AJEER_LIGHT),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                    ("ROUNDEDCORNERS", (0, 0), (-1, -1), [4, 4, 4, 4]),
                ]
            )
        )
        story.append(ai_table)
        story.append(Spacer(1, 4 * mm))

        # Nudge box
        nudge_data = [
            [
                Paragraph(
                    f'<font size="8" color="#854F0B">💡 {summary["nudge"]}</font>',
                    ParagraphStyle("nudge", leading=12),
                )
            ]
        ]
        nudge_table = Table(nudge_data, colWidths=["100%"])
        nudge_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), AMBER_BG),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ]
            )
        )
        story.append(nudge_table)
        story.append(Spacer(1, 5 * mm))

        # ── Transaction detail ───────────────────────────────────────────
        section_title("Transaction Detail")
        txn_header = [
            Paragraph(
                '<font size="8" color="white"><b>Transaction ID</b></font>',
                styles["Normal"],
            ),
            Paragraph(
                '<font size="8" color="white"><b>Recipient</b></font>', styles["Normal"]
            ),
            Paragraph(
                '<font size="8" color="white"><b>Date</b></font>', styles["Normal"]
            ),
            Paragraph(
                '<font size="8" color="white"><b>Amount (GBP)</b></font>',
                ParagraphStyle("th", alignment=TA_RIGHT),
            ),
            Paragraph(
                '<font size="8" color="white"><b>Received</b></font>',
                ParagraphStyle("th2", alignment=TA_RIGHT),
            ),
            Paragraph(
                '<font size="8" color="white"><b>Status</b></font>',
                ParagraphStyle("th3", alignment=TA_CENTER),
            ),
        ]
        txn_rows = [txn_header]
        for t in transactions:
            txn_rows.append(
                [
                    Paragraph(
                        f'<font size="8" color="#6B7280">{t["transaction_id"]}</font>',
                        styles["Normal"],
                    ),
                    Paragraph(
                        f'<font size="8">{t["recipient_name"]}</font>', styles["Normal"]
                    ),
                    Paragraph(
                        f'<font size="8" color="#6B7280">{t["date"]}</font>',
                        styles["Normal"],
                    ),
                    Paragraph(
                        f'<font size="8"><b>£{t["amount_gbp"]:,.2f}</b></font>',
                        ParagraphStyle("ar", alignment=TA_RIGHT),
                    ),
                    Paragraph(
                        f'<font size="8">{t["amount_received"]:,.2f} {t["currency"]}</font>',
                        ParagraphStyle("ar2", alignment=TA_RIGHT),
                    ),
                    Paragraph(
                        f'<font size="8" color="#854F0B">{t["status"]}</font>',
                        ParagraphStyle("ac", alignment=TA_CENTER),
                    ),
                ]
            )

        txn_table = Table(
            txn_rows,
            colWidths=["26%", "18%", "14%", "14%", "16%", "12%"],
        )
        txn_style = [
            ("BACKGROUND", (0, 0), (-1, 0), AJEER_GREEN),
            (
                "ROWBACKGROUNDS",
                (0, 1),
                (-1, -1),
                [colors.white, colors.HexColor("#F9FAFB")],
            ),
            ("GRID", (0, 0), (-1, -1), 0.4, GRAY_BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]
        txn_table.setStyle(TableStyle(txn_style))
        story.append(txn_table)
        story.append(Spacer(1, 6 * mm))

        # ── Footer ───────────────────────────────────────────────────────
        story.append(HRFlowable(width="100%", thickness=0.5, color=GRAY_BORDER))
        story.append(Spacer(1, 2 * mm))
        story.append(
            Paragraph(
                '<font size="8" color="#9CA3AF">Generated by Ajeer AI · Ajeer Web v1.0.0 · support@ajeer.com</font>',
                ParagraphStyle("footer", alignment=TA_CENTER),
            )
        )

        doc.build(story)
        return buf.getvalue()
