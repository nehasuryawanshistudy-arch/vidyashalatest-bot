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

def get_beautiful_q(q_idx, elapsed):
    q = QUIZ[q_idx]
    return (
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📝 QUESTION {q_idx+1} / 5 ⏱️ {elapsed:.1f}s\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"```\n{q['q']}\n```\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👇 TAP AN OPTION BELOW\n"
    )

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
            markup = InlineKeyboardMarkup(row_width=1)
            for i, opt in enumerate(qdata['opts']):
                markup.add(InlineKeyboardButton(f"{chr(65+i)} : {opt}", callback_data=f"ans_{cur}_{i}"))
            bot.edit_message_text(get_beautiful_q(cur, elapsed), chat_id, msg_id, reply_markup=markup, parse_mode="Markdown")
        except:
            pass
        time.sleep(0.8)

def send_blurred(uid, q_idx):
    sessions[uid]['cur'] = q_idx
    text = (
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔒 QUESTION {q_idx+1} / 5 LOCKED\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"```\nQuestion Hidden\n```\n\n"
        f"👁️ Tap below to REVEAL & START LIVE TIMER\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    markup = InlineKeyboardMarkup().add(InlineKeyboardButton("👁️ TAP TO REVEAL & START TIMER", callback_data=f"reveal_{q_idx}"))
    msg = bot.send_message(uid, text, reply_markup=markup, parse_mode="Markdown")
    timer_msg[uid] = (uid, msg.message_id)

def send_next(uid, next_idx):
    time.sleep(1.2)
    if next_idx < 5:
        send_blurred(uid, next_idx)
    else:
        # Final Scorecard - Beautiful
        sess = sessions[uid]
        total = sum(1 for i, a in enumerate(sess['answers']) if a == QUIZ[i]['ans'])
        txt = f"━━━━━━━━━━━━━━━━━━━━\n📊 VIDYASHALA SCORECARD\n━━━━━━━━━━━━━━━━━━━━\n🏆 Score: {total}/5\n\n"
        for i in range(5):
            qdata = QUIZ[i]
            u_ans = sess['answers'][i]
            u_time = sess['times'][i]
            best = best_times.get(i)
            best_str = f"{best[0]:.2f}s by @{best[1]}" if best else "YOU ARE TOPPER!"
            txt += f"━━━━━━━━━━━━\nQ{i+1}: {qdata['q']}\n"
            for j, opt in enumerate(qdata['opts']):
                prefix = f"{chr(65+j)}. {opt}"
                if j == qdata['ans']: prefix += " ✅ CORRECT"
                if j == u_ans and j!= qdata['ans']: prefix += " ❌ YOUR CHOICE"
                if j == u_ans and j == qdata['ans']: prefix += " 👉 YOU (CORRECT)"
                txt += prefix + "\n"
            txt += f"⏱️ Your Time: {u_time:.2f}s\n🏆 Topper Time: {best_str}\n\n"
        txt += "━━━━━━━━━━━━━━━━━━━━\n"
        bot.send_message(uid, txt, parse_mode="Markdown")

@bot.message_handler(commands=['start'])
def handle_start(message):
    uid = message.from_user.id
    if "quiz" in message.text:
        sessions[uid] = {'cur':0, 'answers':[], 'times':[], 'start':0}
        send_blurred(uid, 0)
    else:
        bot.send_message(uid, "Welcome to Vidyashala! Go to @vidyashalatest")

@bot.message_handler(commands=['quiz'])
def post_card(message):
    username = bot.get_me().username
    markup = InlineKeyboardMarkup().add(InlineKeyboardButton("📝 TAKE 5-Q QUIZ IN DM", url=f"https://t.me/{username}?start=quiz"))
    bot.send_message("@vidyashalatest", "📚 **NEW 5-Q BEAUTIFUL QUIZ LIVE!**\n🔒 Blurred → Reveal → Live Timer\n📊 Final Scorecard with Topper Comparison\n👇 Tap below", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: True)
def handle_all(call):
    uid = call.from_user.id
    data = call.data

    if data.startswith("reveal_"):
        q_idx = int(data.split("_")[1])
        if uid not in sessions or sessions[uid]['cur']!= q_idx:
            return
        sessions[uid]['start'] = time.time()
        active_timers[uid] = True
        timer_msg[uid] = (call.message.chat.id, call.message.message_id)
        qdata = QUIZ[q_idx]
        markup = InlineKeyboardMarkup(row_width=1)
        for i, opt in enumerate(qdata['opts']):
            markup.add(InlineKeyboardButton(f"{chr(65+i)} : {opt}", callback_data=f"ans_{q_idx}_{i}"))
        bot.edit_message_text(get_beautiful_q(q_idx, 0.0), call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")
        threading.Thread(target=live_updater, args=(uid,), daemon=True).start()

    elif data.startswith("ans_"):
        _, q_idx, opt_idx = data.split("_")
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
        is_correct = opt_idx == qdata['ans']
        res_text = (
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{'✅ CORRECT ANSWER!' if is_correct else '❌ WRONG ANSWER!'}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"```\n{qdata['q']}\n```\n\n"
            f"Correct: {chr(65+qdata['ans'])} : {qdata['opts'][qdata['ans']]}\n"
            f"Your Choice: {chr(65+opt_idx)} : {qdata['opts'][opt_idx]}\n\n"
            f"Next question in 1 sec..."
        )
        try:
            bot.edit_message_text(res_text, call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        except:
            pass
        bot.answer_callback_query(call.id, "Answer Saved!")
        threading.Thread(target=send_next, args=(uid, q_idx+1), daemon=True).start()

@app.route('/')
def home():
    return "Vidyashala Beautiful Bot OK"

def run_bot():
    while True:
        try:
            bot.delete_webhook(drop_pending_updates=True)
            time.sleep(2)
            bot.infinity_polling(timeout=10, long_polling_timeout=10)
        except Exception as e:
            print(f"Retry {e}")
            time.sleep(5)

threading.Thread(target=run_bot, daemon=True).start()
