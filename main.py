"""
main.py — Bot Dam-daman Telegram (inline keyboard)
"""
import asyncio
import logging
import os
import random
from typing import Dict, Optional

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ButtonStyle, ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    BufferedInputFile, CallbackQuery,
    InlineKeyboardButton, InlineKeyboardMarkup, Message,
)
from dotenv import load_dotenv

from game import Game, WHITE, BLACK
from renderer import draw_board

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("damdaman")

OWNER_ID   = int(os.getenv("OWNER_ID", "0"))
INFO_LINK  = os.getenv("INFO_LINK", "")

games:        Dict[int, Game]           = {}
pending:      Dict[int, tuple]          = {}
board_msg_id: Dict[int, Optional[int]]  = {}

router = Router()

# ── Keyboard helpers ──────────────────────────────────────────────────────────

def kb_slots(slots: list[int], prefix: str, style: ButtonStyle = ButtonStyle.PRIMARY) -> InlineKeyboardMarkup:
    """Buat keyboard dari list slot, 4 per baris."""
    rows, row = [], []
    for s in sorted(slots):
        row.append(InlineKeyboardButton(text=str(s), callback_data=f"{prefix}:{s}", style=style))
        if len(row) == 4:
            rows.append(row); row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_resign() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🏳 Menyerah", callback_data="resign")
    ]])

# ── Board sender ──────────────────────────────────────────────────────────────

async def send_board(bot: Bot, chat_id: int, game: Game, caption: str,
                     reply_markup=None, sources: list = None, targets: list = None):
    old = board_msg_id.pop(chat_id, None)

    img_bytes = draw_board(game, highlight_sources=sources, highlight_targets=targets)
    sent = await bot.send_photo(
        chat_id,
        photo=BufferedInputFile(img_bytes, "board.jpg"),
        caption=caption,
        parse_mode=ParseMode.HTML,
        reply_markup=reply_markup,
    )
    board_msg_id[chat_id] = sent.message_id

    # Hapus pesan lama setelah kirim baru (tidak blocking)
    if old:
        try:
            await bot.delete_message(chat_id, old)
        except Exception:
            pass


def turn_caption(game: Game) -> str:
    name  = game.p1_name if game.turn == WHITE else game.p2_name
    color = "⬜ Putih" if game.turn == WHITE else "⬛ Hitam"
    return f"Giliran <b>{name}</b> ({color})\nPilih bidak yang digerakkan:"


# ── Commands ──────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(msg: Message, bot: Bot):
    me = await bot.get_me()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        # baris 1 — 1 button
        [InlineKeyboardButton(text="➕ Tambah ke Grup", url=f"https://t.me/{me.username}?startgroup=true")],
        # baris 2 — 2 button
        [
            InlineKeyboardButton(text="📋 Fitur", callback_data="start:fitur"),
            InlineKeyboardButton(text="👤 Owner", url=f"tg://user?id={OWNER_ID}"),
        ],
        # baris 3 — 1 button
        [InlineKeyboardButton(text="📢 Info & Update", url=INFO_LINK)],
    ])
    await msg.answer(
        "♟ <b>Dam-daman Bot</b>\n\n"
        "Bot permainan <b>Dam-daman</b> untuk grup Telegram!\n"
        "Tantang temanmu dan jadilah yang pertama memindahkan\n"
        "semua pion ke sisi lawan.\n\n"
        "• 2 pemain per game\n"
        "• Papan 4×8 (32 slot)\n"
        "• Gerak & lompat 4 arah\n"
        "• Wajib lompat jika ada kesempatan",
        reply_markup=kb,
    )


@router.message(Command("help"))
async def cmd_help(msg: Message):
    await msg.answer(
        "📖 <b>Cara Main</b>\n\n"
        "1. /mulai → /join\n"
        "2. Klik button nomor bidak → klik nomor tujuan\n\n"
        "⬜ Putih: slot 1,2,9,10,17,18,25,26 → target kanan\n"
        "⬛ Hitam: slot 7,8,15,16,23,24,31,32 → target kiri\n\n"
        "Lompati pion lawan jika ada slot kosong di baliknya.\n"
        "Jika ada lompatan, wajib lompat.",
        parse_mode=ParseMode.HTML,
    )


@router.message(Command("mulai"))
async def cmd_mulai(msg: Message):
    cid = msg.chat.id
    if not msg.from_user:
        return
    if cid in games:
        return await msg.reply("⚠️ Ada game berjalan. Selesaikan dulu atau /menyerah.")
    pending[cid] = (msg.from_user.id, msg.from_user.first_name or "P1")
    await msg.answer(
        f"⚔️ <b>{msg.from_user.first_name}</b> menantang!\nKetik /join untuk menerima.",
        parse_mode=ParseMode.HTML,
    )


@router.message(Command("join"))
async def cmd_join(msg: Message, bot: Bot):
    cid = msg.chat.id
    if not msg.from_user:
        return
    if cid not in pending:
        return await msg.reply("❌ Tidak ada tantangan aktif.")
    p1_id, p1_name = pending.pop(cid)
    if msg.from_user.id == p1_id:
        return await msg.reply("❌ Kamu yang nantang, tunggu lawan.")

    p2_id, p2_name = msg.from_user.id, msg.from_user.first_name or "P2"

    if random.random() < 0.5:
        game = Game(p1_id, p2_id, p1_name, p2_name)
        info = f"⬜ {p1_name} = Putih | ⬛ {p2_name} = Hitam"
    else:
        game = Game(p2_id, p1_id, p2_name, p1_name)
        info = f"⬜ {p2_name} = Putih | ⬛ {p1_name} = Hitam"

    games[cid] = game
    board_msg_id[cid] = None

    await msg.answer(f"🎮 <b>Game dimulai!</b>\n{info}", parse_mode=ParseMode.HTML)

    sources = game.all_valid_sources()
    await send_board(bot, cid, game, turn_caption(game),
                     reply_markup=kb_slots(sources, "pick", ButtonStyle.PRIMARY),
                     sources=sources)


@router.message(Command("menyerah"))
async def cmd_resign(msg: Message, bot: Bot):
    cid  = msg.chat.id
    game = games.get(cid)
    if not game or not msg.from_user:
        return await msg.reply("Tidak ada game aktif.")
    uid = msg.from_user.id
    if uid not in (game.p1_id, game.p2_id):
        return await msg.reply("Kamu bukan pemain.")
    loser  = WHITE if uid == game.p1_id else BLACK
    game.winner = BLACK if loser == WHITE else WHITE
    wname = game.winner_name()
    await msg.answer(f"🏳 {msg.from_user.first_name} menyerah!\n🏆 <b>{wname} menang!</b>",
                     parse_mode=ParseMode.HTML)
    await send_board(bot, cid, game, f"🏆 <b>{wname} menang!</b>")
    games.pop(cid, None); board_msg_id.pop(cid, None)


# ── Callbacks ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "start:fitur")
async def cb_fitur(cq: CallbackQuery):
    await cq.answer(
        "📋 Fitur Dam-daman:\n\n"
        "/mulai — buka tantangan\n"
        "/join — terima tantangan\n"
        "/menyerah — menyerah\n"
        "/help — cara main\n\n"
        "Klik nomor bidak → pilih tujuan",
        show_alert=True,
    )


@router.callback_query(F.data.startswith("pick:"))
async def cb_pick(cq: CallbackQuery, bot: Bot):
    """Pemain pilih bidak."""
    if not cq.from_user or not cq.message:
        return
    cid  = cq.message.chat.id
    game = games.get(cid)
    if not game or game.is_over():
        return await cq.answer()
    if cq.from_user.id != game.current_player_id():
        return await cq.answer("Bukan giliranmu! ⏳", show_alert=True)

    slot = int(cq.data.split(":")[1])
    moves = game.valid_moves(slot)
    if not moves:
        return await cq.answer("Bidak ini tidak punya gerakan.", show_alert=True)

    game.selected = slot
    await cq.answer()
    await send_board(bot, cid, game,
        f"✅ Bidak <b>{slot}</b> dipilih.\nGerakkan kemana?",
        reply_markup=kb_slots(moves, "move", ButtonStyle.SUCCESS),
        sources=[slot], targets=moves)


@router.callback_query(F.data.startswith("move:"))
async def cb_move(cq: CallbackQuery, bot: Bot):
    """Pemain pilih tujuan."""
    if not cq.from_user or not cq.message:
        return
    cid  = cq.message.chat.id
    game = games.get(cid)
    if not game or game.is_over():
        return await cq.answer()
    if cq.from_user.id != game.current_player_id():
        return await cq.answer("Bukan giliranmu! ⏳", show_alert=True)

    frm = game.selected
    to  = int(cq.data.split(":")[1])

    if frm is None:
        return await cq.answer("Pilih bidak dulu.", show_alert=True)

    ok = game.move(frm, to)
    await cq.answer()

    if not ok:
        moves = game.valid_moves(frm)
        await send_board(bot, cid, game,
            f"❌ Tidak bisa ke slot {to}.\nGerakkan kemana?",
            reply_markup=kb_slots(moves, "move", ButtonStyle.SUCCESS),
            sources=[frm], targets=moves)
        return

    if game.is_over():
        wname = game.winner_name()
        await send_board(bot, cid, game, f"🏆 <b>{wname} menang!</b>")
        games.pop(cid, None); board_msg_id.pop(cid, None)
    else:
        sources = game.all_valid_sources()
        await send_board(bot, cid, game, turn_caption(game),
                         reply_markup=kb_slots(sources, "pick", ButtonStyle.PRIMARY),
                         sources=sources)


@router.callback_query(F.data == "resign")
async def cb_resign(cq: CallbackQuery, bot: Bot):
    if not cq.from_user or not cq.message:
        return
    cid  = cq.message.chat.id
    game = games.get(cid)
    if not game:
        return await cq.answer()
    uid = cq.from_user.id
    if uid not in (game.p1_id, game.p2_id):
        return await cq.answer("Kamu bukan pemain.", show_alert=True)
    loser      = WHITE if uid == game.p1_id else BLACK
    game.winner = BLACK if loser == WHITE else WHITE
    wname      = game.winner_name()
    await cq.answer("🏳 Menyerah.")
    await send_board(bot, cid, game, f"🏆 <b>{wname} menang!</b>")
    games.pop(cid, None); board_msg_id.pop(cid, None)


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
