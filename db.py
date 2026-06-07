"""db.py — Log game ke JSON file, kirim file ke channel Telegram"""
import json
import os
from datetime import datetime

from aiogram.types import BufferedInputFile

LOG_CHANNEL = -1004290378505
DATA_DIR = os.path.join(os.path.dirname(__file__), "game_logs")
_bot = None


def init_db(bot=None):
    global _bot
    _bot = bot
    os.makedirs(DATA_DIR, exist_ok=True)


def _game_path(game_id: int) -> str:
    return os.path.join(DATA_DIR, f"{game_id}.json")


def _board_to_dict(board: dict) -> dict:
    return {str(k): list(v) if v else None for k, v in board.items()}


async def log_new_game(chat_id, p1_id, p1_name, p2_id, p2_name, p1_color, board) -> int:
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    game_id = int(datetime.now().timestamp() * 1000)
    data = {
        "game_id": game_id,
        "chat_id": chat_id,
        "started": datetime.now().isoformat(),
        "p1": {"id": p1_id, "name": p1_name, "color": "W"},
        "p2": {"id": p2_id, "name": p2_name, "color": "B"},
        "moves": [],
        "winner": None,
        "board_start": _board_to_dict(board),
    }
    with open(_game_path(game_id), "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return game_id


async def log_move(game_id, move_num, player, frm, dest, board):
    path = _game_path(game_id)
    if not os.path.exists(path):
        return
    with open(path) as f:
        data = json.load(f)
    data["moves"].append({
        "n": move_num,
        "player": player,
        "from": frm,
        "to": dest,
        "board": _board_to_dict(board),
    })
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


async def log_game_end(game_id, winner):
    path = _game_path(game_id)
    if not os.path.exists(path):
        return
    with open(path) as f:
        data = json.load(f)
    data["winner"] = winner
    data["ended"] = datetime.now().isoformat()
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # Kirim file JSON ke log channel
    if _bot:
        try:
            content = json.dumps(data, ensure_ascii=False, indent=2).encode()
            doc = BufferedInputFile(content, filename=f"game_{game_id}.json")
            caption = f"🏆 <b>{winner}</b> menang\n🏠 <code>#rm{data['chat_id']}</code>"
            await _bot.send_document(LOG_CHANNEL, document=doc, caption=caption, parse_mode="HTML")
        except Exception:
            pass
