import os, time, threading
import telebot
from flask import Flask
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = os.getenv('BOT_TOKEN')
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
app = Flask(__name__)

QUESTION = "SI on 15k for 2yr @10% is 3000. What is CI?"
OPTIONS = ["₹3150", "₹3300", "₹3000", "₹3200"]
CORRECT = 0

start_times = {}
active_timers = {}
timer_msg = {}

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

# When user opens bot via channel link, auto-send blurred quiz
@bot.message_handler(commands=['start'])
def handle_start(message):
    if "quiz" in message.text:
        markup = InlineKeyboardMarkup().add(InlineKeyboardButton("👁️ Tap to Reveal + Start Timer", callback_data="reveal"))
        bot.send_message(message.chat.id, f"🔒 **BLURRED QUIZ RECEIVED**\n\n{QUESTION}\n\n👁️ Tap below to reveal and start LIVE timer", reply_markup=markup, parse_mode="Markdown")
    else:
        bot.send_message(message.chat.id, "Welcome to Vidyashala! Go to @vidyashalatest and tap Take Quiz")

# Admin command to post card in channel
@bot.message_handler(commands=['quiz'])
def send_quiz_card(message):
    try:
        bot_username = bot.get_me().username
    except:
        bot_username = "YOURBOT" # will auto fetch

    # URL button - FORCES DM and 100% works
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("📝 Take Quiz in DM - Click Here", url=f"https://t.me/{bot_username}?start=quiz"))

    bot.send_message("@vidyashalatest",
        f"📚 **VIDYASHALA DAILY QUIZ**\n\n🧠 Topic: Simple vs Compound Interest\n⏱️ Beat 3 sec?\n🏆 Fastest on Leaderboard\n\n👇 Tap to get quiz in YOUR DM",
        reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: True)
def handle_all(call):
    uid = call.from_user.id
    if call.data == "reveal":
        start_times[uid] = time.time()
        active_timers[uid] = True
        timer_msg[uid] = (call.message.chat.id, call.message.message_id)

        markup = InlineKeyboardMarkup()
        for i, opt in enumerate(OPTIONS):
            markup.add(InlineKeyboardButton(opt, callback_data=f"ans_{i}"))

        bot.edit_message_text(f"⏱️ LIVE: 0.0s\n\n{QUESTION}", call.message.chat.id, call.message.message_id, reply_markup=markup)
        threading.Thread(target=live_timer_updater, args=(uid,), daemon=True).start()

    elif call.data.startswith("ans_"):
        active_timers[uid] = False
        elapsed = time.time() - start_times.get(uid, time.time())
        ans = int(call.data.split("_")[1])
        is_correct = ans == CORRECT
        result = "✅ Correct!" if is_correct else f"❌ Wrong! Ans: {OPTIONS[CORRECT]}"
        bot.edit_message_text(f"{result}\n⏱️ Final Time: {elapsed:.2f}s\n\n{QUESTION}", call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id, f"Time: {elapsed:.2f}s")

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
