from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


# ─── PATHS (НЕ ТРОГАЕМ) ────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parents[1]  # src/bot
ASSETS_DIR = BASE_DIR / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
BACKGROUNDS_DIR = ASSETS_DIR / "backgrounds"

FONT_PATH = FONTS_DIR / "DejaVuSans.ttf"
BG_IMAGE_PATH = BACKGROUNDS_DIR / "plant_plan_bg.png"


# ─── PDF ──────────────────────────────────────────────────

def generate_plan_pdf(
    response_text: str,
    output_path: str | Path,
    title: str,
):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if not FONT_PATH.exists():
        raise FileNotFoundError(f"Font not found: {FONT_PATH}")

    pdfmetrics.registerFont(TTFont("DejaVu", str(FONT_PATH)))

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=25 * mm,
        rightMargin=25 * mm,
        topMargin=42 * mm,
        bottomMargin=65 * mm,
    )

    # ─── STYLES ────────────────────────────────────────────

    styles = {
        "title": ParagraphStyle(
            name="Title",
            fontName="DejaVu",
            fontSize=18,
            leading=22,
            spaceAfter=18,
            textColor="#264d36",
        ),
        "section": ParagraphStyle(
            name="Section",
            fontName="DejaVu",
            fontSize=13,
            leading=17,
            spaceBefore=14,
            spaceAfter=8,
            textColor="#1f3d2b",
        ),
        "body": ParagraphStyle(
            name="Body",
            fontName="DejaVu",
            fontSize=11,
            leading=15,
            spaceAfter=6,
        ),
        "bullet": ParagraphStyle(
            name="Bullet",
            fontName="DejaVu",
            fontSize=11,
            leading=15,
            leftIndent=12,
            bulletIndent=0,
            spaceAfter=4,
        ),
    }

    flowables: list = []

    # ─── TITLE ─────────────────────────────────────────────

    flowables.append(Paragraph(title, styles["title"]))
    flowables.append(Spacer(1, 8))

    # ─── TEXT PARSING ──────────────────────────────────────

    lines = response_text.splitlines()

    for line in lines:
        line = line.strip()

        if not line:
            flowables.append(Spacer(1, 6))
            continue

        # Заголовки вида: "### ЭТАП 1"
        if line.startswith("###"):
            flowables.append(
                Paragraph(line.replace("###", "").strip(), styles["section"])
            )
            continue

        # Маркированные списки
        if line.startswith(("– ", "- ", "— ")):
            flowables.append(
                Paragraph(
                    line[2:].strip(),
                    styles["bullet"],
                    bulletText="•",
                )
            )
            continue

        # Обычный текст
        flowables.append(Paragraph(line, styles["body"]))

    # ─── BACKGROUND ────────────────────────────────────────

    def draw_background(canvas, doc):
        if BG_IMAGE_PATH.exists():
            canvas.drawImage(
                str(BG_IMAGE_PATH),
                0,
                0,
                width=A4[0],
                height=A4[1],
                preserveAspectRatio=True,
                mask="auto",
            )

    doc.build(
        flowables,
        onFirstPage=draw_background,
        onLaterPages=draw_background,
    )
