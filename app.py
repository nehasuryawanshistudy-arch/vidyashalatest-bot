import os, time, threading, io, csv, requests
import telebot
from flask import Flask
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from PIL import Image, ImageDraw, ImageFont

BOT_TOKEN = os.getenv('BOT_TOKEN')
bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
app = Flask(__name__)

# BRAND LOCKED from your slide vidyashala-slide-1-1080x1350_3.png
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

# Fallback quiz
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
    # Try DejaVu, fallback default
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", size)
    except:
        return ImageFont.load_default()

def generate_launch_card():
    W,H = 1080,1350
    img = Image.new("RGB", (W,H), BRAND["NAVY"])
    draw = ImageDraw.Draw(img)
    # faint math symbols background
    try:
        f_small = load_font(60)
        symbols = ["π","∑","√","x²","Δ","a/b"]
        for i,s in enumerate(symbols):
            draw.text((80+i*170, H-200), s, fill=(255,255,255,30), font=f_small)
    except: pass
    # yellow glowing circle logo
    cx,cy = W//2, 420
    for r in range(180,120,-10):
        alpha = int(255*(1-(r-120)/60)*0.15)
        draw.ellipse((cx-r, cy-r, cx+r, cy+r), fill=(255,193,7,alpha) if len(BRAND["YELLOW"])==4 else BRAND["YELLOW"])
    draw.ellipse((cx-150, cy-150, cx+150, cy+150), fill=BRAND["YELLOW"], outline=(0,0,0), width=4)
    # Blue sqrt symbol
    try:
        f_logo = load_font(160, True)
        draw.text((cx-55, cy-90), "√", fill=BRAND["BLUE"], font=f_logo)
    except: pass
    draw.text((cx-70, cy+80), "BANKING | INSURANCE", fill=BRAND["NAVY"], font=load_font(22, True), anchor="mm")
    # Top left small logo
    draw.ellipse((60,40,140,120), fill=BRAND["YELLOW"])
    draw.text((75,55), "√", fill=BRAND["BLUE"], font=load_font(50, True))
    draw.text((160,50), "VIDYASHALA", fill=BRAND["WHITE"], font=load_font(22, True))
    draw.text((160,75), "BANKING | INSURANCE", fill=BRAND["YELLOW"], font=load_font(18, True))
    # Main text
    draw.text((W//2, 720), "Take a Diagnostic Test", fill=BRAND["WHITE"], font=load_font(62, True), anchor="mm")
    draw.text((W//2, 800), "It's a time based test so be ready!", fill=BRAND["YELLOW"], font=load_font(32, True), anchor="mm")
    # Badge
    bx,by = W//2, 870
    draw.rounded_rectangle((bx-250, by-20, bx+250, by+20), radius=20, outline=BRAND["YELLOW"], width=2)
    draw.text((bx, by), "BANKING | INSURANCE | DIAGNOSTIC", fill=BRAND["YELLOW"], font=load_font(20, True), anchor="mm")
    # CTA button
    draw.rounded_rectangle((W//2-220, 1020, W//2+220, 1090), radius=30, fill=BRAND["YELLOW"])
    draw.text((W//2, 1055), "TAP TO START", fill=BRAND["NAVY"], font=load_font(34, True), anchor="mm")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

def generate_question_card(q_idx, total, question, opts):
    W,H = 1080,1350
    img = Image.new("RGB", (W,H), BRAND["NAVY"])
    draw = ImageDraw.Draw(img)
    # Top badges
    draw.rounded_rectangle((60,40,260,100), radius=20, fill=BRAND["YELLOW"])
    draw.text((160,70), f"QUESTION {q_idx+1}/{total}", fill=BRAND["NAVY"], font=load_font(24, True), anchor="mm")
    draw.rounded_rectangle((W-260,40,W-60,100), radius=20, fill=BRAND["YELLOW"])
    draw.text((W-160,70), "LIVE TIMER", fill=BRAND["NAVY"], font=load_font(22, True), anchor="mm")
    # Logo glow
    cx,cy = W//2, 280
    draw.ellipse((cx-130, cy-130, cx+130, cy+130), fill=BRAND["YELLOW"])
    draw.text((cx-40, cy-50), "√", fill=BRAND["BLUE"], font=load_font(120, True))
    # Question text - wrap
    def wrap_text(text, font, max_width):
        words = text.split()
        lines, cur = [], ""
        for w in words:
            test = cur + " " + w if cur else w
            if draw.textlength(test, font=font) <= max_width:
                cur = test
            else:
                lines.append(cur)
                cur = w
        if cur: lines.append(cur)
        return lines
    f_q = load_font(52, True)
    lines = wrap_text(question, f_q, W-120)
    y = 480
    for line in lines:
        draw.text((W//2, y), line, fill=BRAND["WHITE"], font=f_q, anchor="mm")
        y+=65
    # Options
    f_opt = load_font(42, True)
    y_opt = y+30
    for i,opt in enumerate(opts[:5]):
        if not opt: continue
        x1,y1 = 80, y_opt
        x2,y2 = W-80, y_opt+90
        draw.rounded_rectangle((x1,y1,x2,y2), radius=20, fill=BRAND["WHITE"])
        draw.rounded_rectangle((x1,y1,x1+80,y2), radius=20, fill=BRAND["YELLOW"])
        draw.text((x1+40, y1+45), chr(65+i), fill=BRAND["NAVY"], font=load_font(40, True), anchor="mm")
        draw.text((x1+110, y1+45), str(opt), fill=BRAND["NAVY"], font=f_opt, anchor="lm")
        y_opt+=110
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

def get_q_caption(q_idx, elapsed, total):
    return f"📝 Q{q_idx+1}/{total} ⏱️ {elapsed:.1f}s"

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
    sessions[uid]['cur']=q_idx
    sessions[uid]['start']=time.time()
    active_timers[uid]=True
    total = len(quiz)
    q = quiz[q_idx]
    markup = InlineKeyboardMarkup(row_width=1)
    for i,opt in enumerate(q['opts']):
        if opt:
            markup.add(InlineKeyboardButton(f"{chr(65+i)} : {opt}", callback_data=f"ans_{q_idx}_{i}"))
    card = generate_question_card(q_idx, total, q['q'], q['opts'])
    msg = bot.send_photo(uid, card, caption=get_q_caption(q_idx,0.0,total), reply_markup=markup)
    timer_msg[uid]=(msg.chat.id, msg.message_id)
    threading.Thread(target=live_updater, args=(uid,total), daemon=True).start()

def send_start_screen(uid):
    quiz = get_quiz()
    txt = f"🎯 **DIAGNOSTIC TEST READY** ({len(quiz)} Qs)\n⏱️ Time based test so be ready!\n\nTap below to START with LIVE timer"
    markup = InlineKeyboardMarkup().add(InlineKeyboardButton("🚀 TAP TO START THE TEST", callback_data="start_test"))
    card = generate_launch_card()
    bot.send_photo(uid, card, caption=txt, reply_markup=markup, parse_mode="Markdown")

def send_next(uid, next_idx):
    time.sleep(1.2)
    quiz = get_quiz()
    if next_idx < len(quiz):
        send_question(uid, next_idx)
    else:
        sess = sessions[uid]
        total = sum(1 for i,a in enumerate(sess['answers']) if a==quiz[i]['ans'])
        txt = f"📊 **SCORECARD {total}/{len(quiz)}**\n━━━━━━━━━━━━\n\n"
        for i in range(len(quiz)):
            u_ans=sess['answers'][i]; u_time=sess['times'][i]
            best=best_times.get(i)
            best_str=f"{best[0]:.2f}s by @{best[1]}" if best else "YOU ARE TOPPER!"
            txt+=f"**Q{i+1}: {quiz[i]['q']}**\nYour: {chr(65+u_ans)} ({u_time:.2f}s) | Topper: {best_str}\n\n"
        bot.send_message(uid, txt, parse_mode="Markdown")

@bot.message_handler(commands=['start'])
def handle_start(message):
    uid=message.from_user.id
    if "quiz" in message.text:
        sessions[uid]={'cur':0,'answers':[],'times':[],'start':0}
        send_start_screen(uid)
    else:
        bot.send_message(uid,"Welcome! Go to @vidyashalatest and tap Take Diagnostic Test")

@bot.message_handler(commands=['quiz'])
def post_card(message):
    username=bot.get_me().username
    markup=InlineKeyboardMarkup().add(InlineKeyboardButton("📝 Take Diagnostic Test", url=f"https://t.me/{username}?start=quiz"))
    caption="🎯 Take a Diagnostic Test\n⏱️ It's a time based test so be ready!"
    card = generate_launch_card()
    try:
        bot.send_photo("@vidyashalatest", card, caption=caption, reply_markup=markup)
        bot.reply_to(message, "✅ Posted branded launch card to @vidyashalatest (auto-generated from Drive sheet)")
    except Exception as e:
        bot.reply_to(message, f"Failed to post to channel, make bot admin: {e}")

@bot.callback_query_handler(func=lambda c: True)
def handle_all(call):
    uid=call.from_user.id
    if call.data=="start_test":
        send_question(uid,0)
    elif call.data.startswith("ans_"):
        _,q_idx,opt_idx=call.data.split("_")
        q_idx,opt_idx=int(q_idx),int(opt_idx)
        if uid not in sessions or sessions[uid]['cur']!=q_idx: return
        active_timers[uid]=False
        elapsed=time.time()-sessions[uid]['start']
        sessions[uid]['answers'].append(opt_idx)
        sessions[uid]['times'].append(elapsed)
        quiz = get_quiz()
        if opt_idx==quiz[q_idx]['ans']:
            cur=best_times.get(q_idx)
            if not cur or elapsed<cur[0]:
                best_times[q_idx]=(elapsed, call.from_user.username or call.from_user.first_name)
        result="✅ CORRECT!" if opt_idx==quiz[q_idx]['ans'] else f"❌ WRONG! Ans {chr(65+quiz[q_idx]['ans'])}"
        try:
            bot.edit_message_caption(caption=result, chat_id=call.message.chat.id, message_id=call.message.message_id)
        except: pass
        bot.answer_callback_query(call.id, result)
        threading.Thread(target=send_next, args=(uid,q_idx+1), daemon=True).start()

@app.route('/')
def home():
    return "Vidyashala AUTO bot OK - reads from Drive sheet"

def run_bot():
    while True:
        try:
            bot.delete_webhook(drop_pending_updates=True)
            time.sleep(2)
            bot.infinity_polling(timeout=10, long_polling_timeout=10)
        except Exception as e:
            print(e); time.sleep(5)
threading.Thread(target=run_bot, daemon=True).start()
