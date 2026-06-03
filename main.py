"""
main.py — Bot Dam-daman Telegram
Input: nomor slot via teks (bukan inline keyboard)
Alur: /mulai → tantang → /join → main
"""
import asyncio
import logging
import os
import random
from typing import Dict, Optional

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import BufferedInputFile, Message
from dotenv import load_dotenv

from game import Game, WHITE, BLACK
from renderer import draw_board

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("damdaman")

# ── State ─────────────────────────────────────────────────────────────────────
games:   Dict[int, Game]               = {}   # chat_id → Game
pending: Dict[int, tuple]              = {}   # chat_id → (user_id, name)
board_msg_id: Dict[int, Optional[int]] = {}   # chat_id → message_id gambar terakhir

router = Router()


# ── Helpers ───────────────────────────────────────────────────────────────────

async def send_board(bot: Bot, chat_id: int, game: Game, caption: str,
                     sources: list = None, targets: list = None):
    """Kirim/update gambar papan. Hapus gambar lama dulu."""
    old = board_msg_id.get(chat_id)
    if old:
        try:
            await bot.delete_message(chat_id, old)
        except Exception:
            pass

    img_bytes = draw_board(game, highlight_sources=sources, highlight_targets=targets)
    sent = await bot.send_photo(
        chat_id,
        photo=BufferedInputFile(img_bytes, filename="board.jpg"),
        caption=caption,
        parse_mode=ParseMode.HTML,
    )
    board_msg_id[chat_id] = sent.message_id


def turn_prompt(game: Game) -> str:
    name  = game.p1_name if game.turn == WHITE else game.p2_name
    color = "⬜ Putih" if game.turn == WHITE else "⬛ Hitam"
    return (
        f"Sekarang giliran <b>{name}</b> ({color}) untuk bermain\n"
        f"<i>Bidak mana yang digerakkan?</i> (ketik nomor slot)"
    )


# ── Commands ──────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(msg: Message):
    await msg.answer(
        "♟ <b>Dam-daman Bot</b>\n\n"
        "/mulai — tantang lawan di grup\n"
        "/join — terima tantangan\n"
        "/menyerah — menyerah\n"
        "/help — cara main",
        parse_mode=ParseMode.HTML,
    )


@router.message(Command("help"))
async def cmd_help(msg: Message):
    await msg.answer(
        "📖 <b>Cara Main Dam-daman</b>\n\n"
        "1. /mulai — buka tantangan\n"
        "2. Lawan ketik /join\n"
        "3. Giliran ditentukan random\n"
        "4. Ketik <b>nomor slot</b> bidak yang mau digerakkan\n"
        "5. Ketik <b>nomor tujuan</b>\n\n"
        "<b>Aturan:</b>\n"
        "• ⬜ Putih mulai di slot 1,2,9,10,17,18,25,26 (kiri)\n"
        "• ⬛ Hitam mulai di slot 7,8,15,16,23,24,31,32 (kanan)\n"
        "• Tujuan putih: isi semua slot kanan\n"
        "• Tujuan hitam: isi semua slot kiri\n"
        "• Gerak 1 langkah ke 4 arah jika kosong\n"
        "• Lompati pion lawan jika ada slot kosong di baliknya\n"
        "• Jika ada lompatan, lompatan wajib dilakukan",
        parse_mode=ParseMode.HTML,
    )


@router.message(Command("mulai"))
async def cmd_mulai(msg: Message):
    cid = msg.chat.id
    if not msg.from_user:
        return
    if cid in games:
        return await msg.reply("⚠️ Sudah ada game berjalan. /menyerah dulu.")
    pending[cid] = (msg.from_user.id, msg.from_user.first_name or "P1")
    await msg.answer(
        f"⚔️ <b>{msg.from_user.first_name}</b> menantang! "
        "Siapa yang mau main? Ketik /join",
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

    p2_id   = msg.from_user.id
    p2_name = msg.from_user.first_name or "P2"

    # Random siapa dapat putih/hitam
    if random.random() < 0.5:
        game = Game(p1_id, p2_id, p1_name, p2_name)  # p1=putih p2=hitam
        color_info = f"⬜ {p1_name} = Putih | ⬛ {p2_name} = Hitam"
    else:
        game = Game(p2_id, p1_id, p2_name, p1_name)  # p2=putih p1=hitam
        color_info = f"⬜ {p2_name} = Putih | ⬛ {p1_name} = Hitam"

    games[cid] = game
    board_msg_id[cid] = None

    await msg.answer(
        f"🎮 <b>Game dimulai!</b>\n{color_info}\n\n"
        f"Putih duluan!",
        parse_mode=ParseMode.HTML,
    )
    sources = game.all_valid_sources()
    await send_board(bot, cid, game, turn_prompt(game), sources=sources)


@router.message(Command("menyerah"))
async def cmd_resign(msg: Message, bot: Bot):
    cid = msg.chat.id
    if not msg.from_user:
        return
    game = games.get(cid)
    if not game:
        return await msg.reply("Tidak ada game aktif.")
    uid = msg.from_user.id
    if uid not in (game.p1_id, game.p2_id):
        return await msg.reply("Kamu bukan pemain.")

    loser  = WHITE if uid == game.p1_id else BLACK
    winner = BLACK if loser == WHITE else WHITE
    game.winner = winner
    wname = game.winner_name()
    await msg.answer(f"🏳 <b>{msg.from_user.first_name} menyerah!</b>\n🏆 {wname} menang!", parse_mode=ParseMode.HTML)
    await send_board(bot, cid, game, f"🏆 <b>{wname} menang!</b>")
    games.pop(cid, None)
    board_msg_id.pop(cid, None)


# ── Main game input handler ───────────────────────────────────────────────────

@router.message(F.text.regexp(r"^\d+$"))
async def handle_number(msg: Message, bot: Bot):
    cid  = msg.chat.id
    game = games.get(cid)
    if not game or game.is_over():
        return
    if not msg.from_user or msg.from_user.id != game.current_player_id():
        return  # bukan giliran dia

    num = int(msg.text.strip())
    if num < 1 or num > 32:
        return await msg.reply("❌ Nomor slot harus 1–32.")

    # Fase 1: belum pilih bidak
    if game.selected is None:
        if game.board.get(num) != game.turn:
            return await msg.reply("❌ Itu bukan bidakmu. Pilih slot yang ada bidakmu.")
        moves = game.valid_moves(num)
        if not moves:
            return await msg.reply("❌ Bidak itu tidak punya gerakan.")
        game.selected = num
        sources = [num]
        await send_board(bot, cid, game,
            f"✅ Bidak slot <b>{num}</b> dipilih.\n"
            f"<i>Bidak digerakkan kemana?</i> (ketik nomor tujuan)\n"
            f"Tujuan valid: {', '.join(map(str, moves))}",
            sources=sources, targets=moves)
        return

    # Fase 2: sudah pilih bidak, sekarang pilih tujuan
    frm = game.selected
    ok  = game.move(frm, num)
    if not ok:
        moves = game.valid_moves(frm)
        await send_board(bot, cid, game,
            f"❌ Tidak bisa menggerakkan bidak kesitu.\n"
            f"<i>Bidak digerakkan kemana?</i>\n"
            f"Tujuan valid: {', '.join(map(str, moves))}",
            sources=[frm], targets=moves)
        return

    if game.is_over():
        wname = game.winner_name()
        await send_board(bot, cid, game, f"🏆 <b>{wname} menang!</b>")
        games.pop(cid, None)
        board_msg_id.pop(cid, None)
    else:
        sources = game.all_valid_sources()
        await send_board(bot, cid, game, turn_prompt(game), sources=sources)


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN wajib diisi di .env!")
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp  = Dispatcher()
    dp.include_router(router)
    log.info("Dam-daman bot started.")
    await dp.start_polling(bot, allowed_updates=["message"])

if __name__ == "__main__":
    asyncio.run(main())
