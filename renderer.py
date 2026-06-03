"""
renderer.py — Generate gambar papan dam-daman pakai PIL
Overlay pion di atas papan_kosong.jpg
"""
import io
import os
from PIL import Image, ImageDraw, ImageFont

from game import Game, WHITE, BLACK, slot_to_rc, WHITE_TARGET, BLACK_TARGET

BOARD_IMG = os.path.join(os.path.dirname(__file__), "papan_kosong.jpg")

# Warna pion
COLOR_WHITE  = (255, 255, 255)
COLOR_BLACK  = (30,  30,  30)
COLOR_SEL    = (255, 215, 0)    # kuning — slot dipilih
COLOR_TARGET = (0,   200, 100)  # hijau  — slot tujuan valid
COLOR_LABEL  = (255, 80,  80)   # merah  — nomor slot

BORDER_W = 3
BORDER_B = 3


def _load_board() -> Image.Image:
    return Image.open(BOARD_IMG).convert("RGB")


def _cell_bbox(img_w: int, img_h: int, row: int, col: int):
    """Bounding box (x1,y1,x2,y2) untuk cell (row,col) di gambar."""
    cw = img_w / 8
    ch = img_h / 4
    x1 = int(col * cw)
    y1 = int(row * ch)
    x2 = int(x1 + cw)
    y2 = int(y1 + ch)
    return x1, y1, x2, y2


def draw_board(game: Game, highlight_sources: list = None, highlight_targets: list = None) -> bytes:
    """
    Render papan + pion + highlight.
    highlight_sources: slot yang bisa dipilih (outline kuning)
    highlight_targets: slot tujuan valid (outline hijau)
    Return: bytes JPEG
    """
    img  = _load_board()
    draw = ImageDraw.Draw(img, "RGBA")
    W, H = img.size

    # Font
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", max(12, H // 20))
    except Exception:
        font = ImageFont.load_default()

    highlight_sources = set(highlight_sources or [])
    highlight_targets = set(highlight_targets or [])

    for slot in range(1, 33):
        row, col = slot_to_rc(slot)
        x1, y1, x2, y2 = _cell_bbox(W, H, row, col)
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2
        cw = x2 - x1
        ch = y2 - y1

        # Highlight cell
        if slot in highlight_targets:
            draw.rectangle([x1, y1, x2, y2], fill=(0, 200, 100, 80), outline=(0, 200, 100), width=4)
        elif slot in highlight_sources:
            draw.rectangle([x1, y1, x2, y2], fill=(255, 215, 0, 60), outline=(255, 215, 0), width=4)

        # Pion
        piece = game.board.get(slot)
        if piece:
            r = int(min(cw, ch) * 0.28)   # pas dalam kotak 160px
            if piece == WHITE:
                # Outline + fill putih
                draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(240, 240, 240), outline=(80, 80, 80), width=BORDER_W)
                # Lingkaran dalam
                ri = int(r * 0.65)
                draw.ellipse([cx - ri, cy - ri, cx + ri, cy + ri], fill=None, outline=(160, 160, 160), width=2)
            else:
                # Pion hitam
                draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(40, 40, 40), outline=(180, 180, 180), width=BORDER_B)
                ri = int(r * 0.65)
                draw.ellipse([cx - ri, cy - ri, cx + ri, cy + ri], fill=None, outline=(100, 100, 100), width=2)

        # Nomor slot (pojok kiri atas, kecil)
        draw.text((x1 + 4, y1 + 2), str(slot), fill=COLOR_LABEL, font=font)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    buf.seek(0)
    return buf.read()
