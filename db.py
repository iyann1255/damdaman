"""db.py — Log game ke channel Telegram"""
import json
from datetime import datetime

LOG_CHANNEL = -1004290378505
_bot = None


def init_db(bot=None):
    global _bot
    _bot = bot


async def log_new_game(chat_id, p1_id, p1_name, p2_id, p2_name, p1_color, board) -> int:
    if not _bot:
        return 0
    try:
        text = (
            f"🎮 <b>Game Baru</b>\n"
            f"🏠 <code>#rm{chat_id}</code>\n"
            f"⬜ {p1_name} (<code>{p1_id}</code>)\n"
            f"⬛ {p2_name} (<code>{p2_id}</code>)\n"
            f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        msg = await _bot.send_message(LOG_CHANNEL, text, parse_mode="HTML")
        return msg.message_id
    except Exception:
        return 0


async def log_move(game_id, move_num, player, frm, dest, board):
    if not _bot:
        return
    try:
        text = (
            f"♟ Move #{move_num} (game msg {game_id})\n"
            f"{player}: {frm} → {dest}"
        )
        await _bot.send_message(LOG_CHANNEL, text)
    except Exception:
        pass


async def log_game_end(game_id, winner):
    if not _bot:
        return
    try:
        text = f"🏆 Game selesai (msg {game_id})\nPemenang: <b>{winner}</b>"
        await _bot.send_message(LOG_CHANNEL, text, parse_mode="HTML")
    except Exception:
        pass
