import os, time, threading
import telebot
from flask import Flask
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = os.getenv('BOT_TOKEN')
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
app = Flask(__name__)

QUESTION = "SI on 15k for 2yr @10% is 3000. CI is?"
OPTIONS = ["3150", "3300", "3000", "3200"]
CORRECT = 0

start_times = {}
active_timers = {} # uid -> True/False
timer_msg = {} # uid -> (chat_id, msg_id)

@bot.message_handler(commands=['quiz'])
def send_hidden_quiz(message):
    markup = InlineKeyboardMarkup().add(InlineKeyboardButton("👁️ Tap to Reveal + Start Timer", callback_data="reveal"))
    bot.send_message("@vidyashalatest", f"🔒 HIDDEN QUIZ\n{QUESTION}\n\nTap to reveal and timer starts", reply_markup=markup)

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
        time.sleep(0.8)

@bot.callback_query_handler(func=lambda c: True)
def handle_click(call):
    uid = call.from_user.id
    if call.data == "reveal":
        start_times[uid] = time.time()
        active_timers[uid] = True

        # Send personal live timer message to user (DM)
        try:
            markup = InlineKeyboardMarkup()
            for i, opt in enumerate(OPTIONS):
                markup.add(InlineKeyboardButton(opt, callback_data=f"ans_{i}"))

            sent = bot.send_message(uid, f"⏱️ LIVE: 0.0s\n\n{QUESTION}\n\nTimer running...", reply_markup=markup)
            timer_msg[uid] = (uid, sent.message_id)

            # Start live updating thread
            threading.Thread(target=live_timer_updater, args=(uid,), daemon=True).start()

            bot.answer_callback_query(call.id, "Timer started! Check DM")
            # Also update channel message for that user
            bot.edit_message_text(f"✅ Timer started for @{call.from_user.username} - Check DM for live timer\n{QUESTION}", call.message.chat.id, call.message.message_id)

        except:
            # If user never started bot, fallback to channel live timer
            markup = InlineKeyboardMarkup()
            for i, opt in enumerate(OPTIONS):
                markup.add(InlineKeyboardButton(opt, callback_data=f"ans_{i}"))
            bot.edit_message_text(f"⏱️ LIVE: 0.0s\n{QUESTION}", call.message.chat.id, call.message.message_id, reply_markup=markup)
            timer_msg[uid] = (call.message.chat.id, call.message.message_id)
            threading.Thread(target=live_timer_updater, args=(uid,), daemon=True).start()

    elif call.data.startswith("ans_"):
        active_timers[uid] = False
        elapsed = time.time() - start_times.get(uid, time.time())
        ans = int(call.data.split("_")[1])
        is_correct = ans == CORRECT
        result = "✅ Correct!" if is_correct else f"❌ Wrong! Correct: {OPTIONS[CORRECT]}"

        try:
            chat_id, msg_id = timer_msg.get(uid, (call.message.chat.id, call.message.message_id))
            bot.edit_message_text(f"{result}\n⏱️ Final Time: {elapsed:.2f}s\n\n{QUESTION}", chat_id, msg_id)
        except:
            pass
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
