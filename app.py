import os, time, threading
import telebot
from flask import Flask
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = os.getenv('BOT_TOKEN')
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
app = Flask(__name__)

# --- 5 QUESTIONS x 5 OPTIONS (Edit here for new quiz) ---
QUIZ = [
    {"q": "Q1: SI on 15k for 2yr @10% is 3000. What is CI?", "opts": ["₹3150", "₹3300", "₹3225", "₹3000", "₹3100"], "ans": 0},
    {"q": "Q2: 25 x 25 =?", "opts": ["500", "625", "600", "650", "525"], "ans": 1},
    {"q": "Q3: Speed 60km/h for 2.5hr =?", "opts": ["120km", "150km", "180km", "100km", "200km"], "ans": 1},
    {"q": "Q4: If CP=100, Profit 20%, SP=?", "opts": ["110", "120", "130", "100", "115"], "ans": 1},
    {"q": "Q5: √144 + √64 =?", "opts": ["18", "20", "16", "22", "19"], "ans": 1},
]

sessions = {} # uid -> {cur, answers[], times[], start, msg_id}
best_times = {} # q_idx -> (best_time, username)
active_timers = {}
timer_msg = {}

def live_updater(uid):
    while active_timers.get(uid, False):
        try:
            cur = sessions[uid]['cur']
            elapsed = time.time() - sessions[uid]['start']
            chat_id, msg_id = timer_msg[uid]
            qdata = QUIZ[cur]
            markup = InlineKeyboardMarkup()
            for i, opt in enumerate(qdata['opts']):
                markup.add(InlineKeyboardButton(f"{chr(65+i)}. {opt}", callback_data=f"ans_{cur}_{i}"))
            bot.edit_message_text(f"Q{cur+1}/5 ⏱️ LIVE: {elapsed:.1f}s\n\n{qdata['q']}", chat_id, msg_id, reply_markup=markup)
        except:
            pass
        time.sleep(0.7)

def send_question(uid, q_idx):
    sessions[uid]['cur'] = q_idx
    sessions[uid]['start'] = time.time()
    active_timers[uid] = True
    qdata = QUIZ[q_idx]
    markup = InlineKeyboardMarkup()
    for i, opt in enumerate(qdata['opts']):
        markup.add(InlineKeyboardButton(f"{chr(65+i)}. {opt}", callback_data=f"ans_{q_idx}_{i}"))
    msg = bot.send_message(uid, f"Q{q_idx+1}/5 ⏱️ LIVE: 0.0s\n\n{qdata['q']}", reply_markup=markup)
    timer_msg[uid] = (uid, msg.message_id)
    threading.Thread(target=live_updater, args=(uid,), daemon=True).start()

def build_scorecard(uid):
    sess = sessions[uid]
    total_correct = sum(1 for i, a in enumerate(sess['answers']) if a == QUIZ[i]['ans'])
    text = f"📊 **VIDYASHALA SCORECARD**\n👤 @{bot.get_me().username}\n✅ Score: {total_correct}/5\n\n"
    for i in range(5):
        qdata = QUIZ[i]
        user_ans = sess['answers'][i]
        user_time = sess['times'][i]
        best = best_times.get(i, (None, None))
        best_time_str = f"{best[0]:.2f}s by @{best[1]}" if best[0] else "You are Topper!"
        is_correct = user_ans == qdata['ans']

        text += f"\n**Q{i+1}: {qdata['q']}**\n"
        for j, opt in enumerate(qdata['opts']):
            mark = ""
            if j == qdata['ans']:
                mark += " ✅ Correct"
            if j == user_ans:
                mark += " 👉 Your Choice"
            text += f"{chr(65+j)}. {opt}{mark}\n"
        text += f"⏱️ Your Time: {user_time:.2f}s | 🏆 Topper: {best_time_str}\n"
        text += f"{'✅' if is_correct else '❌'} {'Correct' if is_correct else 'Wrong'}\n"
        text += "—\n"
    return text

@bot.message_handler(commands=['start'])
def handle_start(message):
    uid = message.from_user.id
    if "quiz" in message.text:
        sessions[uid] = {'cur': 0, 'answers': [], 'times': [], 'start': 0}
        send_question(uid, 0)
    else:
        bot.send_message(uid, "Welcome! Go to @vidyashalatest and tap Take Quiz")

@bot.message_handler(commands=['quiz'])
def post_card(message):
    try:
        username = bot.get_me().username
    except:
        username = "YOURBOT"
    markup = InlineKeyboardMarkup().add(InlineKeyboardButton("📝 Take 5-Q Quiz in DM", url=f"https://t.me/{username}?start=quiz"))
    bot.send_message("@vidyashalatest", f"📚 **NEW 5-QUESTION QUIZ LIVE!**\n⏱️ Live timer per question\n🏆 Scorecard with Topper comparison at end\n\n👇 Tap to start in DM", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: True)
def handle_ans(call):
    uid = call.from_user.id
    if not call.data.startswith("ans_"):
        return
    _, q_idx, opt_idx = call.data.split("_")
    q_idx, opt_idx = int(q_idx), int(opt_idx)

    if uid not in sessions or sessions[uid]['cur']!= q_idx:
        bot.answer_callback_query(call.id, "Old question, ignore")
        return

    active_timers[uid] = False
    elapsed = time.time() - sessions[uid]['start']
    sessions[uid]['answers'].append(opt_idx)
    sessions[uid]['times'].append(elapsed)

    # Update topper time (only if correct)
    if opt_idx == QUIZ[q_idx]['ans']:
        cur_best = best_times.get(q_idx)
        if not
