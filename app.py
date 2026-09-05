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

@bot.message_handler(commands=['quiz'])
def send_hidden_quiz(message):
    markup = InlineKeyboardMarkup().add(InlineKeyboardButton("👁️ Tap to Reveal + Start Timer", callback_data="reveal"))
    bot.send_message("@vidyashalatest", f"🔒 HIDDEN QUIZ\n{QUESTION}\n\nTap below to reveal and start timer", reply_markup=markup)

@bot.callback_query_handler(func=lambda c: True)
def handle_click(call):
    uid = call.from_user.id
    if call.data == "reveal":
        start_times[uid] = time.time()
        markup = InlineKeyboardMarkup()
        for i, opt in enumerate(OPTIONS):
            markup.add(InlineKeyboardButton(opt, callback_data=f"ans_{i}"))
        bot.edit_message_text(f"⏱️ Timer Running...\n{QUESTION}", call.message.chat.id, call.message.message_id, reply_markup=markup)
    elif call.data.startswith("ans_"):
        elapsed = time.time() - start_times.get(uid, time.time())
        ans = int(call.data.split("_")[1])
        is_correct = ans == CORRECT
        result = "✅ Correct!" if is_correct else f"❌ Wrong! Ans: {OPTIONS[CORRECT]}"
        bot.edit_message_text(f"{result}\n⏱️ Your Time: {elapsed:.2f}s", call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id, f"Time: {elapsed:.2f}s")

@app.route('/')
def home():
    return "Vidyashala Bot Running - OK"

def run_bot():
    while True:
        try:
            print("Deleting old webhook...")
            bot.delete_webhook(drop_pending_updates=True)
            bot.remove_webhook()
            time.sleep(3)
            print("Starting polling - single instance")
            bot.infinity_polling(timeout=10, long_polling_timeout=10, skip_pending=True)
        except Exception as e:
            print(f"Polling conflict, retrying in 10 sec: {e}")
            time.sleep(10)

threading.Thread(target=run_bot, daemon=True).start()
