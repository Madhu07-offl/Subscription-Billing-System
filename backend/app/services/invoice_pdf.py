"""Printable invoice (contract: GET /invoices/{id}/print).

The PDF is drawn from the same InvoiceOut that GET /invoices/{id} returns, so a printout always matches the API and the
access rules (customers: own, non-draft invoices only, 404 otherwise) live only in invoice_service.get_invoice.

Amounts use Indian digit grouping like the frontend (12,34,567.00). The currency is written as INR rather than the
rupee sign because the PDF base fonts have no glyph for it.
"""
import io
import re
import uuid
from datetime import date
from decimal import Decimal
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

from app.models.identity import User
from app.schemas.invoices import InvoiceOut
from app.services import invoice_service

SELLER = "Brightloop"
CURRENCY = "INR"
TOTAL = f"Total ({CURRENCY})"
METHODS = {"cash": "Cash", "bank_transfer": "Bank transfer", "card": "Card", "upi": "UPI", "cheque": "Cheque", "other": "Other"}

INK, MUTED = colors.HexColor("#1f2933"), colors.HexColor("#616e7c")
RULE, SHADE = colors.HexColor("#cbd2d9"), colors.HexColor("#f0f4f8")
BASE = ParagraphStyle("base", fontName="Helvetica", fontSize=9, leading=12, textColor=INK)
BOLD = ParagraphStyle("bold", parent=BASE, fontName="Helvetica-Bold")
SMALL = ParagraphStyle("small", parent=BASE, fontSize=8, leading=10, textColor=MUTED)
RIGHT = ParagraphStyle("right", parent=BASE, alignment=TA_RIGHT)
RIGHT_BOLD = ParagraphStyle("right_bold", parent=BOLD, alignment=TA_RIGHT)
RIGHT_SMALL = ParagraphStyle("right_small", parent=SMALL, alignment=TA_RIGHT)
HEADING = ParagraphStyle("heading", parent=BOLD, fontSize=10, leading=14, spaceBefore=6)
TITLE = ParagraphStyle("title", parent=BOLD, fontSize=20, leading=24)
GRID = [("LINEBELOW", (0, 0), (-1, -1), 0.5, RULE), ("BACKGROUND", (0, 0), (-1, 0), SHADE), ("VALIGN", (0, 0), (-1, -1), "TOP")]


def print_invoice(db: Session, invoice_id: uuid.UUID, user: User) -> tuple[bytes, str]:
    """(pdf bytes, file name). Raises the same 404 as GET /invoices/{id} for anything the user may not see."""
    inv = invoice_service.get_invoice(db, invoice_id, user)
    return render(inv), f"{inv.number}.pdf"


def money(value: Decimal) -> str:
    """Two decimals with Indian grouping: 1234567.5 -> '12,34,567.50'."""
    sign, digits = ("-", f"{-value:.2f}") if value < 0 else ("", f"{value:.2f}")
    whole, fraction = digits.split(".")
    if len(whole) > 3:
        head = ",".join(re.findall(r"\d{1,2}", whole[:-3][::-1]))[::-1]
        whole = f"{head},{whole[-3:]}"
    return f"{sign}{whole}.{fraction}"


def _day(d: date | None) -> str:
    return d.strftime("%d %b %Y") if d else "-"


def _p(text: str | None, style: ParagraphStyle = BASE) -> Paragraph:
    """Paragraph markup is XML: every value from the database is escaped."""
    return Paragraph(escape(text or ""), style)


def _header(inv: InvoiceOut) -> Table:
    status = "Overdue" if inv.is_overdue else inv.status.capitalize()
    meta = [
        ("Invoice", inv.number),
        ("Status", status),
        ("Subscription", inv.subscription_number),
        ("Issue date", _day(inv.issue_date)),
        ("Due date", _day(inv.due_date)),
        ("Period", f"{_day(inv.period_start)} to {_day(inv.period_end)}"),
    ]
    facts = Table([[_p(k, SMALL), _p(v, RIGHT)] for k, v in meta], colWidths=[28 * mm, 52 * mm])
    facts.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
    table = Table([[[Paragraph(SELLER, TITLE), _p("Subscription billing", SMALL)], facts]], colWidths=[90 * mm, 90 * mm])
    # the facts' own cell padding already lines their right edge up with the amounts column below
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (1, 0), (1, -1), "RIGHT"), ("RIGHTPADDING", (1, 0), (1, -1), 0),
    ]))  # fmt: skip
    return table


def _bill_to(inv: InvoiceOut) -> list:
    c = inv.customer_details
    lines = [c.name, c.company]
    if c.address:
        a = c.address
        lines += [a.line1, a.line2, ", ".join(x for x in (a.city, a.state, a.postal_code) if x), a.country]
    lines += [c.email, f"Tax ID: {c.tax_id}" if c.tax_id else None]
    return [_p("Bill to", HEADING)] + [_p(x) for x in lines if x]


def _lines(inv: InvoiceOut) -> Table:
    head = [_p("Description", SMALL), _p("Qty", SMALL)] + [_p(h, RIGHT_SMALL) for h in ("Unit price", "Discount", "Tax", "Amount")]
    rows = [head]
    for ln in inv.lines:
        tax = escape(money(ln.tax_amount))
        if ln.tax_name:
            tax += f"<br/><font size=7 color='#616e7c'>{escape(ln.tax_name)}</font>"
        rows.append([
            _p(ln.description), _p(str(ln.quantity)), _p(money(ln.unit_price), RIGHT),
            _p(money(ln.discount_amount), RIGHT), Paragraph(tax, RIGHT), _p(money(ln.amount), RIGHT),
        ])  # fmt: skip
    table = Table(rows, colWidths=[64 * mm, 12 * mm, 26 * mm, 24 * mm, 26 * mm, 28 * mm], repeatRows=1)
    table.setStyle(TableStyle(GRID))
    return table


def _totals(inv: InvoiceOut) -> Table:
    rows = [("Subtotal", inv.subtotal)]
    if inv.discount_total:
        rows.append(("Discount", -inv.discount_total))
    rows += [("Tax", inv.tax_total), (TOTAL, inv.total), ("Paid", inv.amount_paid), ("Amount due", inv.amount_due)]
    strong = {TOTAL, "Amount due"}
    data = [[_p(label, RIGHT_BOLD if label in strong else RIGHT), _p(money(v), RIGHT_BOLD if label in strong else RIGHT)]
            for label, v in rows]  # fmt: skip
    total_row = [label for label, _ in rows].index(TOTAL)
    table = Table(data, colWidths=[40 * mm, 34 * mm], hAlign="RIGHT")
    table.setStyle(TableStyle([("LINEABOVE", (0, total_row), (-1, total_row), 0.75, INK), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    return table


def _payments(inv: InvoiceOut) -> list:
    paid = [p for p in inv.payments if not p.is_voided]
    if not paid:
        return []
    rows = [[_p("Date", SMALL), _p("Method", SMALL), _p("Reference", SMALL), _p("Amount", RIGHT_SMALL)]]
    rows += [
        [_p(_day(p.payment_date)), _p(METHODS.get(p.method, p.method)), _p(p.reference or "-"), _p(money(p.amount), RIGHT)]
        for p in paid
    ]
    table = Table(rows, colWidths=[30 * mm, 36 * mm, 80 * mm, 34 * mm])
    table.setStyle(TableStyle(GRID))
    return [_p("Payments", HEADING), table]


def _decorate(inv: InvoiceOut):
    """Page furniture: a watermark on drafts and cancelled invoices, and the number and page in the footer."""
    mark = {"draft": "DRAFT", "cancelled": "CANCELLED"}.get(inv.status)

    def draw(canvas, doc) -> None:
        if mark:
            canvas.saveState()
            canvas.setFont("Helvetica-Bold", 80)
            canvas.setFillColor(colors.Color(0.8, 0.1, 0.1, alpha=0.12))
            canvas.translate(A4[0] / 2, A4[1] / 2)
            canvas.rotate(35)
            canvas.drawCentredString(0, 0, mark)
            canvas.restoreState()
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(15 * mm, 10 * mm, f"{SELLER} - {inv.number}")
        canvas.drawRightString(A4[0] - 15 * mm, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    return draw


def render(inv: InvoiceOut) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm, topMargin=15 * mm, bottomMargin=18 * mm,
        title=f"Invoice {inv.number}", author=SELLER, invariant=True,
    )  # fmt: skip
    story = [_header(inv), Spacer(1, 6 * mm), *_bill_to(inv), Spacer(1, 5 * mm), _lines(inv), Spacer(1, 4 * mm), _totals(inv)]
    story += _payments(inv)
    if inv.notes:
        story += [_p("Notes", HEADING), _p(inv.notes)]
    decorate = _decorate(inv)
    doc.build(story, onFirstPage=decorate, onLaterPages=decorate)
    return buf.getvalue()
