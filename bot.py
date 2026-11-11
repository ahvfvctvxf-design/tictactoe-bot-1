import asyncio
import uuid
import logging
import sqlite3
import random
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ---------- تنظیمات ----------
BOT_TOKEN = "9183201024:AAGD2YnKQBz4CbDnbKI1yjDqbn8n-ITsi6Q"  # توکن خودت رو اینجا بذار

# ---------- دیتابیس ----------
def init_db():
    conn = sqlite3.connect('scores.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS scores
                 (user_id INTEGER PRIMARY KEY, username TEXT, points INTEGER)''')
    conn.commit()
    conn.close()

def add_point(user_id, username, points=1):
    conn = sqlite3.connect('scores.db')
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO scores (user_id, username, points) VALUES (?, ?, 0)', (user_id, username))
    c.execute('UPDATE scores SET points = points + ?, username = ? WHERE user_id = ?', (points, username, user_id))
    conn.commit()
    conn.close()

def get_leaderboard():
    conn = sqlite3.connect('scores.db')
    c = conn.cursor()
    c.execute('SELECT username, points FROM scores ORDER BY points DESC LIMIT 10')
    rows = c.fetchall()
    conn.close()
    return rows

init_db()

# ---------- وضعیت‌ها ----------
waiting_queue_ttt = []
waiting_queue_rps = []
waiting_queue_hokm = []
user_to_game = {}  
games = {}         
game_lock = asyncio.Lock()

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------- توابع کمکی ----------
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

def check_winner(board):
    wins = [(0,1,2), (3,4,5), (6,7,8), (0,3,6), (1,4,7), (2,5,8), (0,4,8), (2,4,6)]
    for a, b, c in wins:
        if board[a] != " " and board[a] == board[b] == board[c]:
            return board[a]
    return None

def make_rps_keyboard():
    keyboard = [[
        InlineKeyboardButton("🪨 سنگ", callback_data="rps_rock"),
        InlineKeyboardButton("📄 کاغذ", callback_data="rps_paper"),
        InlineKeyboardButton("✂️ قیچی", callback_data="rps_scissors"),
    ]]
    return InlineKeyboardMarkup(keyboard)

# ---------- دستورات عمومی ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "سلام! 👋\n"
        "🎮 دوز: /play\n"
        "✂️ سنگ کاغذ قیچی: /rps\n"
        "🃏 حکم: /hokm\n"
        "🏆 جدول امتیازات: /leaderboard\n"
        "❌ خروج: /cancel"
    )

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = get_leaderboard()
    if not rows:
        await update.message.reply_text("هنوز کسی بازی نکرده!")
        return
    text = "🏆 **برترین‌ها:**\n\n"
    for i, (username, points) in enumerate(rows, 1):
        name = f"@{username}" if username else "ناشناس"
        text += f"{i}. {name} - {points} امتیاز\n"
    await update.message.reply_text(text, parse_mode='Markdown')

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    async with game_lock:
        if user_id in waiting_queue_ttt:
            waiting_queue_ttt.remove(user_id)
            await update.message.reply_text("از صف دوز خارج شدی ✅")
            return
        if user_id in waiting_queue_rps:
            waiting_queue_rps.remove(user_id)
            await update.message.reply_text("از صف سنگ کاغذ قیچی خارج شدی ✅")
            return
        if user_id in waiting_queue_hokm:
            waiting_queue_hokm.remove(user_id)
            await update.message.reply_text("از صف حکم خارج شدی ✅")
            return
        
        if user_id in user_to_game:
            game_info = user_to_game[user_id]
            game_id = game_info["game_id"]
            opponent_id = game_info["opponent_id"]
            
            if game_id in games: del games[game_id]
            if opponent_id in user_to_game: del user_to_game[opponent_id]
            del user_to_game[user_id]
            
            try:
                await context.bot.send_message(chat_id=opponent_id, text="حریفت از بازی خارج شد! 😔")
            except: pass
            await update.message.reply_text("از بازی خارج شدی ✅")
            return
        await update.message.reply_text("شما توی هیچ صف یا بازی‌ای نیستید.")

# ---------- بازی دوز ----------
async def play_ttt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "بدون_نام"
    async with game_lock:
        if user_id in user_to_game or user_id in waiting_queue_rps or user_id in waiting_queue_hokm:
            await update.message.reply_text("شما الان توی یک بازی یا صف هستید!")
            return
        if user_id in waiting_queue_ttt:
            await update.message.reply_text("شما الان توی صف دوز هستید ⏳")
            return

        if waiting_queue_ttt:
            opponent_id, opponent_username = waiting_queue_ttt.pop(0)
            game_id = str(uuid.uuid4())
            games[game_id] = {"type": "ttt", "player1": opponent_id, "player2": user_id, "p1_name": opponent_username, "p2_name": username, "board": [" "] * 9, "turn": opponent_id, "messages": {}}
            user_to_game[opponent_id] = {"game_id": game_id, "type": "ttt", "opponent_id": user_id}
            user_to_game[user_id] = {"game_id": game_id, "type": "ttt", "opponent_id": opponent_id}

            board_markup = make_board(games[game_id]["board"])
            for pid in (opponent_id, user_id):
                msg = await context.bot.send_message(chat_id=pid, text="🎮 دوز شروع شد! نوبت نفر اول (❌)", reply_markup=board_markup)
                games[game_id]["messages"][pid] = msg.message_id
        else:
            waiting_queue_ttt.append((user_id, username))
            await update.message.reply_text("⏳ منتظر حریف برای دوز بمون...")

async def handle_ttt_move(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    async with game_lock:
        if user_id not in user_to_game or user_to_game[user_id]["type"] != "ttt": return
        game = games[user_to_game[user_id]["game_id"]]
        if game["turn"] != user_id:
            await query.answer("نوبت شما نیست!", show_alert=True); return
        index = int(query.data.split("_")[1])
        if game["board"][index] != " ":
            await query.answer("پره!", show_alert=True); return
        
        await query.answer()
        symbol = "❌" if user_id == game["player1"] else "⭕"
        game["board"][index] = symbol
        winner = check_winner(game["board"])

        if winner or " " not in game["board"]:
            if winner:
                winner_id = game["player1"] if symbol == "❌" else game["player2"]
                winner_name = game["p1_name"] if symbol == "❌" else game["p2_name"]
                add_point(winner_id, winner_name, 1)
                txt = f"🎉 برنده: {winner} (+۱ امتیاز)"
            else:
                txt = "🤝 مساوی شد!"
            for pid, mid in game["messages"].items():
                await context.bot.edit_message_text(chat_id=pid, message_id=mid, text=txt, reply_markup=None)
            p1, p2 = game["player1"], game["player2"]
            del games[user_to_game[p1]["game_id"]]; del user_to_game[p1]; del user_to_game[p2]
            return

        game["turn"] = game["player2"] if user_id == game["player1"] else game["player1"]
        board_markup = make_board(game["board"])
        for pid, mid in game["messages"].items():
            await context.bot.edit_message_reply_markup(chat_id=pid, message_id=mid, reply_markup=board_markup)

# ---------- سنگ کاغذ قیچی ----------
async def play_rps(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "بدون_نام"
    async with game_lock:
        if user_id in user_to_game or user_id in waiting_queue_ttt or user_id in waiting_queue_hokm:
            await update.message.reply_text("شما الان توی یک بازی یا صف هستید!"); return
        if user_id in waiting_queue_rps:
            await update.message.reply_text("توی صف هستید ⏳"); return

        if waiting_queue_rps:
            opponent_id, opponent_username = waiting_queue_rps.pop(0)
            game_id = str(uuid.uuid4())
            games[game_id] = {"type": "rps", "player1": opponent_id, "player2": user_id, "p1_name": opponent_username, "p2_name": username, "choices": {}}
            user_to_game[opponent_id] = {"game_id": game_id, "type": "rps", "opponent_id": user_id}
            user_to_game[user_id] = {"game_id": game_id, "type": "rps", "opponent_id": opponent_id}
            for pid in (opponent_id, user_id):
                await context.bot.send_message(chat_id=pid, text="🎮 سنگ کاغذ قیچی! انتخاب کن:", reply_markup=make_rps_keyboard())
        else:
            waiting_queue_rps.append((user_id, username))
            await update.message.reply_text("⏳ منتظر حریف برای سنگ کاغذ قیچی بمون...")

async def handle_rps_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    async with game_lock:
        if user_id not in user_to_game or user_to_game[user_id]["type"] != "rps": return
        game = games[user_to_game[user_id]["game_id"]]
        if user_id in game["choices"]:
            await query.answer("قبلاً انتخاب کردی!", show_alert=True); return
        
        await query.answer()
        game["choices"][user_id] = query.data.split("_")[1]
        await query.edit_message_text(text="✅ ثبت شد. منتظر حریف...", reply_markup=None)

        if len(game["choices"]) == 2:
            p1, p2 = game["player1"], game["player2"]
            c1, c2 = game["choices"][p1], game["choices"][p2]
            names = {"rock": "🪨", "paper": "📄", "scissors": "✂️"}
            
            if c1 == c2: result = "🤝 مساوی!"
            elif (c1=="rock" and c2=="scissors") or (c1=="paper" and c2=="rock") or (c1=="scissors" and c2=="paper"):
                result = "🎉 برنده: نفر اول (+۱)"
                add_point(p1, game["p1_name"], 1)
            else:
                result = "🎉 برنده: نفر دوم (+۱)"
                add_point(p2, game["p2_name"], 1)

            for pid in (p1, p2):
                await context.bot.send_message(chat_id=pid, text=f"{names[c1]} vs {names[c2]}\n\n{result}")
            
            g_id = user_to_game[p1]["game_id"]
            del games[g_id]; del user_to_game[p1]; del user_to_game[p2]

# ---------- بازی حکم (Hokm) ----------
SUITS = {"H": "♥️", "D": "♦️", "C": "♣️", "S": "♠️"}
RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
RANK_VALUES = {r: i for i, r in enumerate(RANKS)}

def create_deck():
    deck = [f"{r}{s}" for s in SUITS for r in RANKS]
    random.shuffle(deck)
    return deck

def card_str(card):
    return f"{card[:-1]}{SUITS[card[-1]]}"

def make_hokm_keyboard(hand, prefix="hokm_play"):
    keyboard = []
    for i in range(0, len(hand), 2):
        row = [InlineKeyboardButton(card_str(hand[i]), callback_data=f"{prefix}_{hand[i]}")]
        if i + 1 < len(hand):
            row.append(InlineKeyboardButton(card_str(hand[i+1]), callback_data=f"{prefix}_{hand[i+1]}"))
        keyboard.append(row)
    return InlineKeyboardMarkup(keyboard)

async def play_hokm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username or "بدون_نام"
    async with game_lock:
        if user_id in user_to_game or user_id in waiting_queue_ttt or user_id in waiting_queue_rps:
            await update.message.reply_text("شما الان توی یک بازی یا صف هستید!"); return
        if user_id in waiting_queue_hokm:
            await update.message.reply_text("توی صف حکم هستید ⏳"); return

        if waiting_queue_hokm:
            opponent_id, opponent_username = waiting_queue_hokm.pop(0)
            game_id = str(uuid.uuid4())
            
            deck = create_deck()
            p1_hand = deck[:13]
            p2_hand = deck[13:26]
            
            games[game_id] = {
                "type": "hokm", "player1": opponent_id, "player2": user_id,
                "p1_name": opponent_username, "p2_name": username,
                "p1_hand": p1_hand, "p2_hand": p2_hand,
                "turn": opponent_id, "hokm": None, 
                "table": [], "tricks_p1": 0, "tricks_p2": 0,
                "messages": {}
            }
            user_to_game[opponent_id] = {"game_id": game_id, "type": "hokm", "opponent_id": user_id}
            user_to_game[user_id] = {"game_id": game_id, "type": "hokm", "opponent_id": opponent_id}

            # نفر اول باید حکم رو انتخاب کنه
            await context.bot.send_message(
                chat_id=opponent_id, 
                text="🃏 بازی حکم شروع شد!\nشما نفر اول هستید. لطفاً **حکم** را انتخاب کنید:", 
                reply_markup=make_hokm_keyboard(list(SUITS.keys()), "hokm_suit")
            )
            await context.bot.send_message(
                chat_id=user_id, 
                text="🃏 بازی حکم شروع شد!\nمنتظر بمانید تا حریف حکم را انتخاب کند..."
            )
        else:
            waiting_queue_hokm.append((user_id, username))
            await update.message.reply_text("⏳ منتظر حریف برای بازی حکم بمون...")

async def handle_hokm_suit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    async with game_lock:
        if user_id not in user_to_game or user_to_game[user_id]["type"] != "hokm": return
        game = games[user_to_game[user_id]["game_id"]]
        
        suit = query.data.split("_")[1]
        game["hokm"] = suit
        await query.answer()
        await query.edit_message_text(text=f"✅ حکم: {SUITS[suit]} انتخاب شد. بازی شروع شد!")
        
        # فرستادن دست اولیه برای نفر اول (حاکم)
        await context.bot.send_message(
            chat_id=user_id,
            text=f"نوبت شماست. حکم: {SUITS[suit]}",
            reply_markup=make_hokm_keyboard(game["p1_hand"], "hokm_play")
        )
        # به نفر دوم بگو منتظر باشه
        await context.bot.send_message(
            chat_id=game["player2"],
            text=f"حریف حکم را {SUITS[suit]} کرد. منتظر بازی حریف باشید..."
        )

async def handle_hokm_play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    async with game_lock:
        if user_id not in user_to_game or user_to_game[user_id]["type"] != "hokm": return
        game = games[user_to_game[user_id]["game_id"]]
        
        if game["turn"] != user_id:
            await query.answer("نوبت شما نیست!", show_alert=True); return
            
        card = query.data.split("_")[1]
        is_p1 = (user_id == game["player1"])
        hand = game["p1_hand"] if is_p1 else game["p2_hand"]
        
        if card not in hand:
            await query.answer("این کارت رو نداری!", show_alert=True); return
            
        # چک کردن رعایت رنگ
        if game["table"]:
            lead_card = game["table"][0][1]
            lead_suit = lead_card[-1]
            if card[-1] != lead_suit and card[-1] != game["hokm"]:
                # اگه رنگ داشت، باید همون رنگ رو بازی می‌کرد
                if any(c[-1] == lead_suit for c in hand):
                    await query.answer(f"باید رنگ {SUITS[lead_suit]} بازی کنی!", show_alert=True); return

        await query.answer()
        
        # کارت رو از دستش کم کن
        hand.remove(card)
        game["table"].append((user_id, card))
        
        # آپدیت پیام‌ها
        await query.edit_message_text(text=f"✅ کارت {card_str(card)} بازی شد.")
        
        # اگه هر دو کارت رو بازی کردن
        if len(game["table"]) == 2:
            c1 = game["table"][0][1]
            c2 = game["table"][1][1]
            lead_suit = c1[-1]
            
            # تعیین برنده دست
            winner_id = None
            if c1[-1] == c2[-1]: # هم رنگ
                winner_id = game["table"][0][0] if RANK_VALUES[c1[:-1]] > RANK_VALUES[c2[:-1]] else game["table"][1][0]
            elif c2[-1] == game["hokm"]: # c2 حاکمه و c1 نبوده
                winner_id = game["table"][1][0]
            else: # c1 یا رنگ اصلی رو داشته یا حاکم بوده
                winner_id = game["table"][0][0]

            # امتیاز دست
            if winner_id == game["player1"]: game["tricks_p1"] += 1
            else: game["tricks_p2"] += 1
            
            game["table"] = []
            game["turn"] = winner_id
            
            # بررسی پایان بازی
            if game["tricks_p1"] >= 7 or game["tricks_p2"] >= 7:
                if game["tricks_p1"] >= 7:
                    winner_name = game["p1_name"]
                    add_point(game["player1"], winner_name, 2) # برنده حکم ۲ امتیاز
                    txt = f"🏆 بازی تموم شد! برنده: {winner_name} (نفر اول) (+۲ امتیاز)"
                else:
                    winner_name = game["p2_name"]
                    add_point(game["player2"], winner_name, 2)
                    txt = f"🏆 بازی تموم شد! برنده: {winner_name} (نفر دوم) (+۲ امتیاز)"
                
                for pid in (game["player1"], game["player2"]):
                    await context.bot.send_message(chat_id=pid, text=txt)
                g_id = user_to_game[game["player1"]]["game_id"]
                del games[g_id]; del user_to_game[game["player1"]]; del user_to_game[game["player2"]]
                return

            # دست بعدی
            next_p1_hand = game["p1_hand"]
            next_p2_hand = game["p2_hand"]
            
            # ارسال کارت‌های نفر بعدی
            next_hand = next_p1_hand if winner_id == game["player1"] else next_p2_hand
            await context.bot.send_message(
                chat_id=winner_id,
                text=f"دست رو بردی! نوبت شماست.\nامتیاز: {game['tricks_p1']} - {game['tricks_p2']}\nحکم: {SUITS[game['hokm']]}",
                reply_markup=make_hokm_keyboard(next_hand, "hokm_play")
            )
            await context.bot.send_message(
                chat_id=game["table"][0][0] if winner_id != game["table"][0][0] else game["table"][1][0], # بازنده
                text=f"حریف دست رو برد. منتظر بمانید..."
            )
        else:
            # نفر بعدی (حریف) باید بازی کنه
            next_player = game["player2"] if user_id == game["player1"] else game["player1"]
            next_hand = game["p2_hand"] if next_player == game["player2"] else game["p1_hand"]
            await context.bot.send_message(
                chat_id=next_player,
                text=f"حریف کارت {card_str(game['table'][0][1])} رو بازی کرد. نوبت شماست:",
                reply_markup=make_hokm_keyboard(next_hand, "hokm_play")
            )

# ---------- چت ناشناس ----------
async def handle_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    if user_id in user_to_game:
        opponent_id = user_to_game[user_id]["opponent_id"]
        try:
            await context.bot.send_message(chat_id=opponent_id, text=f"💬 **پیام از حریف:**\n{text}", parse_mode='Markdown')
            await update.message.reply_text("✅ پیام به حریف ارسال شد.")
        except: await update.message.reply_text("❌ نتونستم بفرستم.")
    else:
        await update.message.reply_text("برای بازی /start رو بزن.")

# ---------- main ----------
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("leaderboard", lea
