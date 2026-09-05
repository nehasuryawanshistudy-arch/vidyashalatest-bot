import os, time, threading
import telebot
from flask import Flask
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

BOT_TOKEN = os.getenv('BOT_TOKEN')
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
app = Flask(__name__)

# === YOUR BRANDING - PUT HEX HERE AFTER YOU SEND ===
BRAND_PRIMARY = "#1E3A8A" # Replace with your colour
BRAND_BG = "white" # Telegram can't do custom bg, but image cards can

QUIZ = [
    {"q": "SI on 15k for 2yr @10% is 3000. What is CI?", "opts": ["₹3150", "₹3300", "₹3225", "₹3000", "₹3100"], "ans": 0},
    {"q": "25 x 25 =?", "opts": ["500", "625", "600", "650", "525"], "ans": 1},
    {"q": "Speed 60km/h for 2.5hr =?", "opts": ["120km", "150km", "180km", "100km", "200km"], "ans": 1},
    {"q": "If CP=100, Profit 20%, SP =?", "opts": ["110", "120", "130", "100", "115"], "ans": 1},
    {"q": "√144 + √64 =?", "opts": ["18", "20", "16", "22", "19"], "ans": 1},
]

sessions, best_times, active_timers, timer_msg = {}, {}, {}, {}

def get_q_text(q_idx, elapsed):
    q = QUIZ[q_idx]
    # Bigger look: BOLD + CAPS + box
    return (
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📝 Q{q_idx+1}/5 ⏱️ {elapsed:.1f}s\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"**{q['q'].upper()}**\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
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
    sessions[uid]['cur'] = q_idx
    sessions[uid]['start'] = time.time()
    active_timers[uid] = True
    qdata = QUIZ[q_idx]
    markup = InlineKeyboardMarkup(row_width=1)
    for i, opt in enumerate(qdata['opts']):
        markup.add(InlineKeyboardButton(f"➡️ {chr(65+i)} : {opt}", callback_data=f"ans_{q_idx}_{i}"))
    msg = bot.send_message(uid, get_q_text(q_idx, 0.0), reply_markup=markup, parse_mode="Markdown")
    timer_msg[uid] = (uid, msg.message_id)
    threading.Thread(target=live_updater, args=(uid,), daemon=True).start()

def send_start_screen(uid):
    text = (
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 DIAGNOSTIC TEST\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"**5 Questions | Time Based**\n"
        f"Be Ready! Timer starts on TAP\n\n"
        f"👇 Tap to START TEST\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    markup = InlineKeyboardMarkup().add(InlineKeyboardButton("🚀 TAP TO START TEST WITH TIMER", callback_data="start_test"))
    bot.send_message(uid, text, reply_markup=markup, parse_mode="Markdown")

def send_next(uid, next_idx):
    time.sleep(1.0)
    if next_idx < 5:
        send_question(uid, next_idx)
    else:
        sess = sessions[uid]
        total = sum(1 for i, a in enumerate(sess['answers']) if a == QUIZ[i]['ans'])
        txt = f"📊 **DIAGNOSTIC SCORECARD - {total}/5**\n━━━━━━━━━━━━\n\n"
        for i in range(5):
            qdata = QUIZ[i]
            u_ans = sess['answers'][i]
            u_time = sess['times'][i]
            best = best_times.get(i)
            best_str = f"{best[0]:.2f}s by @{best[1]}" if best else "YOU ARE TOPPER!"
            txt += f"**Q{i+1}: {qdata['q']}**\n"
            for j, opt in enumerate(qdata['opts']):
                line = f"{chr(65+j)}. {opt}"
                if j == qdata['ans']: line += " ✅"
                if j == u_ans: line += " 👉 You"
                txt += line + "\n"
            txt += f"⏱️ You: {u_time:.2f}s | 🏆 Topper: {best_str}\n\n"
        bot.send_message(uid, txt, parse_mode="Markdown")

@bot.message_handler(commands=['start'])
def handle_start(message):
    uid = message.from_user.id
    if "quiz" in message.text:
        sessions[uid] = {'cur':0, 'answers':[], 'times':[], 'start':0}
        send_start_screen(uid)
    else:
        bot.send_message(uid, "Welcome! Go to @vidyashalatest")

@bot.message_handler(commands=['quiz'])
def post_card(message):
    username = bot.get_me().username
    markup = InlineKeyboardMarkup().add(InlineKeyboardButton("📝 Take Diagnostic Test", url=f"https://t.me/{username}?start=quiz"))
    # --- WITH LOGO ---
    # If you have logo file_id, use send_photo. For now text + logo placeholder
    try:
        # Try sending with logo if LOGO_URL env is set
        logo_url = os.getenv('LOGO_URL') # put your logo image URL in Render Env
        if logo_url:
            bot.send_photo("@vidyashalatest", logo_url, caption="🎯 **Take a Diagnostic Test**\n⏱️ It's a time based test so be ready!\n👇 Tap below to start in DM", reply_markup=markup, parse_mode="Markdown")
        else:
            bot.send_message("@vidyashalatest", "🎯 **Take a Diagnostic Test**\n⏱️ It's a time based test so be ready!\n👇 Tap below to start in DM\n\n@vidyashalatest", reply_markup=markup, parse_mode="Markdown")
    except Exception as e:
        bot.send_message("@vidyashalatest", "🎯 **Take a Diagnostic Test**\n⏱️ It's a time based test so be ready!", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda c: True)
def handle_all(call):
    uid = call.from_user.id
    if call.data == "start_test":
        send_question(uid, 0)

    elif call.data.startswith("ans_"):
        _, q_idx, opt_idx = call.data.split("_")
        q_idx, opt_idx = int(q_idx), int(opt_idx)
        if sessions[uid]['cur']!= q_idx: return
        active_timers[uid]=False
        elapsed = time.time() - sessions[uid]['start']
        sessions[uid]['answers'].append(opt_idx)
        sessions[uid]['times'].append(elapsed)
        if opt_idx == QUIZ[q_idx]['ans']:
            cur_best = best_times.get(q_idx)
            if not cur_best or elapsed < cur_best[0]:
                best_times[q_idx]=(elapsed, call.from_user.username or call.from_user.first_name)
        qdata = QUIZ[q_idx]
        result = "✅ CORRECT!" if opt_idx==qdata['ans'] else f"❌ WRONG! Correct is {chr(65+qdata['ans'])}"
        try:
            bot.edit_message_text(f"{result}\n\n**{qdata['q']}**\nNext Q coming...", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
        except: pass
        bot.answer_callback_query(call.id, result)
        threading.Thread(target=send_next, args=(uid, q_idx+1), daemon=True).start()

@app.route('/')
def home():
    return "Vidyashala Diagnostic Bot OK"

def run_bot():
    while True:
        try:
            bot.delete_webhook(drop_pending_updates=True)
            time.sleep(2)
            bot.infinity_polling(timeout=10, long_polling_timeout=10)
        except Exception as e:
            print(e)
            time.sleep(5)

threading.Thread(target=run_bot, daemon=True).start()
