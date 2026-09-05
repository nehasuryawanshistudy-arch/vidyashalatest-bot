import os, time, threading, io, csv, requests
import telebot
from flask import Flask
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from PIL import Image, ImageDraw, ImageFont

BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    print("ERROR: BOT_TOKEN env var not set in Render")
    # Don't crash, let Flask start to show error
    BOT_TOKEN = "MISSING_TOKEN"

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
app = Flask(__name__)

# BRAND
BRAND = {"YELLOW":(255,193,7), "BLUE":(11,61,179), "NAVY":(10,25,49), "WHITE":(255,255,255)}
SHEET_ID = "1921UYtW2eka524IVrcrJYkGyzoz_qUbPHJKCePdftlA"
SHEET_CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv"

sessions, best_times, active_timers, timer_msg = {}, {}, {}, {}

def fetch_questions():
    try:
        r = requests.get(SHEET_CSV_URL, timeout=10)
        r.raise_for_status()
        reader = csv.DictReader(io.StringIO(r.text))
        quiz = []
        for row in reader:
            if not row.get('Question'): continue
            opts = [row.get('Option A',''), row.get('Option B',''), row.get('Option C',''), row.get('Option D',''), row.get('Option E','')]
            ans_letter = (row.get('Correct Answer (A/B/C/D/E)') or 'A').strip().upper()
            ans = {'A':0,'B':1,'C':2,'D':3,'E':4}.get(ans_letter,0)
            quiz.append({"q":row['Question'],"opts":opts,"ans":ans})
        return quiz if quiz else None
    except Exception as e:
        print(f"Sheet fetch failed: {e}")
        return None

QUIZ_FALLBACK = [
    {"q": "SI on 15k for 2yr @10% is 3000. What is CI?", "opts": ["₹3150","₹3300","₹3225","₹3000","₹3100"], "ans": 0},
    {"q": "25 x 25 =?", "opts": ["500","625","600","650","525"], "ans": 1},
    {"q": "Speed 60km/h for 2.5hr =?", "opts": ["120km","150km","180km","100km","200km"], "ans": 1},
    {"q": "If CP=100, Profit 20%, SP =?", "opts": ["110","120","130","100","115"], "ans": 1},
    {"q": "√144 + √64 =?", "opts": ["18","20","16","22","19"], "ans": 1},
]

def get_quiz():
    q = fetch_questions()
    return q if q and len(q)>=1 else QUIZ_FALLBACK

def load_font(size, bold=False):
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", size)
    except:
        return ImageFont.load_default()

def generate_launch_card():
    W,H = 1080,1350
    img = Image.new("RGB", (W,H), BRAND["NAVY"])
    draw = ImageDraw.Draw(img)
    cx,cy = W//2, 420
    draw.ellipse((cx-150, cy-150, cx+150, cy+150), fill=BRAND["YELLOW"])
    draw.text((cx-20, cy-60), "√", fill=BRAND["BLUE"], font=load_font(130, True), anchor="mm")
    draw.ellipse((60,40,140,120), fill=BRAND["YELLOW"])
    draw.text((100,80), "√", fill=BRAND["BLUE"], font=load_font(40, True), anchor="mm")
    draw.text((160,50), "VIDYASHALA", fill=BRAND["WHITE"], font=load_font(22, True))
    draw.text((160,75), "BANKING | INSURANCE", fill=BRAND["YELLOW"], font=load_font(18, True))
    draw.text((W//2, 720), "Take a Diagnostic Test", fill=BRAND["WHITE"], font=load_font(56, True), anchor="mm")
    draw.text((W//2, 800), "It's a time based test so be ready!", fill=BRAND["YELLOW"], font=load_font(30, True), anchor="mm")
    draw.rounded_rectangle((W//2-220, 1020, W//2+220, 1090), radius=30, fill=BRAND["YELLOW"])
    draw.text((W//2, 1055), "TAP TO START", fill=BRAND["NAVY"], font=load_font(32, True), anchor="mm")
    buf = io.BytesIO(); img.save(buf, format="PNG"); buf.seek(0); return buf

def generate_question_card(q_idx, total, question, opts):
    W,H = 1080,1350
    img = Image.new("RGB", (W,H), BRAND["NAVY"])
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((60,40,260,100), radius=20, fill=BRAND["YELLOW"])
    draw.text((160,70), f"Q{q_idx+1}/{total}", fill=BRAND["NAVY"], font=load_font(24, True), anchor="mm")
    draw.rounded_rectangle((W-260,40,W-60,100), radius=20, fill=BRAND["YELLOW"])
    draw.text((W-160,70), "LIVE TIMER", fill=BRAND["NAVY"], font=load_font(20, True), anchor="mm")
    cx,cy = W//2, 260
    draw.ellipse((cx-100, cy-100, cx+100, cy+100), fill=BRAND["YELLOW"])
    draw.text((cx, cy), "√", fill=BRAND["BLUE"], font=load_font(100, True), anchor="mm")
    f_q = load_font(42, True)
    # simple wrap
    words = question.split(); lines=[]; cur=""
    for w in words:
        test = cur+" "+w if cur else w
        if draw.textlength(test, font=f_q) < W-120:
            cur=test
        else:
            lines.append(cur); cur=w
    if cur: lines.append(cur)
    y=430
    for line in lines[:3]:
        draw.text((W//2, y), line, fill=BRAND["WHITE"], font=f_q, anchor="mm"); y+=55
    y_opt=y+20; f_opt=load_font(36, True)
    for i,opt in enumerate(opts[:5]):
        if not opt: continue
        draw.rounded_rectangle((80,y_opt,W-80,y_opt+80), radius=18, fill=BRAND["WHITE"])
        draw.rounded_rectangle((80,y_opt,160,y_opt+80), radius=18, fill=BRAND["YELLOW"])
        draw.text((120, y_opt+40), chr(65+i), fill=BRAND["NAVY"], font=load_font(32, True), anchor="mm")
        draw.text((180, y_opt+40), str(opt), fill=BRAND["NAVY"], font=f_opt, anchor="lm")
        y_opt+=95
    buf = io.BytesIO(); img.save(buf, format="PNG"); buf.seek(0); return buf

def get_q_caption(q_idx, elapsed, total):
    return f"Q{q_idx+1}/{total} - {elapsed:.1f}s"

def live_updater(uid, total):
    while active_timers.get(uid):
        try:
            cur = sessions[uid]['cur']
            elapsed = time.time() - sessions[uid]['start']
            chat_id, msg_id = timer_msg.get(uid,(None,None))
            if not chat_id: break
            quiz = get_quiz()
            markup = InlineKeyboardMarkup(row_width=1)
            for i,opt in enumerate(quiz[cur]['opts']):
                if opt:
                    markup.add(InlineKeyboardButton(f"{chr(65+i)} : {opt}", callback_data=f"ans_{cur}_{i}"))
            bot.edit_message_caption(caption=get_q_caption(cur, elapsed, total), chat_id=chat_id, message_id=msg_id, reply_markup=markup)
        except: pass
        time.sleep(0.8)

def send_question(uid, q_idx):
    quiz = get_quiz()
    sessions[uid]['cur']=q_idx; sessions[uid]['start']=time.time(); active_timers[uid]=True
    total=len(quiz); q=quiz[q_idx]
    markup=InlineKeyboardMarkup(row_width=1)
    for i,opt in enumerate(q['opts']):
        if opt: markup.add(InlineKeyboardButton(f"{chr(65+i)} : {opt}", callback_data=f"ans_{q_idx}_{i}"))
    card=generate_question_card(q_idx,total,q['q'],q['opts'])
    msg=bot.send_photo(uid, card, caption=get_q_caption(q_idx,0.0,total), reply_markup=markup)
    timer_msg[uid]=(msg.chat.id, msg.message_id)
    threading.Thread(target=live_updater, args=(uid,total), daemon=True).start()

def send_start_screen(uid):
    quiz=get_quiz()
    txt=f"DIAGNOSTIC READY ({len(quiz)} Qs) - Time based, be ready!"
    markup=InlineKeyboardMarkup().add(InlineKeyboardButton("TAP TO START THE TEST", callback_data="start_test"))
    card=generate_launch_card()
    bot.send_photo(uid, card, caption=txt, reply_markup=markup)

def send_next(uid, next_idx):
    time.sleep(1.2); quiz=get_quiz()
    if next_idx < len(quiz):
        send_question(uid, next_idx)
    else:
        sess=sessions[uid]
        total=sum(1 for i,a in enumerate(sess['answers']) if a==quiz[i]['ans'])
        txt=f"SCORE {total}/{len(quiz)}\n"
        for i in range(len(quiz)):
            u_ans=sess['answers'][i]; u_time=sess['times'][i]
            best=best_times.get(i)
            best_str=f"{best[0]:.2f}s by @{best[1]}" if best else "YOU TOPPER"
            txt+=f"Q{i+1}: Your {chr(65+u_ans)} ({u_time:.2f}s) | Top {best_str}\n"
        bot.send_message(uid, txt)

@bot.message_handler(commands=['start'])
def handle_start(message):
    uid=message.from_user.id
    if "quiz" in message.text:
        sessions[uid]={'cur':0,'answers':[],'times':[],'start':0}
        send_start_screen(uid)
    else:
        bot.send_message(uid,"Go to @vidyashalatest and tap Take Diagnostic Test")

@bot.message_handler(commands=['quiz'])
def post_card(message):
    username=bot.get_me().username
    markup=InlineKeyboardMarkup().add(InlineKeyboardButton("Take Diagnostic Test", url=f"https://t.me/{username}?start=quiz"))
    caption="Take a Diagnostic Test\nIt's a time based test so be ready!"
    card=generate_launch_card()
    try:
        bot.send_photo("@vidyashalatest", card, caption=caption, reply_markup=markup)
        bot.reply_to(message, "Posted to @vidyashalatest")
    except Exception as e:
        bot.reply_to(message, f"Make bot admin in channel: {e}")

@bot.callback_query_handler(func=lambda c: True)
def handle_all(call):
    uid=call.from_user.id
    if call.data=="start_test":
        send_question(uid,0)
    elif call.data.startswith("ans_"):
        _,q_idx,opt_idx=call.data.split("_"); q_idx,opt_idx=int(q_idx),int(opt_idx)
        if uid not in sessions or sessions[uid]['cur']!=q_idx: return
        active_timers[uid]=False
        elapsed=time.time()-sessions[uid]['start']
        sessions[uid]['answers'].append(opt_idx); sessions[uid]['times'].append(elapsed)
        quiz=get_quiz()
        if opt_idx==quiz[q_idx]['ans']:
            cur=best_times.get(q_idx)
            if not cur or elapsed<cur[0]:
                best_times[q_idx]=(elapsed, call.from_user.username or call.from_user.first_name)
        result="CORRECT!" if opt_idx==quiz[q_idx]['ans'] else f"WRONG! Ans {chr(65+quiz[q_idx]['ans'])}"
        try: bot.edit_message_caption(caption=result, chat_id=call.message.chat.id, message_id=call.message.message_id)
        except: pass
        bot.answer_callback_query(call.id, result)
        threading.Thread(target=send_next, args=(uid,q_idx+1), daemon=True).start()

@app.route('/')
def home():
    return "Vidyashala AUTO bot OK"

def run_bot():
    while True:
        try:
            bot.delete_webhook(drop_pending_updates=True)
            time.sleep(2)
            bot.infinity_polling(timeout=10, long_polling_timeout=10)
        except Exception as e:
            print(f"Bot polling error: {e}"); time.sleep(5)

threading.Thread(target=run_bot, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
