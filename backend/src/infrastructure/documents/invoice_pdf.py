"""Rendu PDF des factures BazarStore (ReportLab, polices PDF standard : aucun fichier de police requis)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from src.shared.amount_in_words import amount_in_words

NAVY = colors.HexColor("#172744")
BLUE = colors.HexColor("#315e91")
MUTED = colors.HexColor("#6b7489")
LINE = colors.HexColor("#dfe4ec")
SOFT = colors.HexColor("#f4f6fa")
NBSP = "\N{NO-BREAK SPACE}"
DEFAULT_LOGO = Path(__file__).parent / "assets" / "bazarstore-logo.png"
LOGO_SIZE = 17 * mm


@dataclass(frozen=True)
class InvoiceSeller:
    name: str
    address: str = ""
    city: str = ""
    phone: str = ""
    email: str = ""
    nif: str = ""
    stat: str = ""
    rcs: str = ""
    logo_path: Path | None = DEFAULT_LOGO


@dataclass(frozen=True)
class InvoiceLine:
    designation: str
    reference: str
    quantity: int
    unit_price: int  # TTC, en ariary
    total: int  # TTC, en ariary


@dataclass(frozen=True)
class InvoiceData:
    number: str
    issued_at: datetime
    order_reference: str
    order_date: datetime
    customer_name: str
    customer_email: str
    seller: InvoiceSeller
    lines: list[InvoiceLine]
    total_ttc: int
    vat_rate: float
    is_paid: bool
    paid_at: datetime | None = None
    payment_method: str | None = None
    payment_terms: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def total_ht(self) -> int:
        return (
            round(self.total_ttc / (1 + self.vat_rate / 100)) if self.vat_rate else self.total_ttc
        )

    @property
    def total_vat(self) -> int:
        return self.total_ttc - self.total_ht


def format_ariary(amount: int) -> str:
    # Espace insécable comme séparateur de milliers (présent dans l'encodage des polices standard).
    return f"{amount:,}".replace(",", NBSP) + f"{NBSP}Ar"


def _date(value: datetime) -> str:
    return value.strftime("%d/%m/%Y")


def _styles() -> dict[str, ParagraphStyle]:
    base = ParagraphStyle("base", fontName="Helvetica", fontSize=9, leading=12.5, textColor=NAVY)
    return {
        "base": base,
        "muted": ParagraphStyle("muted", parent=base, textColor=MUTED, fontSize=8.5, leading=12),
        "brand": ParagraphStyle(
            "brand", parent=base, fontName="Helvetica-Bold", fontSize=18, leading=22
        ),
        "title": ParagraphStyle(
            "title",
            parent=base,
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=26,
            alignment=TA_RIGHT,
            textColor=BLUE,
        ),
        "right": ParagraphStyle("right", parent=base, alignment=TA_RIGHT),
        "label": ParagraphStyle(
            "label",
            parent=base,
            fontName="Helvetica-Bold",
            fontSize=7.5,
            leading=10,
            textColor=MUTED,
        ),
        "th": ParagraphStyle(
            "th", parent=base, fontName="Helvetica-Bold", fontSize=8, textColor=colors.white
        ),
        "th_right": ParagraphStyle(
            "th_right",
            parent=base,
            fontName="Helvetica-Bold",
            fontSize=8,
            textColor=colors.white,
            alignment=TA_RIGHT,
        ),
        "cell": ParagraphStyle("cell", parent=base, alignment=TA_LEFT),
        "small": ParagraphStyle("small", parent=base, fontSize=7.5, leading=10, textColor=MUTED),
    }


def _seller_block(
    seller: InvoiceSeller, details_html: str, st: dict[str, ParagraphStyle], width: float
) -> Table | list:
    """Logo (s'il existe) à gauche du nom et des coordonnées du vendeur."""
    text = [Paragraph(escape(seller.name), st["brand"]), Paragraph(details_html, st["muted"])]
    if not seller.logo_path or not seller.logo_path.is_file():
        return text
    logo = Image(str(seller.logo_path), width=LOGO_SIZE, height=LOGO_SIZE, kind="proportional")
    block = Table([[logo, text]], colWidths=[LOGO_SIZE + 4 * mm, width - LOGO_SIZE - 4 * mm])
    block.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return block


def render_invoice_pdf(invoice: InvoiceData) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=24 * mm,
        title=f"Facture {invoice.number}",
        author=invoice.seller.name,
        subject=f"Facture de la commande {invoice.order_reference}",
    )
    st = _styles()
    width = doc.width
    story: list = []

    # ─── En-tête : vendeur à gauche, titre et numéro à droite ───
    seller = invoice.seller
    seller_details = [
        seller.address,
        seller.city,
        seller.phone and f"Tél. : {seller.phone}",
        seller.email,
    ]
    seller_html = "<br/>".join(escape(line) for line in seller_details if line)
    status_color = "#1f7a4d" if invoice.is_paid else "#a2620f"
    status_label = "PAYÉE" if invoice.is_paid else "EN ATTENTE DE RÈGLEMENT"
    header = Table(
        [
            [
                _seller_block(seller, seller_html, st, width * 0.55),
                [
                    Paragraph("FACTURE", st["title"]),
                    Paragraph(f"<b>N° {escape(invoice.number)}</b>", st["right"]),
                    Paragraph(
                        f'<font color="{status_color}"><b>{status_label}</b></font>', st["right"]
                    ),
                ],
            ]
        ],
        colWidths=[width * 0.55, width * 0.45],
    )
    header.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story += [header, Spacer(1, 9 * mm)]

    # ─── Informations facture / client ───
    def info_block(label: str, rows: list[str]) -> list:
        return [Paragraph(label, st["label"]), Spacer(1, 1.5 * mm)] + [
            Paragraph(row, st["base"]) for row in rows
        ]

    invoice_rows = [
        f"Date d'émission : <b>{_date(invoice.issued_at)}</b>",
        f"Commande : <b>{escape(invoice.order_reference)}</b>",
        f"Date de commande : {_date(invoice.order_date)}",
    ]
    customer_rows = [f"<b>{escape(invoice.customer_name)}</b>", escape(invoice.customer_email)]
    info = Table(
        [[info_block("FACTURE", invoice_rows), info_block("FACTURÉ À", customer_rows)]],
        colWidths=[width / 2, width / 2],
    )
    info.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (-1, -1), SOFT),
                ("BOX", (0, 0), (-1, -1), 0.6, LINE),
                ("LINEAFTER", (0, 0), (0, 0), 0.6, LINE),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    story += [info, Spacer(1, 8 * mm)]

    # ─── Lignes ───
    head = [
        Paragraph("Désignation", st["th"]),
        Paragraph("Réf.", st["th"]),
        Paragraph("Qté", st["th_right"]),
        Paragraph("Prix unitaire TTC", st["th_right"]),
        Paragraph("Montant TTC", st["th_right"]),
    ]
    rows = [head] + [
        [
            Paragraph(escape(line.designation), st["cell"]),
            Paragraph(escape(line.reference), st["small"]),
            Paragraph(str(line.quantity), st["right"]),
            Paragraph(format_ariary(line.unit_price), st["right"]),
            Paragraph(format_ariary(line.total), st["right"]),
        ]
        for line in invoice.lines
    ]
    lines_table = Table(
        rows,
        colWidths=[width * 0.38, width * 0.17, width * 0.08, width * 0.185, width * 0.185],
        repeatRows=1,
    )
    lines_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, SOFT]),
                ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINE),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story += [lines_table, Spacer(1, 6 * mm)]

    # ─── Totaux ───
    totals_rows = []
    if invoice.vat_rate:
        vat = f"{invoice.vat_rate:g}".replace(".", ",")
        totals_rows += [
            ["Total HT", format_ariary(invoice.total_ht)],
            [f"TVA {vat} %", format_ariary(invoice.total_vat)],
        ]
    totals_rows.append(
        ["Total TTC" if invoice.vat_rate else "Total", format_ariary(invoice.total_ttc)]
    )
    last = len(totals_rows) - 1

    def total_cell(text: str, style: str, index: int) -> Paragraph:
        # Dernière ligne (total à payer) en blanc et gras sur fond bleu nuit.
        return Paragraph(
            f'<font color="white"><b>{text}</b></font>' if index == last else text, st[style]
        )

    totals = Table(
        [
            [total_cell(label, "base", index), total_cell(value, "right", index)]
            for index, (label, value) in enumerate(totals_rows)
        ],
        colWidths=[width * 0.22, width * 0.2],
        hAlign="RIGHT",
    )
    totals.setStyle(
        TableStyle(
            [
                ("LINEBELOW", (0, 0), (-1, -2), 0.4, LINE),
                ("BACKGROUND", (0, last), (-1, last), NAVY),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story += [totals, Spacer(1, 7 * mm)]

    # ─── Mentions ───
    words = amount_in_words(invoice.total_ttc)
    story.append(
        Paragraph(
            f"Arrêtée la présente facture à la somme de <b>{words} ariary</b> "
            f"({format_ariary(invoice.total_ttc)}){' TTC' if invoice.vat_rate else ''}.",
            st["base"],
        )
    )
    story.append(Spacer(1, 4 * mm))
    if invoice.is_paid:
        method = f" par {invoice.payment_method}" if invoice.payment_method else ""
        when = f" le {_date(invoice.paid_at)}" if invoice.paid_at else ""
        payment = f'<font color="#1f7a4d"><b>Facture acquittée</b></font>{method}{when}.'
    else:
        payment = f"<b>Règlement :</b> {escape(invoice.payment_terms)}"
    story.append(Paragraph(payment, st["base"]))
    if not invoice.vat_rate:
        story.append(Paragraph("TVA non applicable.", st["muted"]))
    for note in invoice.notes:
        story.append(Paragraph(escape(note), st["muted"]))

    legal = " · ".join(
        part
        for part in (
            seller.name,
            seller.nif and f"NIF : {seller.nif}",
            seller.stat and f"STAT : {seller.stat}",
            seller.rcs and f"RCS : {seller.rcs}",
        )
        if part
    )

    def draw_footer(canvas: Canvas, document: SimpleDocTemplate) -> None:
        canvas.saveState()
        canvas.setStrokeColor(LINE)
        canvas.line(document.leftMargin, 15 * mm, A4[0] - document.rightMargin, 15 * mm)
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(document.leftMargin, 10.5 * mm, legal)
        canvas.drawRightString(
            A4[0] - document.rightMargin,
            10.5 * mm,
            f"Facture {invoice.number} · page {canvas.getPageNumber()}",
        )
        canvas.restoreState()

    doc.build(story, onFirstPage=draw_footer, onLaterPages=draw_footer)
    return buffer.getvalue()
