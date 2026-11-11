import asyncio
import uuid
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# ---------- تنظیمات ----------
# توکن رو اینجا بذار (به جای TOKEN_RO_HATMAN_BEZAR)
BOT_TOKEN = "9183201024:AAGD2YnKQBz4CbDnbKI1yjDqbn8n-ITsi6Q"

# ---------- وضعیت‌ها ----------
waiting_queue = []          # لیست user_id های منتظر حریف
user_to_game = {}           # user_id -> game_id
games = {}                  # game_id -> dict اطلاعات بازی
game_lock = asyncio.Lock()  # برای جلوگیری از race condition

# ---------- لاگ ----------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ---------- ساخت صفحه ----------
def make_board(board):
    keyboard = []
    for row in range(3):
        line = []
        for col in range(3):
            i = row * 3 + col
            text = board[i] if board[i] != " " else "⬜"
            line.append(InlineKeyboardButton(text, callback_data=f"move_{i}"))
        keyboard.append(line)
    return InlineKeyboardMarkup(keyboard)


# ---------- بررسی برنده ----------
def check_winner(board):
    wins = [
        (0, 1, 2), (3, 4, 5), (6, 7, 8),
        (0, 3, 6), (1, 4, 7), (2, 5, 8),
        (0, 4, 8), (2, 4, 6),
    ]
    for a, b, c in wins:
        if board[a] != " " and board[a] == board[b] == board[c]:
            return board[a]
    return None


# ---------- دستور /start ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "سلام! 👋\n"
        "برای شروع بازی دوز بزن /play\n"
        "برای خروج از صف یا بازی بزن /cancel"
    )


# ---------- دستور /play ----------
async def play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    async with game_lock:
        if user_id in user_to_game:
            await update.message.reply_text("شما الان توی یک بازی هستید!")
            return

        if user_id in waiting_queue:
            await update.message.reply_text("شما الان توی صف انتظار هستید ⏳")
            return

        # اگه کسی تو صف هست، باهاش بازی شروع کن
        if waiting_queue:
            opponent_id = waiting_queue.pop(0)
            game_id = str(uuid.uuid4())

            games[game_id] = {
                "player1": opponent_id,
                "player2": user_id,
                "board": [" "] * 9,
                "turn": opponent_id,   # نفر اول صف شروع می‌کنه
                "messages": {},        # user_id -> message_id
            }
            user_to_game[opponent_id] = game_id
            user_to_game[user_id] = game_id

            board_markup = make_board(games[game_id]["board"])

            # ارسال پیام برای هر دو بازیکن
            for pid in (opponent_id, user_id):
                try:
                    msg = await context.bot.send_message(
                        chat_id=pid,
                        text="🎮 بازی شروع شد!\nنوبت: نفر اول (❌)",
                        reply_markup=board_markup,
                    )
                    games[game_id]["messages"][pid] = msg.message_id
                except Exception as e:
                    logger.error(f"خطا در ارسال پیام به {pid}: {e}")

        else:
            waiting_queue.append(user_id)
            await update.message.reply_text(
                "⏳ منتظر حریف بمون...\n"
                "وقتی نفر دوم بیاد، بازی خودکار شروع می‌شه."
            )


# ---------- هندل کلیک روی دکمه‌ها ----------
async def handle_move(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id

    async with game_lock:
        if user_id not in user_to_game:
            await query.answer("شما توی بازی نیستید!", show_alert=True)
            return

        game_id = user_to_game[user_id]
        game = games.get(game_id)

        if not game:
            await query.answer("بازی پیدا نشد!", show_alert=True)
            return

        if game["turn"] != user_id:
            await query.answer("نوبت شما نیست!", show_alert=True)
            return

        index = int(query.data.split("_")[1])
        if game["board"][index] != " ":
            await query.answer("این خونه پره!", show_alert=True)
            return

        await query.answer()

        symbol = "❌" if user_id == game["player1"] else "⭕"
        game["board"][index] = symbol

        winner = check_winner(game["board"])

        # ---------- برد ----------
        if winner:
            for pid, mid in game["messages"].items():
                try:
                    await context.bot.edit_message_text(
                        chat_id=pid,
                        message_id=mid,
                        text=f"🎉 برنده: {winner}\nبازی تموم شد!",
                        reply_markup=None,
                    )
                except Exception:
                    pass
            cleanup_game(game_id)
            return

        # ---------- مساوی ----------
        if " " not in game["board"]:
            for pid, mid in game["messages"].items():
                try:
                    await context.bot.edit_message_text(
                        chat_id=pid,
                        message_id=mid,
                        text="🤝 مساوی شد!",
                        reply_markup=None,
                    )
                except Exception:
                    pass
            cleanup_game(game_id)
            return

        # ---------- ادامه بازی ----------
        game["turn"] = (
            game["player2"] if user_id == game["player1"] else game["player1"]
        )
        next_player = game["turn"]
        next_symbol = "❌" if next_player == game["player1"] else "⭕"

        board_markup = make_board(game["board"])
        for pid, mid in game["messages"].items():
            try:
                await context.bot.edit_message_reply_markup(
                    chat_id=pid,
                    message_id=mid,
                    reply_markup=board_markup,
                )
            except Exception:
                pass

        # اطلاع نوبت به هر دو
        for pid in game["messages"]:
            try:
                await context.bot.send_message(
                    chat_id=pid,
                    text=f"نوبت: {'شما' if pid == next_player else 'حریف'} ({next_symbol})",
                )
            except Exception:
                pass


# ---------- پاکسازی بازی ----------
def cleanup_game(game_id):
    game = games.pop(game_id, None)
    if not game:
        return
    user_to_game.pop(game["player1"], None)
    user_to_game.pop(game["player2"], None)


# ---------- دستور /cancel ----------
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    async with game_lock:
        if user_id in waiting_queue:
            waiting_queue.remove(user_id)
            await update.message.reply_text("از صف خارج شدی ✅")
            return

        if user_id in user_to_game:
            game_id = user_to_game[user_id]
            game = games.get(game_id)
            cleanup_game(game_id)
            if game:
                opponent = (
                    game["player2"]
                    if user_id == game["player1"]
                    else game["player1"]
                )
                try:
                    await context.bot.send_message(
                        chat_id=opponent,
                        text="حریفت از بازی خارج شد! 😔",
                    )
                except Exception:
                    pass
            await update.message.reply_text("از بازی خارج شدی ✅")
            return

        await update.message.reply_text("شما توی هیچ صف یا بازی‌ای نیستید.")


# ---------- main ----------
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("play", play))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CallbackQueryHandler(handle_move, pattern=r"^move_\d$"))

    logger.info("ربات روشن شد...")
    app.run_polling()


if __name__ == "__main__":
    main()
