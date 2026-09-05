import os, time, threading
import telebot
from flask import Flask
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = os.getenv('BOT_TOKEN')
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
app = Flask(__name__)

# --- YOUR QUIZ DATA ---
QUESTION = "SI on 15k for 2yr @10% is 3000. What is CI?"
OPTIONS = ["₹3150", "₹3300", "₹3000", "₹3200"]
CORRECT = 0

start_times = {}
active_timers = {}
timer_msg = {}

def get_quiz_card():
    return (
        "📚 **VIDYASHALA DAILY QUIZ**\n\n"
        "🧠 Topic: Simple vs Compound Interest\n"
        "⏱️ Can you solve in under 3 sec?\n"
        "🏆 Fastest time gets on leaderboard\n\n"
        "👇 Tap below to get quiz in your DM"
    )

def live_timer_updater(uid):
    while active_timers.get(uid, False):
        try:
            elapsed = time.time() - start_times[uid]
            chat_id, msg_id = timer_msg[uid]
            markup = InlineKeyboardMarkup()
            for i, opt in enumerate(OPTIONS):
                markup.add(InlineKeyboardButton(opt, callback_data=f"ans_{i}"))
            bot.edit_message_text(f"⏱️ LIVE: {elapsed:.1f}s\n\n{QUESTION}", chat_id, msg_id, reply_markup=markup)
        except:
            pass
        time.sleep(0.7)

# STEP 1: Admin types /quiz -> Card goes to Channel
@bot.message_handler(commands=['quiz'])
def send_quiz_card(message):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📝 Take Quiz in DM", callback_data="take_quiz"))
    bot.send_message("@vidyashalatest", get_quiz_card(), reply_markup=markup, parse_mode="Markdown")

# STEP 2 & 3: Handle all button taps
@bot.callback_query_handler(func=lambda c: True)
def handle_all(call):
    uid = call.from_user.id
    bot_username = bot.get_me().username

    # A) User tapped "Take Quiz" in CHANNEL
    if call.data == "take_quiz":
        try:
            # Send BLURRED quiz to their DM
            markup = InlineKeyboardMarkup().add(InlineKeyboardButton("👁️ Tap to Reveal + Start Timer", callback_data="reveal"))
            bot.send_message(uid, f"🔒 **BLURRED QUIZ**\n\n{QUESTION}\n\n👁️ Tap below to reveal and start LIVE timer", reply_markup=markup, parse_mode="Markdown")
            bot.answer_callback_query(call.id, "✅ Quiz sent to your DM! Check private chat")
        except:
            # User never started bot - ask to start
            markup = InlineKeyboardMarkup().add(InlineKeyboardButton("🚀 Start Bot First", url=f"https://t.me/{bot_username}?start=quiz"))
            bot.answer_callback_query(call.id, "Please START the bot first!", show_alert=True)
            bot.send_message(call.message.chat.id, f"⚠️ @{call.from_user.username} please start @{bot_username} in DM first, then tap Take Quiz again.", reply_markup=markup)

    # B) User tapped "Reveal" in DM -> START LIVE TIMER
    elif call.data == "reveal":
        start_times[uid] = time.time()
        active_timers[uid] = True
        timer_msg[uid] = (call.message.chat.id, call.message.message_id)

        markup = InlineKeyboardMarkup()
        for i, opt in enumerate(OPTIONS):
            markup.add(InlineKeyboardButton(opt, callback_data=f"ans_{i}"))

        bot.edit_message_text(f"⏱️ LIVE: 0.0s\n\n{QUESTION}", call.message.chat.id, call.message.message_id, reply_markup=markup)
        threading.Thread(target=live_timer_updater, args=(uid,), daemon=True).start()

    # C) User answered
    elif call.data.startswith("ans_"):
        active_timers[uid] = False
        elapsed = time.time() - start_times.get(uid, time.time())
        ans = int(call.data.split("_")[1])
        is_correct = ans == CORRECT
        result = "✅ Correct! Super Fast!" if is_correct else f"❌ Wrong! Correct is {OPTIONS[CORRECT]}"

        try:
            bot.edit_message_text(f"{result}\n⏱️ Your Time: {elapsed:.2f}s\n\n{QUESTION}\n\nWant another? Go to @vidyashalatest", call.message.chat.id, call.message.message_id)
        except:
            pass
        bot.answer_callback_query(call.id, f"⏱️ Time: {elapsed:.2f}s")

@app.route('/')
def home():
    return "Vidyashala Bot Running - OK"

def run_bot():
    while True:
        try:
            bot.delete_webhook(drop_pending_updates=True)
            time.sleep(2)
            bot.infinity_polling(timeout=10, long_polling_timeout=10, skip_pending=True)
        except Exception as e:
            print(f"Retry: {e}")
            time.sleep(10)

threading.Thread(target=run_bot, daemon=True).start()
