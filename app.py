import os, time, threading, io, csv, requests
from flask import Flask, request, abort
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)

BRAND = {"YELLOW":(255,193,7), "BLUE":(11,61,179), "NAVY":(10,25,49), "WHITE":(255,255,255), "LIGHT_NAVY":(21,43,82)}
SHEET_ID = "1921UYtW2eka524IVrcrJYkGyzoz_qUbPHJKCePdftlA"
SHEET_CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv"

BOT_TOKEN = os.getenv('BOT_TOKEN')
RENDER_URL = os.getenv('RENDER_EXTERNAL_URL')

print(f"BOT_TOKEN present: {bool(BOT_TOKEN)} | RENDER_URL: {RENDER_URL}")

bot = None
if BOT_TOKEN and ":" in BOT_TOKEN:
    try:
        import telebot
        from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, Update, InputMediaPhoto
        bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
        print("Bot initialized OK")
    except Exception as e:
        print(f"Bot init failed: {e}")
        bot = None
else:
    print("BOT_TOKEN missing - bot disabled")
    bot = None

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
    {"q": "SI on 15k for 2yr @10% is 3000. What is CI?", "opts": ["3150","3300","3225","3000","3100"], "ans": 0},
    {"q": "25 x 25 =?", "opts": ["500","625","600","650","525"], "ans": 1},
    {"q": "Speed 60km/h for 2.5hr =?", "opts": ["120km","150km","180km","100km","200km"], "ans": 1},
    {"q": "If CP=100, Profit 20%, SP =?", "opts": ["110","120","130","100","115"], "ans": 1},
    {"q": "sqrt144 + sqrt64 =?", "opts": ["18","20","16","22","19"], "ans": 1},
]

def get_quiz():
    q = fetch_questions()
    return q if q and len(q)>=1 else QUIZ_FALLBACK

def load_font(size, bold=False):
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", size)
    except:
        return ImageFont.load_default()

def draw_correct_logo(draw, cx, cy, radius, bg=YELLOW, tick_color=None):
    # Correct Vidyashala logo: Yellow circle + Blue thick checkmark (✓)
    if tick_color is None:
        tick_color = BRAND["BLUE"]
    draw.ellipse((cx-radius, cy-radius, cx+radius, cy+radius), fill=BRAND["YELLOW"])
    # Draw a proper checkmark with thick lines - looks like √ but proper ✓
    # Use 2 lines forming tick
    x1 = cx - radius*0.35
    y1 = cy + radius*0.05
    x2 = cx - radius*0.05
    y2 = cy + radius*0.35
    x3 = cx + radius*0.45
    y3 = cy - radius*0.30
    # thickness proportional to radius
    w = max(8, int(radius*0.12))
    draw.line([(x1,y1),(x2,y2)], fill=tick_color, width=w, joint="round")
    draw.line([(x2,y2),(x3,y3)], fill=tick_color, width=w, joint="round")

def generate_launch_card():
    W,H = 1080,1350
    img = Image.new("RGB", (W,H), BRAND["NAVY"])
    draw = ImageDraw.Draw(img)
    # Subtle background pattern - light navy circles
    for i in range(0, W, 200):
        for j in range(200, H, 200):
            draw.ellipse((i-20, j-20, i+20, j+20), fill=BRAND["LIGHT_NAVY"])
    # Big centered logo - CORRECTED
    cx,cy = W//2, 420
    draw_correct_logo(draw, cx, cy, 150)
    # Small top left logo - CORRECTED
    draw_correct_logo(draw, 100, 80, 35)
    draw.text((160,50), "VIDYASHALA", fill=BRAND["WHITE"], font=load_font(24, True))
    draw.text((160,80), "BANKING | INSURANCE | SSC", fill=BRAND["YELLOW"], font=load_font(16, True))
    # Title
    draw.text((W//2, 700), "Take a Diagnostic Test", fill=BRAND["WHITE"], font=load_font(54, True), anchor="mm")
    draw.text((W//2, 770), "It's a time based test so be ready!", fill=BRAND["YELLOW"], font=load_font(30, True), anchor="mm")
    # Attractive CTA button with shadow
    draw.rounded_rectangle((W//2-230, 1020-4, W//2+230, 1090+4), radius=32, fill=(0,0,0,60))
    draw.rounded_rectangle((W//2-220, 1020, W//2+220, 1090), radius=30, fill=BRAND["YELLOW"])
    draw.text((W//2, 1055), "TAP TO START ▶", fill=BRAND["NAVY"], font=load_font(32, True), anchor="mm")
    # Bottom trust line
    draw.text((W//2, 1220), "Trusted by 10k+ Banking Aspirants", fill=BRAND["WHITE"], font=load_font(20, True), anchor="mm")
    buf = io.BytesIO(); img.save(buf, format="PNG"); buf.seek(0); return buf

def generate_question_card_clickable(q_idx, total, question, elapsed=0.0):
    W,H = 1080, 1150
    img = Image.new("RGB", (W,H), BRAND["NAVY"])
    draw = ImageDraw.Draw(img)
    # Background subtle dots
    for i in range(0, W, 180):
        for j in range(150, H, 180):
            draw.ellipse((i-15, j-15, i+15, j+15), fill=BRAND["LIGHT_NAVY"])
    # Top bar - Q badge
    draw.rounded_rectangle((50,35,270,95), radius=18, fill=BRAND["YELLOW"])
    draw.text((160,65), f"Q {q_idx+1} / {total}", fill=BRAND["NAVY"], font=load_font(22, True), anchor="mm")
    # Top bar - LIVE TIMER INSIDE CARD (attractive)
    # Timer pill with pulsing red dot effect
    timer_text = f"⏱ {elapsed:.1f}s LIVE"
    # Background pill
    tw = draw.textlength(timer_text, font=load_font(20, True)) + 80
    x2 = W-50
    x1 = x2 - tw
    draw.rounded_rectangle((x1,35,x2,95), radius=18, fill=BRAND["WHITE"])
    # Red dot
    draw.ellipse((x1+18, 52, x1+34, 68), fill=(255,59,48))
    draw.text((x1+48,65), timer_text, fill=BRAND["NAVY"], font=load_font(20, True), anchor="lm")
    # Center logo - CORRECTED LOGO
    cx,cy = W//2, 250
    draw_correct_logo(draw, cx, cy, 85)
    # Progress bar under logo - attractive animated bar based on elapsed
    bar_w = 400
    bar_h = 8
    bx1 = cx - bar_w//2
    by1 = cy + 110
    # Track
    draw.rounded_rectangle((bx1, by1, bx1+bar_w, by1+bar_h), radius=4, fill=(255,255,255,40))
    # Fill - grows with time (mod 10s for loop effect)
    progress = (elapsed % 10) / 10.0
    fill_w = int(bar_w * progress)
    draw.rounded_rectangle((bx1, by1, bx1+fill_w, by1+bar_h), radius=4, fill=BRAND["YELLOW"])
    # Question - big, bold, centered
    f_q = load_font(46, True)
    words = question.split()
    lines = []
    cur = ""
    for w in words:
        test = cur + " " + w if cur else w
        if draw.textlength(test, font=f_q) < W-100:
            cur = test
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    y = 430
    if len(lines) > 4:
        lines = lines[:4]
        lines[-1] = lines[-1][:35] + "..."
    for line in lines:
        # Text with subtle shadow for attractiveness
        draw.text((W//2+2, y+2), line, fill=(0,0,0,100), font=f_q, anchor="mm")
        draw.text((W//2, y), line, fill=BRAND["WHITE"], font=f_q, anchor="mm")
        y += 68
    # Bottom hint - attractive
    draw.rounded_rectangle((W//2-200, y+40, W//2+200, y+85), radius=20, fill=BRAND["YELLOW"])
    draw.text((W//2, y+62), "👇 TAP YOUR ANSWER BELOW", fill=BRAND["NAVY"], font=load_font(20, True), anchor="mm")
    # Footer small branding
    draw.text((W//2, H-40), "VIDYASHALA • Speed + Accuracy", fill=(255,255,255,120), font=load_font(16, True), anchor="mm")
    buf = io.BytesIO(); img.save(buf, format="PNG"); buf.seek(0); return buf

def get_q_caption(q_idx, elapsed, total):
    return f"Q{q_idx+1}/{total} | ⏱ {elapsed:.1f}s LIVE | Choose below 👇"

def build_clickable_markup(q_idx, opts):
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
    markup = InlineKeyboardMarkup(row_width=1)
    emojis = ["🅰️","🅱️","🅲","🅳","🅴"]
    for i,opt in enumerate(opts):
        if not opt: continue
        btn_text = f"{emojis[i]}  {opt}"
        markup.add(InlineKeyboardButton(btn_text, callback_data=f"ans_{q_idx}_{i}"))
    return markup

def live_updater(uid, total):
    # Now updates BOTH image (timer inside card) and caption - looks premium
    while active_timers.get(uid):
        try:
            cur = sessions[uid]['cur']
            elapsed = time.time() - sessions[uid]['start']
            chat_id, msg_id = timer_msg.get(uid,(None,None))
            if not chat_id: break
            quiz = get_quiz()
            # Regenerate card with live timer INSIDE image
            card = generate_question_card_clickable(cur, total, quiz[cur]['q'], elapsed)
            markup = build_clickable_markup(cur, quiz[cur]['opts'])
            if bot:
                # Edit media (image with timer) - this makes timer appear inside card
                from telebot.types import InputMediaPhoto
                bot.edit_message_media(media=InputMediaPhoto(card, caption=get_q_caption(cur, elapsed, total)), chat_id=chat_id, message_id=msg_id, reply_markup=markup)
        except Exception as e:
            # If media edit fails (rate limit), fallback to caption edit
            try:
                if bot:
                    bot.edit_message_caption(caption=get_q_caption(cur, elapsed, total), chat_id=chat_id, message_id=msg_id, reply_markup=markup)
            except: pass
        time.sleep(1.0)

def send_question(uid, q_idx):
    if not bot: return
    quiz = get_quiz()
    sessions[uid]['cur']=q_idx; sessions[uid]['start']=time.time(); active_timers[uid]=True
    total=len(quiz); q=quiz[q_idx]
    markup = build_clickable_markup(q_idx, q['opts'])
    card = generate_question_card_clickable(q_idx, total, q['q'], 0.0)
    msg = bot.send_photo(uid, card, caption=get_q_caption(q_idx,0.0,total), reply_markup=markup)
    timer_msg[uid]=(msg.chat.id, msg.message_id)
    threading.Thread(target=live_updater, args=(uid,total), daemon=True).start()

def send_start_screen(uid):
    if not bot: return
    quiz=get_quiz()
    txt=f"DIAGNOSTIC READY ({len(quiz)} Qs) - Time based, be ready!"
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
    markup=InlineKeyboardMarkup().add(InlineKeyboardButton("▶️ TAP TO START THE TEST", callback_data="start_test"))
    card=generate_launch_card()
    bot.send_photo(uid, card, caption=txt, reply_markup=markup)

def send_next(uid, next_idx):
    time.sleep(1.2); quiz=get_quiz()
    if next_idx < len(quiz):
        send_question(uid, next_idx)
    else:
        sess=sessions[uid]
        total=sum(1 for i,a in enumerate(sess['answers']) if a==quiz[i]['ans'])
        txt=f"✅ FINISHED! SCORE {total}/{len(quiz)}\n\n"
        for i in range(len(quiz)):
            u_ans=sess['answers'][i]; u_time=sess['times'][i]
            best=best_times.get(i)
            best_str=f"{best[0]:.2f}s by @{best[1]}" if best else "YOU ARE TOPPER!"
            mark = "✅" if u_ans==quiz[i]['ans'] else "❌"
            txt+=f"{mark} Q{i+1}: Your {chr(65+u_ans)} ({u_time:.2f}s) | Top: {best_str}\n"
        if bot:
            bot.send_message(uid, txt)

if bot:
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
        from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
        username=bot.get_me().username
        markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🎯 Take Diagnostic Test", url=f"https://t.me/{username}?start=quiz"))
        caption="Take a Diagnostic Test\nIt's a time based test so be ready!"
        card=generate_launch_card()
        try:
            bot.send_photo("@vidyashalatest", card, caption=caption, reply_markup=markup)
            bot.reply_to(message, "Posted to @vidyashalatest - logo fixed ✅")
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
            result="✅ CORRECT!" if opt_idx==quiz[q_idx]['ans'] else f"❌ WRONG! Ans: {chr(65+quiz[q_idx]['ans'])}"
            try:
                if bot:
                    bot.edit_message_caption(caption=result, chat_id=call.message.chat.id, message_id=call.message.message_id)
            except: pass
            if bot:
                bot.answer_callback_query(call.id, result)
            threading.Thread(target=send_next, args=(uid,q_idx+1), daemon=True).start()

@app.route('/')
def home():
    mode = "webhook" if RENDER_URL else "polling"
    return f"Vidyashala bot OK - PREMIUM TIMER INSIDE CARD - mode:{mode}"

@app.route('/webhook', methods=['POST'])
def webhook():
    if not bot:
        return 'bot disabled', 200
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        try:
            update = Update.de_json(json_string)
            bot.process_new_updates([update])
        except Exception as e:
            print(f"Webhook error: {e}")
        return '', 200
    else:
        abort(403)

def setup_webhook():
    if not bot or not RENDER_URL:
        return False
    try:
        bot.delete_webhook()
        time.sleep(1)
        url = RENDER_URL.rstrip('/') + '/webhook'
        print(f"Setting webhook to {url}")
        bot.set_webhook(url=url, drop_pending_updates=True)
        print("Webhook set OK")
        return True
    except Exception as e:
        print(f"Webhook setup failed: {e}")
        return False

def run_polling():
    if not bot or RENDER_URL:
        return
    while True:
        try:
            bot.delete_webhook(drop_pending_updates=True)
            time.sleep(2)
            bot.infinity_polling(timeout=10, long_polling_timeout=10, skip_pending=True)
        except Exception as e:
            if "409" in str(e):
                time.sleep(20)
            else:
                time.sleep(5)

if bot:
    if RENDER_URL:
        def init_webhook():
            time.sleep(3)
            setup_webhook()
        threading.Thread(target=init_webhook, daemon=True).start()
    else:
        threading.Thread(target=run_polling, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
