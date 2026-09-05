import os, time, csv, threading
import telebot
from flask import Flask
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = os.environ['BOT_TOKEN']
bot = telebot.TeleBot(BOT_TOKEN)
start_times = {}
app = Flask(__name__)

QUESTION = "SI on 15k for 2yr @10% is 3000. CI is?"
OPTIONS = ["3150", "3300", "3000", "3200"]
CORRECT = 0

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
        with open("times.csv", "a", newline="") as f:
            csv.writer(f).writerow([uid, call.from_user.username, f"{elapsed:.2f}", is_correct])
        result = "✅ Correct!" if is_correct else f"❌ Wrong! Ans: {OPTIONS[CORRECT]}"
        bot.edit_message_text(f"{result}\n⏱️ Your Time: {elapsed:.2f}s", call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id, f"Time: {elapsed:.2f}s")

@app.route('/')
def home():
    return "Vidyashala Bot Running"

def run_bot():
    bot.infinity_polling()

if __name__ == "__main__":
    threading.Thread(target=run_bot).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
