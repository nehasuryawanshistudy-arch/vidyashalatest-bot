import os, time, threading
import telebot
from flask import Flask
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = os.getenv('BOT_TOKEN')
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
app = Flask(__name__)

QUIZ = [
    {"q": "Q1: SI on 15k for 2yr @10% is 3000. What is CI?", "opts": ["₹3150", "₹3300", "₹3225", "₹3000", "₹3100"], "ans": 0},
    {"q": "Q2: 25 x 25 =?", "opts": ["500", "625", "600", "650", "525"], "ans": 1},
    {"q": "Q3: Speed 60km/h for 2.5hr =?", "opts": ["120km", "150km", "180km", "100km", "200km"], "ans": 1},
    {"q": "Q4: If CP=100, Profit 20%, SP=?", "opts": ["110", "120", "130", "100", "115"], "ans": 1},
    {"q": "Q5: √144 + √64 =?", "opts": ["18", "20", "16", "22", "19"], "ans": 1},
]

sessions = {}
best_times = {}
active_timers = {}
timer_msg = {}

def live_updater(uid):
    while active_timers.get(uid):
        try:
            sess = sessions.get(uid)
            if not sess: break
            cur = sess['cur']
            elapsed = time.time() - sess['start']
            chat_id, msg_id = timer_msg.get(uid, (None,None))
            if not chat_id: break
            qdata = QUIZ[cur]
            markup = InlineKeyboardMarkup()
            for i, opt in enumerate(qdata['opts']):
                markup.add(InlineKeyboardButton(f"{chr(65+i)}. {opt}", callback_data=f"ans_{cur}_{i}"))
            bot.edit_message_text(f"Q{cur+1}/5 ⏱️ LIVE: {elapsed:.1f}s\n\n{qdata['q']}", chat_id, msg_id, reply_markup=markup)
        except Exception as e:
            # print(f"timer err {e}")
            pass
        time.sleep(0.8)

def send_question(uid, q_idx):
    print(f"Sending Q{q_idx+1} to {uid}")
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

def send_next_delayed(uid, next_idx):
    time.sleep(1.2)
    if uid in sessions and next_idx < 5:
        send_question(uid, next_idx)
    elif next_idx >=5:
        # scorecard
        sess = sessions[uid]
        total = sum(1 for i, a in enumerate(sess['answers']) if a == QUIZ[i]['ans'])
        text = f"📊 **VIDYASHALA SCORECARD - {total}/5**\n\n"
        for i in range(5):
            qdata = QUIZ[i]
            u_ans = sess['answers'][i]
            u_time = sess['times'][i]
            best = best_times.get(i)
            best_str = f"{best[0]:.2f}s by @{best[1]}" if best else "YOU are Topper!"
            text += f"**Q{i+1}: {qdata['q']}**\n"
            for j, opt in enumerate(qdata['opts']):
                line = f"{chr(65+j)}. {opt}"
                if j == qdata['ans']: line += " ✅"
                if j == u_ans: line += " 👉 You"
                text += line + "\n"
            text += f"⏱️ You: {u_time:.2f}s | 🏆 Topper: {best_str}\n\n"
        bot.send_message(uid, text, parse_mode="Markdown")

@bot.message_handler(commands=['start'])
def handle_start(message):
    uid = message.from_user.id
    if "quiz" in message.text:
        sessions[uid] = {'cur':0, 'answers':[], 'times':[], 'start':0}
        send_question(uid, 0)
    else:
        bot.send_message(uid, "Welcome! Go to @vidyashalatest")

@bot.message_handler(commands=['quiz'])
def post_card(message):
    username = bot.get_me().username
    markup = InlineKeyboardMarkup().add(InlineKeyboardButton("📝 Take 5-Q Quiz in DM", url=f"https://t.me/{username}?start=quiz"))
    bot.send_message("@vidyashalatest", "📚 **NEW 5-Q QUIZ LIVE!**\n5 Questions, Live Timer, Final Scorecard with Topper Time\n👇 Tap to start", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: c.data.startswith("ans_"))
def handle_ans(call):
    uid = call.from_user.id
    _, q_idx, opt_idx = call.data.split("_")
    q_idx, opt_idx = int(q_idx), int(opt_idx)
    if uid not in sessions or sessions[uid]['cur']!= q_idx:
        return
    active_timers[uid] = False
    elapsed = time.time() - sessions[uid]['start']
    sessions[uid]['answers'].append(opt_idx)
    sessions[uid]['times'].append(elapsed)
    if opt_idx == QUIZ[q_idx]['ans']:
        cur_best = best_times.get(q_idx)
        if not cur_best or elapsed < cur_best[0]:
            best_times[q_idx] = (elapsed, call.from_user.username or call.from_user.first_name)

    qdata = QUIZ[q_idx]
    result = "✅ Correct!" if opt_idx == qdata['ans'] else f"❌ Wrong! Ans: {chr(65+qdata['ans'])}"
    try:
        bot.edit_message_text(f"Q{q_idx+1}/5 {result}\n\n{qdata['q']}\n\nAnswer revealed. Next Q in 1 sec...", call.message.chat.id, call.message.message_id)
    except:
        pass
    bot.answer_callback_query(call.id, result)
    # FIX: Send next Q in background thread so it doesn't block
    threading.Thread(target=send_next_delayed, args=(uid, q_idx+1), daemon=True).start()

@app.route('/')
def home():
    return "Vidyashala 5Q Bot OK"

def run_bot():
    while True:
        try:
            bot.delete_webhook(drop_pending_updates=True)
            time.sleep(2)
            bot.infinity_polling(timeout=10, long_polling_timeout=10)
        except Exception as e:
            print(f"Poll error {e}")
            time.sleep(5)

threading.Thread(target=run_bot, daemon=True).start()
