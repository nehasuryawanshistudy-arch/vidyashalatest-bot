import os, time, threading, io, csv, requests, math
from flask import Flask, request, abort
from PIL import Image, ImageDraw, ImageFont

app = Flask(__name__)

BRAND = {
    "YELLOW":(255,193,7), 
    "BLUE":(11,61,179), 
    "NAVY":(10,25,49), 
    "WHITE":(255,255,255), 
    "LIGHT_NAVY":(21,43,82),
    "GREEN":(46,213,115),
    "RED":(255,71,87),
    "GRAY":(116,125,140),
    "LIGHT_GRAY":(240,240,240)
}
SHEET_ID = "1921UYtW2eka524IVrcrJYkGyzoz_qUbPHJKCePdftlA"
SHEET_CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv"

BOT_TOKEN = os.getenv('BOT_TOKEN')
RENDER_URL = os.getenv('RENDER_EXTERNAL_URL')

QUESTION_TIME_LIMIT = 120  # 2 minutes autosubmit
CORRECT_MARK = 1.0
WRONG_MARK = -0.25

print(f"BOT_TOKEN present: {bool(BOT_TOKEN)} | RENDER_URL: {RENDER_URL} | TimeLimit: {QUESTION_TIME_LIMIT}s")

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

sessions, best_times, active_timers, timer_msg, result_msg = {}, {}, {}, {}, {}
best_overall = {"marks": -999, "time": 9999, "user": "None"}  # topper overall

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

def draw_correct_logo(draw, cx, cy, radius, tick_color=None):
    if tick_color is None:
        tick_color = BRAND["BLUE"]
    draw.ellipse((cx-radius, cy-radius, cx+radius, cy+radius), fill=BRAND["YELLOW"])
    x1 = cx - radius*0.35
    y1 = cy + radius*0.05
    x2 = cx - radius*0.05
    y2 = cy + radius*0.35
    x3 = cx + radius*0.45
    y3 = cy - radius*0.30
    w = max(8, int(radius*0.12))
    draw.line([(x1,y1),(x2,y2)], fill=tick_color, width=w, joint="round")
    draw.line([(x2,y2),(x3,y3)], fill=tick_color, width=w, joint="round")

def calculate_score(answers, times, quiz):
    correct = 0
    incorrect = 0
    left = 0
    for i, ans in enumerate(answers):
        if ans == -1:
            left += 1
        elif ans == quiz[i]['ans']:
            correct += 1
        else:
            incorrect += 1
    total_marks = correct * CORRECT_MARK + incorrect * WRONG_MARK
    total_time = sum(times)
    avg_time = total_time / len(quiz) if quiz else 0
    return {
        "correct": correct,
        "incorrect": incorrect,
        "left": left,
        "total_marks": total_marks,
        "total_time": total_time,
        "avg_time": avg_time
    }

def generate_launch_card():
    W,H = 1080,1350
    img = Image.new("RGB", (W,H), BRAND["NAVY"])
    draw = ImageDraw.Draw(img)
    for i in range(0, W, 200):
        for j in range(200, H, 200):
            draw.ellipse((i-20, j-20, i+20, j+20), fill=BRAND["LIGHT_NAVY"])
    cx,cy = W//2, 420
    draw_correct_logo(draw, cx, cy, 150)
    draw_correct_logo(draw, 100, 80, 35)
    draw.text((160,50), "VIDYASHALA", fill=BRAND["WHITE"], font=load_font(24, True))
    draw.text((160,80), "BANKING | INSURANCE | SSC", fill=BRAND["YELLOW"], font=load_font(16, True))
    draw.text((W//2, 700), "Take a Diagnostic Test", fill=BRAND["WHITE"], font=load_font(54, True), anchor="mm")
    draw.text((W//2, 770), "It's a time based test so be ready!", fill=BRAND["YELLOW"], font=load_font(30, True), anchor="mm")
    draw.rounded_rectangle((W//2-230, 1020-4, W//2+230, 1090+4), radius=32, fill=(0,0,0,60))
    draw.rounded_rectangle((W//2-220, 1020, W//2+220, 1090), radius=30, fill=BRAND["YELLOW"])
    draw.text((W//2, 1055), "TAP TO START ▶", fill=BRAND["NAVY"], font=load_font(32, True), anchor="mm")
    draw.text((W//2, 1220), "Trusted by 10k+ Banking Aspirants | +1 / -0.25", fill=BRAND["WHITE"], font=load_font(18, True), anchor="mm")
    buf = io.BytesIO(); img.save(buf, format="PNG"); buf.seek(0); return buf

def generate_question_card_clickable(q_idx, total, question, elapsed=0.0):
    W,H = 1080, 1150
    img = Image.new("RGB", (W,H), BRAND["NAVY"])
    draw = ImageDraw.Draw(img)
    for i in range(0, W, 180):
        for j in range(150, H, 180):
            draw.ellipse((i-15, j-15, i+15, j+15), fill=BRAND["LIGHT_NAVY"])
    draw.rounded_rectangle((50,35,270,95), radius=18, fill=BRAND["YELLOW"])
    draw.text((160,65), f"Q {q_idx+1} / {total}", fill=BRAND["NAVY"], font=load_font(22, True), anchor="mm")
    # Timer with countdown to 120s
    remaining = max(0, QUESTION_TIME_LIMIT - elapsed)
    mins = int(remaining // 60)
    secs = int(remaining % 60)
    timer_text = f"⏱ {mins:02d}:{secs:02d} LEFT"
    # Color changes when <30s
    timer_bg = BRAND["WHITE"] if remaining > 30 else (255,200,200)
    tw = draw.textlength(timer_text, font=load_font(20, True)) + 80
    x2 = W-50
    x1 = x2 - tw
    draw.rounded_rectangle((x1,35,x2,95), radius=18, fill=timer_bg)
    draw.ellipse((x1+18, 52, x1+34, 68), fill=BRAND["RED"] if remaining <=30 else (255,59,48))
    draw.text((x1+48,65), timer_text, fill=BRAND["NAVY"], font=load_font(20, True), anchor="lm")
    cx,cy = W//2, 250
    draw_correct_logo(draw, cx, cy, 85)
    bar_w = 400
    bar_h = 8
    bx1 = cx - bar_w//2
    by1 = cy + 110
    draw.rounded_rectangle((bx1, by1, bx1+bar_w, by1+bar_h), radius=4, fill=(255,255,255,40))
    progress = elapsed / QUESTION_TIME_LIMIT
    progress = min(progress, 1.0)
    fill_w = int(bar_w * progress)
    bar_color = BRAND["YELLOW"] if remaining>30 else BRAND["RED"]
    draw.rounded_rectangle((bx1, by1, bx1+fill_w, by1+bar_h), radius=4, fill=bar_color)
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
        draw.text((W//2+2, y+2), line, fill=(0,0,0,100), font=f_q, anchor="mm")
        draw.text((W//2, y), line, fill=BRAND["WHITE"], font=f_q, anchor="mm")
        y += 68
    draw.rounded_rectangle((W//2-200, y+40, W//2+200, y+85), radius=20, fill=BRAND["YELLOW"])
    draw.text((W//2, y+62), "👇 TAP YOUR ANSWER BELOW", fill=BRAND["NAVY"], font=load_font(20, True), anchor="mm")
    draw.text((W//2, H-40), f"Auto-submit in {mins:02d}:{secs:02d} | +1 / -0.25", fill=(255,255,255,120), font=load_font(16, True), anchor="mm")
    buf = io.BytesIO(); img.save(buf, format="PNG"); buf.seek(0); return buf

def generate_question_result_card(q_idx, quiz, answers, times, best_times):
    # Premium per-question result card
    W,H = 1080, 1350
    img = Image.new("RGB", (W,H), BRAND["NAVY"])
    draw = ImageDraw.Draw(img)
    for i in range(0, W, 200):
        for j in range(0, H, 200):
            draw.ellipse((i-15, j-15, i+15, j+15), fill=BRAND["LIGHT_NAVY"])
    # Header
    draw_correct_logo(draw, 90, 70, 32)
    draw.text((140, 45), "VIDYASHALA", fill=BRAND["WHITE"], font=load_font(20, True))
    draw.text((140, 70), f"Q{q_idx+1} ANALYSIS", fill=BRAND["YELLOW"], font=load_font(16, True))
    # Status badge
    ans = answers[q_idx]
    correct_ans = quiz[q_idx]['ans']
    if ans == -1:
        status = "LEFT"
        status_color = BRAND["GRAY"]
        status_text = "⏭ LEFT"
    elif ans == correct_ans:
        status = "CORRECT"
        status_color = BRAND["GREEN"]
        status_text = "✅ CORRECT"
    else:
        status = "WRONG"
        status_color = BRAND["RED"]
        status_text = "❌ WRONG"
    # Status pill top right
    draw.rounded_rectangle((W-250, 35, W-50, 95), radius=20, fill=status_color)
    draw.text((W-150, 65), status_text, fill=BRAND["WHITE"], font=load_font(20, True), anchor="mm")
    # Question box - white premium
    q_box_y = 130
    draw.rounded_rectangle((50, q_box_y, W-50, q_box_y+200), radius=20, fill=BRAND["WHITE"])
    f_q = load_font(28, True)
    q_text = quiz[q_idx]['q']
    # Wrap question
    words = q_text.split()
    lines = []
    cur = ""
    for w in words:
        test = cur + " " + w if cur else w
        if draw.textlength(test, font=f_q) < W-140:
            cur = test
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    y = q_box_y+30
    for line in lines[:3]:
        draw.text((80, y), line, fill=BRAND["NAVY"], font=f_q, anchor="lm")
        y+=45
    # Your answer vs Correct answer - two cards
    y_cards = q_box_y+230
    # Your answer card
    if ans == -1:
        your_opt_text = "Not Attempted"
        your_letter = "-"
    else:
        your_opt_text = quiz[q_idx]['opts'][ans] if ans < len(quiz[q_idx]['opts']) else "?"
        your_letter = chr(65+ans)
    correct_opt_text = quiz[q_idx]['opts'][correct_ans]
    correct_letter = chr(65+correct_ans)
    # Your answer
    draw.rounded_rectangle((50, y_cards, W//2-15, y_cards+120), radius=18, fill=status_color if ans!=-1 else BRAND["GRAY"])
    draw.text((70, y_cards+20), "YOUR ANSWER", fill=BRAND["WHITE"], font=load_font(14, True))
    draw.text((70, y_cards+50), f"{your_letter}. {your_opt_text[:28]}", fill=BRAND["WHITE"], font=load_font(22, True))
    draw.text((70, y_cards+85), f"Time: {times[q_idx]:.2f}s", fill=BRAND["WHITE"], font=load_font(16, True))
    # Correct answer
    draw.rounded_rectangle((W//2+15, y_cards, W-50, y_cards+120), radius=18, fill=BRAND["GREEN"])
    draw.text((W//2+35, y_cards+20), "CORRECT ANSWER", fill=BRAND["WHITE"], font=load_font(14, True))
    draw.text((W//2+35, y_cards+50), f"{correct_letter}. {correct_opt_text[:28]}", fill=BRAND["WHITE"], font=load_font(22, True))
    best = best_times.get(q_idx)
    if best:
        draw.text((W//2+35, y_cards+85), f"Topper: {best[0]:.2f}s by {best[1][:12]}", fill=BRAND["WHITE"], font=load_font(16, True))
    else:
        draw.text((W//2+35, y_cards+85), "You are Topper!", fill=BRAND["WHITE"], font=load_font(16, True))
    # Time comparison - premium table
    y_table = y_cards+150
    draw.rounded_rectangle((50, y_table, W-50, y_table+200), radius=18, fill=BRAND["WHITE"])
    draw.text((80, y_table+20), "⏱ TIME ANALYSIS", fill=BRAND["NAVY"], font=load_font(20, True))
    draw.line([(80, y_table+45),(W-80, y_table+45)], fill=BRAND["LIGHT_GRAY"], width=2)
    # Row
    draw.text((80, y_table+70), "Your Time:", fill=BRAND["GRAY"], font=load_font(18, True))
    draw.text((W-80, y_table+70), f"{times[q_idx]:.2f}s", fill=BRAND["NAVY"], font=load_font(18, True), anchor="rm")
    if best:
        draw.text((80, y_table+105), "Topper's Time:", fill=BRAND["GRAY"], font=load_font(18, True))
        draw.text((W-80, y_table+105), f"{best[0]:.2f}s by @{best[1]}", fill=BRAND["GREEN"], font=load_font(18, True), anchor="rm")
        diff = times[q_idx] - best[0]
        diff_text = f"{'+' if diff>0 else ''}{diff:.2f}s {'slower' if diff>0 else 'faster'} than topper" if ans!=-1 else "Not attempted"
        draw.text((80, y_table+140), "Difference:", fill=BRAND["GRAY"], font=load_font(18, True))
        draw.text((W-80, y_table+140), diff_text, fill=BRAND["RED"] if diff>0 else BRAND["GREEN"], font=load_font(18, True), anchor="rm")
    # Marks for this Q
    y_marks = y_table+230
    if ans == -1:
        marks_text = "0 (Left - No marks)"
        marks_color = BRAND["GRAY"]
    elif ans == correct_ans:
        marks_text = "+1.00"
        marks_color = BRAND["GREEN"]
    else:
        marks_text = "-0.25"
        marks_color = BRAND["RED"]
    draw.rounded_rectangle((50, y_marks, W-50, y_marks+80), radius=18, fill=marks_color)
    draw.text((W//2, y_marks+40), f"Marks for this Q: {marks_text}", fill=BRAND["WHITE"], font=load_font(26, True), anchor="mm")
    # Footer
    draw.text((W//2, H-40), "Use tabs below to view other questions", fill=(255,255,255,100), font=load_font(16, True), anchor="mm")
    buf = io.BytesIO(); img.save(buf, format="PNG"); buf.seek(0); return buf

def generate_final_summary_card(uid, quiz, answers, times, best_times, best_overall):
    W,H = 1080, 1350
    img = Image.new("RGB", (W,H), BRAND["NAVY"])
    draw = ImageDraw.Draw(img)
    for i in range(0, W, 200):
        for j in range(0, H, 200):
            draw.ellipse((i-20, j-20, i+20, j+20), fill=BRAND["LIGHT_NAVY"])
    # Header logo
    draw_correct_logo(draw, 90, 70, 32)
    draw.text((140, 45), "VIDYASHALA", fill=BRAND["WHITE"], font=load_font(20, True))
    draw.text((140, 70), "DIAGNOSTIC REPORT", fill=BRAND["YELLOW"], font=load_font(16, True))
    # Title
    draw.text((W//2, 140), "FINAL SCORE CARD", fill=BRAND["WHITE"], font=load_font(38, True), anchor="mm")
    draw.text((W//2, 175), "Premium Performance Analysis", fill=BRAND["YELLOW"], font=load_font(18, True), anchor="mm")
    score = calculate_score(answers, times, quiz)
    # Big marks circle
    cx,cy = W//2, 280
    draw.ellipse((cx-90, cy-90, cx+90, cy+90), fill=BRAND["YELLOW"])
    draw.text((cx, cy-15), f"{score['total_marks']:.2f}", fill=BRAND["NAVY"], font=load_font(48, True), anchor="mm")
    draw.text((cx, cy+25), f"/ {len(quiz)}", fill=BRAND["NAVY"], font=load_font(20, True), anchor="mm")
    # Stats row - 3 boxes
    y_stats = 380
    # Correct
    draw.rounded_rectangle((50, y_stats, 350, y_stats+110), radius=18, fill=BRAND["GREEN"])
    draw.text((200, y_stats+25), "✅ CORRECT", fill=BRAND["WHITE"], font=load_font(16, True), anchor="mm")
    draw.text((200, y_stats+65), str(score['correct']), fill=BRAND["WHITE"], font=load_font(36, True), anchor="mm")
    # Incorrect
    draw.rounded_rectangle((390, y_stats, 690, y_stats+110), radius=18, fill=BRAND["RED"])
    draw.text((540, y_stats+25), "❌ WRONG", fill=BRAND["WHITE"], font=load_font(16, True), anchor="mm")
    draw.text((540, y_stats+65), str(score['incorrect']), fill=BRAND["WHITE"], font=load_font(36, True), anchor="mm")
    # Left
    draw.rounded_rectangle((730, y_stats, 1030, y_stats+110), radius=18, fill=BRAND["GRAY"])
    draw.text((880, y_stats+25), "⏭ LEFT", fill=BRAND["WHITE"], font=load_font(16, True), anchor="mm")
    draw.text((880, y_stats+65), str(score['left']), fill=BRAND["WHITE"], font=load_font(36, True), anchor="mm")
    # Marks breakdown
    y_break = y_stats+130
    draw.rounded_rectangle((50, y_break, W-50, y_break+100), radius=18, fill=BRAND["WHITE"])
    draw.text((80, y_break+20), "📊 MARKS BREAKDOWN", fill=BRAND["NAVY"], font=load_font(18, True))
    draw.text((80, y_break+50), f"Correct: {score['correct']} x 1.0 = +{score['correct']*1.0:.2f}", fill=BRAND["GREEN"], font=load_font(16, True))
    draw.text((80, y_break+75), f"Wrong: {score['incorrect']} x -0.25 = {score['incorrect']*-0.25:.2f}", fill=BRAND["RED"], font=load_font(16, True))
    draw.text((W-80, y_break+50), f"Total: {score['total_marks']:.2f}", fill=BRAND["NAVY"], font=load_font(22, True), anchor="rm")
    # Time analysis
    y_time = y_break+120
    draw.rounded_rectangle((50, y_time, W-50, y_time+140), radius=18, fill=BRAND["WHITE"])
    draw.text((80, y_time+15), "⏱ TIME ANALYSIS", fill=BRAND["NAVY"], font=load_font(18, True))
    draw.text((80, y_time+45), f"Total Time: {score['total_time']:.2f}s", fill=BRAND["NAVY"], font=load_font(16, True))
    draw.text((80, y_time+70), f"Avg per Q: {score['avg_time']:.2f}s", fill=BRAND["NAVY"], font=load_font(16, True))
    # Topper comparison
    topper_total_time = sum([t for t,_ in best_times.values()]) if best_times else score['total_time']
    topper_avg = topper_total_time / len(quiz) if quiz else 0
    draw.text((80, y_time+95), f"Topper Avg: {topper_avg:.2f}s | Topper Total: {topper_total_time:.2f}s", fill=BRAND["GRAY"], font=load_font(14, True))
    # Comparison vs topper overall
    y_comp = y_time+160
    draw.rounded_rectangle((50, y_comp, W-50, y_comp+160), radius=18, fill=BRAND["LIGHT_NAVY"])
    draw.text((80, y_comp+15), "🏆 COMPARISON WITH TOPPER", fill=BRAND["YELLOW"], font=load_font(18, True))
    # Overall topper
    topper_marks = best_overall["marks"]
    topper_user = best_overall["user"]
    draw.text((80, y_comp+45), f"Topper: @{topper_user} - {topper_marks:.2f} marks", fill=BRAND["WHITE"], font=load_font(16, True))
    diff_marks = score['total_marks'] - topper_marks
    diff_text = f"You are {abs(diff_marks):.2f} marks {'behind' if diff_marks<0 else 'ahead of'} topper"
    draw.text((80, y_comp+70), diff_text, fill=BRAND["YELLOW"], font=load_font(16, True))
    # Speed comparison
    if score['avg_time'] < topper_avg:
        speed_text = f"⚡ You are {topper_avg - score['avg_time']:.2f}s faster per Q than topper avg!"
    else:
        speed_text = f"🐢 You are {score['avg_time'] - topper_avg:.2f}s slower per Q than topper avg"
    draw.text((80, y_comp+95), speed_text, fill=BRAND["WHITE"], font=load_font(16, True))
    # Accuracy
    acc = (score['correct']/len(quiz)*100) if quiz else 0
    draw.text((80, y_comp+120), f"Accuracy: {acc:.1f}% ({score['correct']}/{len(quiz)})", fill=BRAND["WHITE"], font=load_font(16, True))
    # Footer message based on score
    y_footer = y_comp+190
    if score['total_marks'] >= len(quiz)*0.8:
        msg = "🌟 Outstanding! Banking Topper Material!"
        color = BRAND["GREEN"]
    elif score['total_marks'] >= len(quiz)*0.5:
        msg = "💪 Good Job! Keep Practicing!"
        color = BRAND["YELLOW"]
    else:
        msg = "📚 Need More Practice - You Got This!"
        color = BRAND["RED"]
    draw.rounded_rectangle((50, y_footer, W-50, y_footer+70), radius=18, fill=color)
    draw.text((W//2, y_footer+35), msg, fill=BRAND["WHITE"] if color!=BRAND["YELLOW"] else BRAND["NAVY"], font=load_font(22, True), anchor="mm")
    draw.text((W//2, H-30), "Tap tabs below for Q-wise analysis | +1 Correct / -0.25 Wrong / 0 Left", fill=(255,255,255,100), font=load_font(14, True), anchor="mm")
    buf = io.BytesIO(); img.save(buf, format="PNG"); buf.seek(0); return buf

def get_q_caption(q_idx, elapsed, total):
    remaining = max(0, QUESTION_TIME_LIMIT - elapsed)
    mins = int(remaining // 60)
    secs = int(remaining % 60)
    return f"Q{q_idx+1}/{total} | ⏱ {mins:02d}:{secs:02d} left | Auto-submit in 2min | +1 / -0.25"

def build_clickable_markup(q_idx, opts):
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
    markup = InlineKeyboardMarkup(row_width=1)
    emojis = ["🅰️","🅱️","🅲","🅳","🅴"]
    for i,opt in enumerate(opts):
        if not opt: continue
        btn_text = f"{emojis[i]}  {opt}"
        markup.add(InlineKeyboardButton(btn_text, callback_data=f"ans_{q_idx}_{i}"))
    return markup

def build_result_tabs(quiz_len, current_idx=None):
    # Premium tabs: Q1 Q2 Q3... + SUMMARY
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
    markup = InlineKeyboardMarkup(row_width=5)
    buttons = []
    for i in range(quiz_len):
        label = f"Q{i+1}"
        if current_idx == i:
            label = f"•{label}•"
        buttons.append(InlineKeyboardButton(label, callback_data=f"res_q_{i}"))
    # Add in rows of 5
    for i in range(0, len(buttons), 5):
        markup.row(*buttons[i:i+5])
    markup.row(InlineKeyboardButton("📊 FINAL SUMMARY", callback_data="res_summary"))
    markup.row(InlineKeyboardButton("🔄 Retake Test", callback_data="retake"))
    return markup

def live_updater(uid, total):
    while active_timers.get(uid):
        try:
            cur = sessions[uid]['cur']
            elapsed = time.time() - sessions[uid]['start']
            chat_id, msg_id = timer_msg.get(uid,(None,None))
            if not chat_id: break
            # AUTOSUBMIT after 2 minutes
            if elapsed >= QUESTION_TIME_LIMIT:
                # Mark as left
                print(f"Auto-submit Q{cur} for {uid} after {QUESTION_TIME_LIMIT}s")
                active_timers[uid] = False
                sessions[uid]['answers'].append(-1)
                sessions[uid]['times'].append(float(QUESTION_TIME_LIMIT))
                try:
                    if bot:
                        bot.edit_message_caption(caption=f"⏰ TIME UP! Q{cur+1} marked as LEFT (0 marks) - Auto-submitted after 2min", chat_id=chat_id, message_id=msg_id)
                except: pass
                time.sleep(1)
                send_next(uid, cur+1)
                break
            quiz = sessions[uid].get('quiz') or get_quiz()
            card = generate_question_card_clickable(cur, total, quiz[cur]['q'], elapsed)
            markup = build_clickable_markup(cur, quiz[cur]['opts'])
            if bot:
                from telebot.types import InputMediaPhoto
                bot.edit_message_media(media=InputMediaPhoto(card, caption=get_q_caption(cur, elapsed, total)), chat_id=chat_id, message_id=msg_id, reply_markup=markup)
        except Exception as e:
            try:
                # Fallback to caption edit
                if bot and 'markup' in locals():
                    bot.edit_message_caption(caption=get_q_caption(cur, elapsed, total), chat_id=chat_id, message_id=msg_id, reply_markup=markup)
            except: pass
        time.sleep(1.0)

def send_question(uid, q_idx):
    if not bot: return
    quiz = sessions[uid].get('quiz') or get_quiz()
    sessions[uid]['quiz'] = quiz
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
    sessions[uid] = {'cur':0,'answers':[],'times':[],'start':0, 'quiz':quiz, 'username': 'user'}
    txt=f"DIAGNOSTIC READY ({len(quiz)} Qs)\n+1 Correct, -0.25 Wrong, 0 Left\n2min per Q auto-submit"
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
    markup=InlineKeyboardMarkup().add(InlineKeyboardButton("▶️ TAP TO START THE TEST", callback_data="start_test"))
    card=generate_launch_card()
    bot.send_photo(uid, card, caption=txt, reply_markup=markup)

def send_next(uid, next_idx):
    time.sleep(1.2)
    sess = sessions.get(uid)
    if not sess:
        return
    quiz = sess.get('quiz') or get_quiz()
    if next_idx < len(quiz):
        send_question(uid, next_idx)
    else:
        send_final_results(uid)

def send_final_results(uid):
    sess = sessions.get(uid)
    if not sess: return
    quiz = sess.get('quiz') or get_quiz()
    answers = sess['answers']
    times = sess['times']
    # Ensure lengths match
    while len(answers) < len(quiz):
        answers.append(-1)
        times.append(QUESTION_TIME_LIMIT)
    score = calculate_score(answers, times, quiz)
    # Update best overall
    global best_overall
    if score['total_marks'] > best_overall['marks'] or (score['total_marks'] == best_overall['marks'] and score['total_time'] < best_overall['time']):
        best_overall = {"marks": score['total_marks'], "time": score['total_time'], "user": sess.get('username','user')}
    # Generate premium summary card
    card = generate_final_summary_card(uid, quiz, answers, times, best_times, best_overall)
    markup = build_result_tabs(len(quiz), current_idx=None)
    try:
        msg = bot.send_photo(uid, card, caption=f"✅ TEST COMPLETED! Final: {score['total_marks']:.2f}/{len(quiz)} | Correct:{score['correct']} Wrong:{score['incorrect']} Left:{score['left']} | Time:{score['total_time']:.1f}s", reply_markup=markup)
        result_msg[uid] = (msg.chat.id, msg.message_id, quiz, answers, times)
    except Exception as e:
        print(f"Send final results error: {e}")
        # Fallback text
        bot.send_message(uid, f"Score: {score['total_marks']:.2f}/{len(quiz)} Correct:{score['correct']} Wrong:{score['incorrect']} Left:{score['left']}")

if bot:
    @bot.message_handler(commands=['start'])
    def handle_start(message):
        uid=message.from_user.id
        username = message.from_user.username or message.from_user.first_name
        quiz = get_quiz()
        sessions[uid] = {'cur':0,'answers':[],'times':[],'start':0, 'quiz':quiz, 'username': username}
        if "quiz" in message.text:
            send_start_screen(uid)
        else:
            bot.send_message(uid,"Go to @vidyashalatest and tap Take Diagnostic Test")

    @bot.message_handler(commands=['quiz'])
    def post_card(message):
        from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
        username=bot.get_me().username
        markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🎯 Take Diagnostic Test", url=f"https://t.me/{username}?start=quiz"))
        caption="Take a Diagnostic Test\nIt's a time based test so be ready!\n+1 / -0.25 / 2min auto-submit"
        card=generate_launch_card()
        try:
            bot.send_photo("@vidyashalatest", card, caption=caption, reply_markup=markup)
            bot.reply_to(message, "Posted to @vidyashalatest - Premium version ✅")
        except Exception as e:
            bot.reply_to(message, f"Make bot admin in channel: {e}")

    @bot.callback_query_handler(func=lambda c: True)
    def handle_all(call):
        uid=call.from_user.id
        data = call.data
        if data=="start_test":
            send_question(uid,0)
        elif data.startswith("ans_"):
            _,q_idx,opt_idx=data.split("_"); q_idx,opt_idx=int(q_idx),int(opt_idx)
            if uid not in sessions or sessions[uid]['cur']!=q_idx: return
            active_timers[uid]=False
            elapsed=time.time()-sessions[uid]['start']
            sessions[uid]['answers'].append(opt_idx); sessions[uid]['times'].append(elapsed)
            quiz=sessions[uid].get('quiz') or get_quiz()
            if opt_idx==quiz[q_idx]['ans']:
                cur=best_times.get(q_idx)
                if not cur or elapsed<cur[0]:
                    best_times[q_idx]=(elapsed, call.from_user.username or call.from_user.first_name)
            result="✅ CORRECT! +1" if opt_idx==quiz[q_idx]['ans'] else f"❌ WRONG! -0.25 | Ans: {chr(65+quiz[q_idx]['ans'])}"
            try:
                if bot:
                    bot.edit_message_caption(caption=result, chat_id=call.message.chat.id, message_id=call.message.message_id)
            except: pass
            if bot:
                bot.answer_callback_query(call.id, result)
            threading.Thread(target=send_next, args=(uid,q_idx+1), daemon=True).start()
        elif data.startswith("res_q_"):
            # Premium Q-wise tab
            try:
                q_idx = int(data.split("_")[-1])
                if uid not in result_msg: return
                chat_id, msg_id, quiz, answers, times = result_msg[uid]
                card = generate_question_result_card(q_idx, quiz, answers, times, best_times)
                markup = build_result_tabs(len(quiz), current_idx=q_idx)
                if bot:
                    from telebot.types import InputMediaPhoto
                    bot.edit_message_media(media=InputMediaPhoto(card, caption=f"Q{q_idx+1} Analysis - Tap tabs below"), chat_id=chat_id, message_id=msg_id, reply_markup=markup)
                bot.answer_callback_query(call.id, f"Q{q_idx+1} details")
            except Exception as e:
                print(f"res_q error: {e}")
        elif data=="res_summary":
            try:
                if uid not in result_msg: return
                chat_id, msg_id, quiz, answers, times = result_msg[uid]
                card = generate_final_summary_card(uid, quiz, answers, times, best_times, best_overall)
                markup = build_result_tabs(len(quiz), current_idx=None)
                if bot:
                    from telebot.types import InputMediaPhoto
                    score = calculate_score(answers, times, quiz)
                    bot.edit_message_media(media=InputMediaPhoto(card, caption=f"Final Summary: {score['total_marks']:.2f}/{len(quiz)} | {score['correct']}C {score['incorrect']}W {score['left']}L"), chat_id=chat_id, message_id=msg_id, reply_markup=markup)
                bot.answer_callback_query(call.id, "Summary")
            except Exception as e:
                print(f"res_summary error: {e}")
        elif data=="retake":
            quiz = get_quiz()
            sessions[uid] = {'cur':0,'answers':[],'times':[],'start':0, 'quiz':quiz, 'username': call.from_user.username or call.from_user.first_name}
            bot.answer_callback_query(call.id, "Starting new test...")
            send_start_screen(uid)

@app.route('/')
def home():
    mode = "webhook" if RENDER_URL else "polling"
    return f"Vidyashala bot OK - PREMIUM +1/-0.25 + 2min auto + tabs - mode:{mode}"

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
