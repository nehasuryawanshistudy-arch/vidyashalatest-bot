import os, time, threading
import telebot
from flask import Flask
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = os.getenv('BOT_TOKEN')
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
app = Flask(__name__)

QUIZ = [
    {"q": "SI on 15k for 2yr @10% is 3000. What is CI?", "opts": ["₹3150", "₹3300", "₹3225", "₹3000", "₹3100"], "ans": 0},
    {"q": "25 x 25 =?", "opts": ["500", "625", "600", "650", "525"], "ans": 1},
    {"q": "Speed 60km/h for 2.5hr =?", "opts": ["120km", "150km", "180km", "100km", "200km"], "ans": 1},
    {"q": "If CP=100, Profit 20%, SP =?", "opts": ["110", "120", "130", "100", "115"], "ans": 1},
    {"q": "√144 + √64 =?", "opts": ["18", "20", "16", "22", "19"], "ans": 1},
]

sessions, best_times, active_timers, timer_msg = {}, {}, {}, {}
LOGO_FILE_ID = None

# Load saved logo id if exists
if os.path.exists("logo_id.txt"):
    try:
        with open("logo_id.txt","r") as f:
            LOGO_FILE_ID = f.read().strip()
    except: pass

def get_q_text(q_idx, elapsed):
    q = QUIZ[q_idx]
    return (
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📝 QUESTION {q_idx+1} / 5 ⏱️ {elapsed:.1f}s\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"```\n{q['q']}\n```\n\n" # White box + black text + bigger look
    )

def live_updater(uid):
    while active_timers.get(uid):
        try:
            cur = sessions[uid]['cur']
            elapsed = time.time() - sessions[uid]['start']
            chat_id, msg_id = timer_msg.get(uid, (None,None))
            qdata = QUIZ[cur]
            markup = InlineKeyboardMarkup(row_width=1)
            for i, opt in enumerate(qdata['opts']):
                markup.add(InlineKeyboardButton(f"{chr(65+i)} : {opt}", callback_data=f"ans_{cur}_{i}"))
            bot.edit_message_text(get_q_text(cur, elapsed), chat_id, msg_id, reply_markup=markup, parse_mode="Markdown")
        except: pass
        time.sleep(0.8)

def send_question(uid, q_idx):
    sessions[uid]['cur']=q_idx
    sessions[uid]['start']=time.time()
    active_timers[uid]=True
    qdata=QUIZ[q_idx]
    markup=InlineKeyboardMarkup(row_width=1
