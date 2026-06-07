"""
main.py — Bot Dam-daman Telegram (inline keyboard)
"""
import asyncio
import logging
import os
import random
import sys
from typing import Dict, Optional

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ButtonStyle, ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    BufferedInputFile, CallbackQuery,
    InlineKeyboardButton, InlineKeyboardMarkup, Message,
)
from dotenv import load_dotenv

from game import Game, WHITE, BLACK
from renderer import draw_board
from db import init_db, log_new_game, log_move, log_game_end

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("damdaman")

OWNER_ID   = int(os.getenv("OWNER_ID", "0"))
INFO_LINK  = os.getenv("INFO_LINK", "")

games:         Dict[int, Game]           = {}
pending:       Dict[int, tuple]          = {}
board_msg_id:  Dict[int, Optional[int]]  = {}
pending_moves: Dict[int, list]           = {}   # cid → valid move slots saat menunggu input teks
game_db_id:    Dict[int, int]            = {}   # cid → db game id
move_counter:  Dict[int, int]            = {}   # cid → move number

router = Router()

# ── Keyboard helpers ──────────────────────────────────────────────────────────

def kb_slots(slots: list[int], prefix: str, style: ButtonStyle = ButtonStyle.PRIMARY) -> InlineKeyboardMarkup:
    """Buat keyboard dari list slot, 4 per baris. Tambah tombol Menyerah."""
    rows, row = [], []
    for s in sorted(slots):
        row.append(InlineKeyboardButton(text=str(s), callback_data=f"{prefix}:{s}", style=style))
        if len(row) == 4:
            rows.append(row); row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton(text="🏳 Menyerah", callback_data="resign")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
    uid   = game.p1_id if game.turn == WHITE else game.p2_id
    name  = game.p1_name if game.turn == WHITE else game.p2_name
    color = "⬜ Putih" if game.turn == WHITE else "⬛ Hitam"
    mention = f'<a href="tg://user?id={uid}">{name}</a>'
    return f"<blockquote>Giliran {mention} ({color})\nPilih bidak:</blockquote>"


# ── Commands ──────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(msg: Message, bot: Bot):
    me = await bot.get_me()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Tambah ke Grup", url=f"https://t.me/{me.username}?startgroup=true")],
        [
            InlineKeyboardButton(text="📋 Fitur", callback_data="start:fitur"),
            InlineKeyboardButton(text="👤 Owner", url=f"tg://user?id={OWNER_ID}"),
        ],
        [
            InlineKeyboardButton(text="📜 Rules", callback_data="start:rules"),
            InlineKeyboardButton(text="🔒 Privasi", callback_data="start:privasi"),
        ],
        [InlineKeyboardButton(text="📢 Info & Update", url=INFO_LINK)],
    ])
    await msg.answer(
        "┏━━━━━━━━━━━━━━━━━━━┓\n"
        "┃  ♟ <b>DAM-DAMAN BOT</b>  ♟  ┃\n"
        "┗━━━━━━━━━━━━━━━━━━━┛\n\n"
        "🎮 Mainkan permainan tradisional\n"
        "<b>Dam-daman</b> langsung di Telegram!\n\n"
        "┌─────────────────────┐\n"
        "│ ⬜ vs ⬛ • 2 Pemain        │\n"
        "│ 📐 Papan 4×8 (32 slot)   │\n"
        "│ 🏃 Gerak & Lompat          │\n"
        "│ 🏆 Finish duluan = Menang │\n"
        "└─────────────────────┘\n\n"
        "💡 <i>Tambahkan bot ke grup lalu\n"
        "ketik /new untuk mulai!</i>",
        reply_markup=kb,
    )


@router.message(Command("help"))
async def cmd_help(msg: Message):
    await msg.answer(
        "<blockquote>📖 <b>Cara Main</b>\n\n"
        "1. /new → Join\n"
        "2. Klik button nomor bidak → ketik nomor tujuan\n\n"
        "⬜ Putih: slot 1,2,9,10,17,18,25,26 → target kanan\n"
        "⬛ Hitam: slot 7,8,15,16,23,24,31,32 → target kiri\n\n"
        "Ketik /rules untuk aturan lengkap.</blockquote>",
        parse_mode=ParseMode.HTML,
    )


@router.message(Command("rules"))
async def cmd_rules(msg: Message):
    await msg.answer(
        "<blockquote>📜 <b>Aturan Dam-daman</b>\n\n"
        "<b>Tujuan:</b>\n"
        "Pemain yang pertama kali berhasil menempatkan ke-8 bidaknya ke area tujuan (finish) lawan dinyatakan menang.\n\n"
        "<b>Gerakan:</b>\n"
        "• Bidak dapat bergerak 1 langkah ke depan (maju lurus) atau 1 langkah ke samping (atas/bawah).\n"
        "• Bidak <b>tidak dapat</b> bergerak mundur atau diagonal dalam 1 langkah.\n\n"
        "<b>Lompatan:</b>\n"
        "• Bidak dapat melompati bidak lain (kawan maupun lawan) secara diagonal ke depan atau lurus ke depan.\n"
        "• Bidak yang dilompati <b>tidak</b> dihapus dari papan.\n"
        "• Pemain dapat terus melompat hingga sampai ke tujuan selama ada bidak yang dapat dilompati.\n\n"
        "<b>Menang:</b>\n"
        "Pemain yang terlebih dahulu menyusun 8 bidaknya di area finish lawan memenangkan permainan.</blockquote>",
        parse_mode=ParseMode.HTML,
    )


@router.message(Command("privasi"))
async def cmd_privasi(msg: Message):
    await msg.answer(
        "<blockquote>🔒 <b>Kebijakan Privasi</b>\n"
        "Berlaku sejak: 5 Juni 2025\n\n"
        "Selamat datang di pernyataan kebijakan privasi <b>Dam-daman Bot</b>. "
        "Di sinilah kami menjelaskan bagaimana kami menangani Data Pribadi Anda.\n\n"
        "<b>1. Data yang kami kumpulkan</b>\n"
        "Data yang kami kumpulkan tidak lain adalah user ID, nama depan, "
        "chat ID, dan data permainan (riwayat langkah). "
        "Kami tidak menyimpan pesan Anda. Data digunakan untuk keperluan permainan "
        "agar dapat berjalan tanpa masalah.\n\n"
        "<b>2. Dari mana data tersebut berasal?</b>\n"
        "Data ini secara otomatis diberikan oleh Telegram saat Anda menggunakan bot ini.\n\n"
        "<b>3. Data yang kami bagikan kepada pihak ketiga</b>\n"
        "Kami tidak pernah membagikan data Anda kepada pihak ketiga.\n\n"
        "<i>Kebijakan Privasi ini dapat berubah seiring waktu tanpa pemberitahuan lebih lanjut.</i></blockquote>",
        parse_mode=ParseMode.HTML,
    )


@router.message(Command("reboot"))
async def cmd_reboot(msg: Message):
    if not msg.from_user or msg.from_user.id != OWNER_ID:
        return
    await msg.reply("♻️ Rebooting...")
    os.execv(sys.executable, [sys.executable] + sys.argv)


@router.message(Command("room"))
async def cmd_room(msg: Message):
    if not msg.from_user or msg.from_user.id != OWNER_ID:
        return
    if not games:
        return await msg.reply("Tidak ada room aktif.")
    lines = []
    for cid, game in games.items():
        color = "⬜" if game.turn == WHITE else "⬛"
        lines.append(f"• <code>{cid}</code> — {game.p1_name} vs {game.p2_name} ({color} giliran)")
    await msg.reply("<blockquote>🏠 <b>Room Aktif:</b>\n" + "\n".join(lines) + "</blockquote>", parse_mode=ParseMode.HTML)


@router.message(Command("new"))
async def cmd_mulai(msg: Message):
    cid = msg.chat.id
    if not msg.from_user:
        return
    if cid in games:
        return await msg.reply("⚠️ Ada game berjalan. Selesaikan dulu atau /menyerah.")
    if cid in pending and pending[cid][0] == msg.from_user.id:
        return await msg.reply("⚠️ Kamu sudah buka tantangan. Tunggu lawan join.")
    pending[cid] = (msg.from_user.id, msg.from_user.first_name or "P1")
    kb_join = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⚔️ Join", callback_data="join")
    ]])
    await msg.answer(
        f"<blockquote>⚔️ <b>{msg.from_user.first_name}</b> menantang!\nTekan tombol untuk menerima.</blockquote>",
        parse_mode=ParseMode.HTML,
        reply_markup=kb_join,
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
    game_db_id[cid] = await log_new_game(cid, game.p1_id, game.p1_name, game.p2_id, game.p2_name, "W", game.board)
    move_counter[cid] = 0

    await msg.answer(f"<blockquote>🎮 <b>Game dimulai!</b>\n🏠 <code>#rm{cid}</code>\n{info}</blockquote>", parse_mode=ParseMode.HTML)
    sources = game.all_valid_sources()
    await send_board(bot, cid, game, turn_caption(game),
                     reply_markup=kb_slots(sources, "pick", ButtonStyle.PRIMARY))


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
    await msg.answer(f"<blockquote>🏳 {msg.from_user.first_name} menyerah!\n🏆 <b>{wname} menang!</b></blockquote>",
                     parse_mode=ParseMode.HTML)
    await send_board(bot, cid, game, f"<blockquote>🏆 <b>{wname} menang!</b></blockquote>")
    await log_game_end(game_db_id.get(cid, 0), wname)
    games.pop(cid, None); board_msg_id.pop(cid, None)
    game_db_id.pop(cid, None); move_counter.pop(cid, None)
    pending_moves.pop(cid, None)


# ── Callbacks ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "start:fitur")
async def cb_fitur(cq: CallbackQuery):
    await cq.answer(
        "📋 Fitur Dam-daman:\n\n"
        "/new — buka tantangan\n"
        "/menyerah — menyerah\n"
        "/rules — aturan\n"
        "/privasi — kebijakan privasi\n\n"
        "Klik nomor bidak → ketik tujuan",
        show_alert=True,
    )


@router.callback_query(F.data == "start:rules")
async def cb_rules(cq: CallbackQuery):
    await cq.answer()
    await cq.message.answer(
        "<blockquote>📜 <b>Aturan Dam-daman</b>\n\n"
        "• Gerak: maju lurus / menyamping 1 langkah\n"
        "• Lompat: diagonal/lurus ke depan, lewati bidak apapun\n"
        "• Dapat terus melompat selama ada bidak yang bisa dilompati\n"
        "• Bidak yang dilompati TIDAK dihapus\n"
        "• Menang: 8 bidak sampai di area finish lawan duluan</blockquote>",
        parse_mode=ParseMode.HTML,
    )


@router.callback_query(F.data == "start:privasi")
async def cb_privasi(cq: CallbackQuery):
    await cq.answer()
    await cq.message.answer(
        "<blockquote>🔒 <b>Kebijakan Privasi</b>\n"
        "Berlaku sejak: 5 Juni 2025\n\n"
        "• Data: user ID, nama, chat ID, riwayat langkah\n"
        "• Tidak menyimpan pesan pribadi\n"
        "• Tidak membagikan data ke pihak ketiga\n"
        "• Data digunakan hanya untuk jalannya permainan</blockquote>",
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="📄 Selengkapnya", callback_data="privasi:full")
        ]]),
    )


@router.callback_query(F.data == "privasi:full")
async def cb_privasi_full(cq: CallbackQuery):
    await cq.answer()
    await cq.message.edit_text(
        "<blockquote>🔒 <b>Kebijakan Privasi</b>\n"
        "Berlaku sejak: 5 Juni 2025\n\n"
        "Selamat datang di pernyataan kebijakan privasi <b>Dam-daman Bot</b>. "
        "Di sinilah kami menjelaskan bagaimana kami menangani Data Pribadi Anda.\n\n"
        "<b>1. Data yang kami kumpulkan</b>\n"
        "Data yang kami kumpulkan tidak lain adalah user ID, nama depan, "
        "chat ID, dan data permainan (riwayat langkah). "
        "Kami tidak menyimpan pesan Anda. Data digunakan untuk keperluan permainan "
        "agar dapat berjalan tanpa masalah.\n\n"
        "<b>2. Dari mana data tersebut berasal?</b>\n"
        "Data ini secara otomatis diberikan oleh Telegram saat Anda menggunakan bot ini.\n\n"
        "<b>3. Data yang kami bagikan kepada pihak ketiga</b>\n"
        "Kami tidak pernah membagikan data Anda kepada pihak ketiga.\n\n"
        "<i>Kebijakan Privasi ini dapat berubah seiring waktu tanpa pemberitahuan lebih lanjut.</i></blockquote>",
        parse_mode=ParseMode.HTML,
    )





@router.callback_query(F.data == "join")
async def cb_join(cq: CallbackQuery, bot: Bot):
    if not cq.from_user or not cq.message:
        return
    cid = cq.message.chat.id
    if cid not in pending:
        return await cq.answer("❌ Tidak ada tantangan aktif.", show_alert=True)
    p1_id, p1_name = pending[cid]
    if cq.from_user.id == p1_id:
        return await cq.answer("❌ Kamu yang nantang, tunggu lawan.", show_alert=True)

    pending.pop(cid)
    p2_id, p2_name = cq.from_user.id, cq.from_user.first_name or "P2"

    if random.random() < 0.5:
        game = Game(p1_id, p2_id, p1_name, p2_name)
        info = f"⬜ {p1_name} = Putih | ⬛ {p2_name} = Hitam"
    else:
        game = Game(p2_id, p1_id, p2_name, p1_name)
        info = f"⬜ {p2_name} = Putih | ⬛ {p1_name} = Hitam"

    games[cid] = game
    board_msg_id[cid] = None
    game_db_id[cid] = await log_new_game(cid, game.p1_id, game.p1_name, game.p2_id, game.p2_name, "W", game.board)
    move_counter[cid] = 0

    await cq.answer()
    await cq.message.edit_text(f"<blockquote>🎮 <b>Game dimulai!</b>\n🏠 <code>#rm{cid}</code>\n{info}</blockquote>", parse_mode=ParseMode.HTML)
    sources = game.all_valid_sources()
    await send_board(bot, cid, game, turn_caption(game),
                     reply_markup=kb_slots(sources, "pick", ButtonStyle.PRIMARY))


@router.callback_query(F.data.startswith("pick:"))
async def cb_pick(cq: CallbackQuery, bot: Bot):
    if not cq.from_user or not cq.message:
        return
    cid  = cq.message.chat.id
    game = games.get(cid)
    if not game or game.is_over():
        return await cq.answer()
    if cq.from_user.id != game.current_player_id():
        return await cq.answer("Bukan giliranmu! ⏳", show_alert=True)

    slot = int(cq.data.split(":")[1])
    if slot not in game.all_valid_sources():
        return await cq.answer("Bidak ini tidak bisa dipilih sekarang.", show_alert=True)
    moves = game.valid_moves(slot)
    if not moves:
        return await cq.answer("Bidak ini tidak punya gerakan.", show_alert=True)

    game.selected = slot
    pending_moves[cid] = moves
    await cq.answer()
    await send_board(bot, cid, game,
        f"<blockquote>✅ Bidak <b>{slot}</b> dipilih. Pilih tujuan:</blockquote>",
        sources=[slot], targets=moves,
        reply_markup=kb_slots(moves, "dest", ButtonStyle.SECONDARY))


@router.message(F.text.regexp(r"^\d+$"))
async def on_move_input(msg: Message, bot: Bot):
    if not msg.from_user:
        return
    cid  = msg.chat.id
    game = games.get(cid)
    if not game or game.is_over():
        return
    if msg.from_user.id != game.current_player_id():
        return
    moves = pending_moves.get(cid)
    if not moves or not game.selected:
        return

    num = int(msg.text.strip())

    # Stop chain jump
    if num == 0:
        pending_moves.pop(cid, None)
        game.turn = BLACK if game.turn == WHITE else WHITE
        game.selected = None
        sources = game.all_valid_sources()
        await send_board(bot, cid, game, turn_caption(game),
                         reply_markup=kb_slots(sources, "pick", ButtonStyle.PRIMARY))
        return

    if num not in moves:
        return await msg.reply("❌ Tujuan tidak valid.")

    frm = game.selected
    pending_moves.pop(cid, None)
    color = game.board[frm][0] if game.board[frm] else "?"
    is_jump = num in game._jump_moves(frm)
    game.move(frm, num)

    # Log ke db
    move_counter[cid] = move_counter.get(cid, 0) + 1
    await log_move(game_db_id.get(cid, 0), move_counter[cid], color, frm, num, game.board)

    # Setelah lompat, cek apakah bisa lompat lagi (chain jump)
    if is_jump and not game.is_over():
        next_jumps = game._jump_moves(num)
        if next_jumps:
            # Kembalikan giliran ke pemain yang sama untuk chain jump
            game.turn = WHITE if color == WHITE else BLACK
            game.selected = num
            pending_moves[cid] = next_jumps
            await send_board(bot, cid, game,
                f"<blockquote>🔄 Lompat lagi! Bidak <b>{num}</b> bisa lanjut.\nPilih tujuan atau ketik <b>0</b> untuk stop:</blockquote>",
                sources=[num], targets=next_jumps,
                reply_markup=kb_slots(next_jumps, "dest", ButtonStyle.SECONDARY))
            return

    if game.is_over():
        wname = game.winner_name()
        await log_game_end(game_db_id.get(cid, 0), wname)
        await send_board(bot, cid, game, f"<blockquote>🏆 <b>{wname} menang!</b></blockquote>")
        games.pop(cid, None); board_msg_id.pop(cid, None)
        game_db_id.pop(cid, None); move_counter.pop(cid, None)
        pending_moves.pop(cid, None)
    else:
        sources = game.all_valid_sources()
        if not sources:
            game.turn = BLACK if game.turn == WHITE else WHITE
            sources = game.all_valid_sources()
            await send_board(bot, cid, game,
                f"<blockquote>⏭ Tidak ada gerakan tersedia, giliran dilewati.</blockquote>\n" + turn_caption(game),
                reply_markup=kb_slots(sources, "pick", ButtonStyle.PRIMARY))
        else:
            await send_board(bot, cid, game, turn_caption(game),
                             reply_markup=kb_slots(sources, "pick", ButtonStyle.PRIMARY))



@router.callback_query(F.data.startswith("dest:"))
async def cb_dest(cq: CallbackQuery, bot: Bot):
    """Handle pilihan tujuan via inline button."""
    if not cq.from_user or not cq.message:
        return
    cid = cq.message.chat.id
    game = games.get(cid)
    if not game or game.is_over():
        return await cq.answer()
    if cq.from_user.id != game.current_player_id():
        return await cq.answer("Bukan giliranmu! ⏳", show_alert=True)
    moves = pending_moves.get(cid)
    if not moves or not game.selected:
        return await cq.answer()

    num = int(cq.data.split(":")[1])
    if num not in moves:
        return await cq.answer("Tujuan tidak valid.", show_alert=True)

    frm = game.selected
    pending_moves.pop(cid, None)
    color = game.board[frm][0] if game.board[frm] else "?"
    is_jump = num in game._jump_moves(frm)
    game.move(frm, num)

    move_counter[cid] = move_counter.get(cid, 0) + 1
    await log_move(game_db_id.get(cid, 0), move_counter[cid], color, frm, num, game.board)
    await cq.answer()

    if is_jump and not game.is_over():
        next_jumps = game._jump_moves(num)
        if next_jumps:
            game.turn = WHITE if color == WHITE else BLACK
            game.selected = num
            pending_moves[cid] = next_jumps
            await send_board(bot, cid, game,
                f"<blockquote>🔄 Lompat lagi! Bidak <b>{num}</b> bisa lanjut.\nPilih tujuan atau ketik <b>0</b> untuk stop:</blockquote>",
                sources=[num], targets=next_jumps,
                reply_markup=kb_slots(next_jumps, "dest", ButtonStyle.SECONDARY))
            return

    if game.is_over():
        wname = game.winner_name()
        await log_game_end(game_db_id.get(cid, 0), wname)
        await send_board(bot, cid, game, f"<blockquote>🏆 <b>{wname} menang!</b></blockquote>")
        games.pop(cid, None); board_msg_id.pop(cid, None)
        game_db_id.pop(cid, None); move_counter.pop(cid, None)
        pending_moves.pop(cid, None)
    else:
        sources = game.all_valid_sources()
        if not sources:
            game.turn = BLACK if game.turn == WHITE else WHITE
            sources = game.all_valid_sources()
            await send_board(bot, cid, game,
                f"<blockquote>⏭ Tidak ada gerakan tersedia, giliran dilewati.</blockquote>\n" + turn_caption(game),
                reply_markup=kb_slots(sources, "pick", ButtonStyle.PRIMARY))
        else:
            await send_board(bot, cid, game, turn_caption(game),
                             reply_markup=kb_slots(sources, "pick", ButtonStyle.PRIMARY))

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
    await send_board(bot, cid, game, f"<blockquote>🏆 <b>{wname} menang!</b></blockquote>")
    await log_game_end(game_db_id.get(cid, 0), wname)
    games.pop(cid, None); board_msg_id.pop(cid, None)
    game_db_id.pop(cid, None); move_counter.pop(cid, None)
    pending_moves.pop(cid, None)


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN wajib diisi di .env!")
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    init_db(bot)
    from aiogram.types import BotCommand
    await bot.set_my_commands([
        BotCommand(command="new", description="Buka tantangan baru"),
        BotCommand(command="join", description="Terima tantangan"),
        BotCommand(command="menyerah", description="Menyerah"),
        BotCommand(command="rules", description="Aturan permainan"),
        BotCommand(command="privasi", description="Kebijakan privasi"),
        BotCommand(command="help", description="Cara main"),
    ])
    dp  = Dispatcher()
    dp.include_router(router)
    log.info("Dam-daman bot started.")
    await dp.start_polling(bot, allowed_updates=["message", "callback_query"])

if __name__ == "__main__":
    asyncio.run(main())
