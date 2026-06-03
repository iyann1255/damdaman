"""
main.py — Dam-daman Telegram Bot (aiogram v3)
"""
import asyncio
import logging
import os
from typing import Dict, Optional

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from dotenv import load_dotenv

from game import (
    EMPTY, P1, P2, P1_DAM, P2_DAM,
    GameState, Pos, owner,
)

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("damdaman")

# ── In-memory session storage ─────────────────────────────────────────────────
# key: chat_id
games: Dict[int, GameState] = {}
# pending invite: chat_id → challenger_id
pending: Dict[int, int] = {}

router = Router()

# ── Board rendering ───────────────────────────────────────────────────────────

CELL_ICONS = {
    "dark_empty":   "⬛",
    "light":        "⬜",
    "p1":           "🔴",
    "p2":           "🔵",
    "p1_dam":       "🅡",   # fallback
    "p2_dam":       "🅑",
    "selected":     "🟡",
    "target":       "🟢",
}

# Better DAM display using text on button label
def _cell_label(r: int, c: int, g: GameState, targets: list) -> str:
    from game import is_dark
    if not is_dark(r, c):
        return "⬜"
    if (r, c) == g.selected:
        return "🟡"
    if (r, c) in targets:
        return "🟢"
    v = g.board[r][c]
    if v == P1:     return "🔴"
    if v == P2:     return "🔵"
    if v == P1_DAM: return "👑🔴"
    if v == P2_DAM: return "👑🔵"
    return "⬛"

def build_board_keyboard(g: GameState) -> InlineKeyboardMarkup:
    targets: list = []
    if g.selected:
        sr, sc = g.selected
        targets = g.valid_targets(sr, sc)

    rows = []
    for r in range(8):
        row = []
        for c in range(8):
            label = _cell_label(r, c, g, targets)
            row.append(InlineKeyboardButton(
                text=label,
                callback_data=f"cell:{r}:{c}",
            ))
        rows.append(row)

    # Action buttons row
    actions = [
        InlineKeyboardButton(text="🏳 Menyerah", callback_data="resign"),
        InlineKeyboardButton(text="🤝 Seri",    callback_data="draw_offer"),
    ]
    rows.append(actions)
    return InlineKeyboardMarkup(inline_keyboard=rows)

def status_text(g: GameState, p1_name: str, p2_name: str) -> str:
    if g.winner is not None:
        if g.winner == 0:
            return "🤝 <b>Seri!</b>"
        winner_name = p1_name if g.winner == 1 else p2_name
        return f"🏆 <b>{winner_name} menang!</b>"

    turn_name = p1_name if g.turn == 1 else p2_name
    icon      = "🔴" if g.turn == 1 else "🔵"
    p1_count  = len(g.pieces_of(1))
    p2_count  = len(g.pieces_of(2))
    chain_note = " ⛓ <i>(makan berantai!)</i>" if g.chain_piece else ""
    must_note  = " ⚠️ <i>(wajib makan)</i>" if g.must_capture() and not g.chain_piece else ""
    return (
        f"🎯 <b>Dam-daman</b>\n"
        f"🔴 {p1_name}: <b>{p1_count}</b> bidak  |  🔵 {p2_name}: <b>{p2_count}</b> bidak\n\n"
        f"Giliran: {icon} <b>{turn_name}</b>{chain_note}{must_note}"
    )

# ── Session helpers ───────────────────────────────────────────────────────────

async def render_game(bot: Bot, chat_id: int, message_id: Optional[int] = None):
    g = games.get(chat_id)
    if not g:
        return
    try:
        p1_info = await bot.get_chat(g.player1_id)
        p2_info = await bot.get_chat(g.player2_id)
        p1_name = p1_info.first_name or "P1"
        p2_name = p2_info.first_name or "P2"
    except Exception:
        p1_name, p2_name = "P1", "P2"

    text = status_text(g, p1_name, p2_name)
    kb   = build_board_keyboard(g) if not g.is_game_over() else None

    if message_id:
        try:
            await bot.edit_message_text(
                text, chat_id=chat_id, message_id=message_id,
                parse_mode=ParseMode.HTML, reply_markup=kb,
            )
        except Exception:
            pass
    else:
        await bot.send_message(chat_id, text, parse_mode=ParseMode.HTML, reply_markup=kb)

# ── Commands ──────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(msg: Message):
    await msg.answer(
        "♟ <b>Dam-daman Bot</b>\n\n"
        "/challenge @username — tantang pemain\n"
        "/join — terima tantangan\n"
        "/cancel — batalkan tantangan / game\n"
        "/help — bantuan",
        parse_mode=ParseMode.HTML,
    )

@router.message(Command("help"))
async def cmd_help(msg: Message):
    await msg.answer(
        "📖 <b>Cara Main Dam-daman</b>\n\n"
        "1. Ketik /challenge @lawanmu\n"
        "2. Lawan ketik /join untuk menerima\n"
        "3. Klik bidak kamu (🔴/🔵) untuk memilih\n"
        "4. Klik kotak hijau 🟢 untuk melangkah\n\n"
        "<b>Aturan:</b>\n"
        "• Wajib makan jika ada kesempatan ⚠️\n"
        "• Makan berantai harus dilanjutkan ⛓\n"
        "• Bidak sampai ujung → jadi DAM 👑\n"
        "• DAM bisa bergerak 4 arah diagonal\n\n"
        "🏳 Menyerah | 🤝 Tawarkan seri",
        parse_mode=ParseMode.HTML,
    )

@router.message(Command("challenge"))
async def cmd_challenge(msg: Message, bot: Bot):
    chat_id = msg.chat.id
    if not msg.from_user:
        return

    if chat_id in games:
        return await msg.reply("⚠️ Sudah ada game berjalan. /cancel dulu.")

    # Cari @username dari argumen
    args = (msg.text or "").split(maxsplit=1)
    if len(args) < 2 or not args[1].startswith("@"):
        return await msg.reply("Contoh: /challenge @username")

    uname = args[1].lstrip("@")
    try:
        target = await bot.get_chat(f"@{uname}")
    except Exception:
        return await msg.reply(f"❌ User @{uname} tidak ditemukan.")

    if target.id == msg.from_user.id:
        return await msg.reply("❌ Tidak bisa tantang diri sendiri.")

    pending[chat_id] = msg.from_user.id
    challenger_name = msg.from_user.first_name or msg.from_user.username or "Seseorang"
    await msg.answer(
        f"⚔️ <b>{challenger_name}</b> menantang <b>@{uname}</b>!\n\n"
        f"@{uname}, ketik /join untuk menerima tantangan.",
        parse_mode=ParseMode.HTML,
    )

@router.message(Command("join"))
async def cmd_join(msg: Message, bot: Bot):
    chat_id = msg.chat.id
    if not msg.from_user:
        return

    if chat_id not in pending:
        return await msg.reply("❌ Tidak ada tantangan aktif. Minta seseorang /challenge dulu.")

    challenger_id = pending.pop(chat_id)
    if msg.from_user.id == challenger_id:
        return await msg.reply("❌ Kamu yang nantang, tunggu lawan /join.")

    g = GameState.new(p1_id=challenger_id, p2_id=msg.from_user.id)
    games[chat_id] = g

    try:
        p1_info = await bot.get_chat(challenger_id)
        p1_name = p1_info.first_name or "P1"
    except Exception:
        p1_name = "P1"
    p2_name = msg.from_user.first_name or "P2"

    await msg.answer(
        f"🎮 <b>Game dimulai!</b>\n"
        f"🔴 {p1_name} vs 🔵 {p2_name}\n\n"
        f"🔵 <b>{p2_name}</b> jalan duluan!",
        parse_mode=ParseMode.HTML,
    )
    await render_game(bot, chat_id)

@router.message(Command("cancel"))
async def cmd_cancel(msg: Message):
    chat_id = msg.chat.id
    if chat_id in pending:
        pending.pop(chat_id)
        return await msg.reply("✅ Tantangan dibatalkan.")
    if chat_id in games:
        games.pop(chat_id)
        return await msg.reply("✅ Game dibatalkan.")
    await msg.reply("Tidak ada tantangan atau game aktif.")

# ── Callback: klik cell ───────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("cell:"))
async def cb_cell(cq: CallbackQuery, bot: Bot):
    if not cq.from_user or not cq.message:
        return
    chat_id = cq.message.chat.id
    g = games.get(chat_id)
    if not g:
        return await cq.answer("Tidak ada game aktif.")
    if g.is_game_over():
        return await cq.answer("Game sudah selesai.")

    uid = cq.from_user.id
    if uid not in (g.player1_id, g.player2_id):
        return await cq.answer("Kamu bukan pemain di game ini.", show_alert=True)

    player = 1 if uid == g.player1_id else 2
    if player != g.turn:
        return await cq.answer("Bukan giliran kamu! ⏳")

    _, r_str, c_str = cq.data.split(":")
    r, c = int(r_str), int(c_str)

    from game import is_dark
    if not is_dark(r, c):
        return await cq.answer()

    # Fase: belum pilih bidak
    if g.selected is None and g.chain_piece is None:
        if owner(g.cell(r, c)) != player:
            return await cq.answer("Pilih bidakmu sendiri.")
        if (r, c) not in g.valid_sources():
            hint = "Wajib pilih bidak yang bisa makan! ⚠️" if g.must_capture() else "Bidak ini tidak punya gerakan."
            return await cq.answer(hint)
        g.selected = (r, c)
        await cq.answer()
        await render_game(bot, chat_id, message_id=cq.message.message_id)
        return

    # Fase: sudah pilih bidak, atau chain
    src = g.chain_piece or g.selected
    if src is None:
        return await cq.answer()

    # Klik ulang bidak yang sama → deselect
    if (r, c) == src and g.chain_piece is None:
        g.selected = None
        await cq.answer()
        await render_game(bot, chat_id, message_id=cq.message.message_id)
        return

    # Klik bidak sendiri yang lain → ganti pilihan (hanya jika bukan chain)
    if g.chain_piece is None and owner(g.cell(r, c)) == player and (r, c) in g.valid_sources():
        g.selected = (r, c)
        await cq.answer()
        await render_game(bot, chat_id, message_id=cq.message.message_id)
        return

    # Coba gerakkan
    fr, fc = src
    ok = g.move(fr, fc, r, c)
    if not ok:
        await cq.answer("Gerakan tidak valid. ❌")
        return

    await cq.answer()

    if g.is_game_over():
        await render_game(bot, chat_id, message_id=cq.message.message_id)
        games.pop(chat_id, None)
    else:
        await render_game(bot, chat_id, message_id=cq.message.message_id)

# ── Callback: resign ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "resign")
async def cb_resign(cq: CallbackQuery, bot: Bot):
    if not cq.from_user or not cq.message:
        return
    chat_id = cq.message.chat.id
    g = games.get(chat_id)
    if not g or g.is_game_over():
        return await cq.answer()

    uid = cq.from_user.id
    if uid not in (g.player1_id, g.player2_id):
        return await cq.answer("Kamu bukan pemain.", show_alert=True)

    player = 1 if uid == g.player1_id else 2
    g.winner = 2 if player == 1 else 1
    await cq.answer("🏳 Kamu menyerah.")
    await render_game(bot, chat_id, message_id=cq.message.message_id)
    games.pop(chat_id, None)

# ── Callback: draw offer ──────────────────────────────────────────────────────

@router.callback_query(F.data == "draw_offer")
async def cb_draw_offer(cq: CallbackQuery, bot: Bot):
    if not cq.from_user or not cq.message:
        return
    chat_id = cq.message.chat.id
    g = games.get(chat_id)
    if not g or g.is_game_over():
        return await cq.answer()

    uid = cq.from_user.id
    if uid not in (g.player1_id, g.player2_id):
        return await cq.answer("Kamu bukan pemain.", show_alert=True)

    player = 1 if uid == g.player1_id else 2

    if g.draw_offered_by is None:
        g.draw_offered_by = player
        await cq.answer("Tawaran seri dikirim ke lawan. 🤝")
        name = cq.from_user.first_name or "Lawan"
        await bot.send_message(
            chat_id,
            f"🤝 <b>{name}</b> menawarkan seri. Klik 🤝 Seri untuk menerima.",
            parse_mode=ParseMode.HTML,
        )
    elif g.draw_offered_by != player:
        # Lawan menerima
        g.winner = 0
        await cq.answer("Seri disepakati! 🤝")
        await render_game(bot, chat_id, message_id=cq.message.message_id)
        games.pop(chat_id, None)
    else:
        await cq.answer("Kamu sudah menawarkan seri, tunggu respons lawan.")

# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN wajib diisi di .env!")

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp  = Dispatcher()
    dp.include_router(router)
    log.info("Dam-daman bot started.")
    await dp.start_polling(bot, allowed_updates=["message", "callback_query"])

if __name__ == "__main__":
    asyncio.run(main())
