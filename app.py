import os, time, threading, io, csv, requests, json, math
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
    "LIGHT_GRAY":(240,240,240),
    "DARK":(15,23,42)
}
SHEET_ID = "1921UYtW2eka524IVrcrJYkGyzoz_qUbPHJKCePdftlA"
SHEET_CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv"

BOT_TOKEN = os.getenv('BOT_TOKEN')
RENDER_URL = os.getenv('RENDER_EXTERNAL_URL')

TOTAL_QUIZ_TIME = 7 * 60  # 7 minutes combined as per new spec
CORRECT_MARK = 1.0
WRONG_MARK = -0.25
SESSION_FILE = "vidyashala_sessions.json"

LOGO_PATHS = [
    "/mnt/data/Blue_Square_Root_Emblem",
    "/mnt/data/logo.jpg",
    "/mnt/data/logo.png",
    "/mnt/data/vidyashala_logo.jpg",
    "logo.jpg",
    "Blue_Square_Root_Emblem",
    "vidyashala_logo.jpg"
]

print(f"BOT_TOKEN present: {bool(BOT_TOKEN)} | RENDER_URL: {RENDER_URL} | TotalTime: {TOTAL_QUIZ_TIME}s")

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

sessions = {}  # uid -> {quiz, answers, q_times, start_time, current_q, last_entry, username, finished, msg_id}
best_times = {}
best_overall = {"marks": -999, "time": 9999, "user": "None"}
active_overall_timers = {}  # uid -> bool
result_msg = {}  # uid -> (chat_id, msg_id, quiz, answers, times)

def load_logo_image(size):
    """Load real Vidyashala logo from uploaded file, resize to size x size"""
    for path in LOGO_PATHS:
        try:
            if os.path.exists(path):
                img = Image.open(path).convert("RGBA")
                # Make circular mask for clean look
                img = img.resize((size, size), Image.LANCZOS)
                return img
        except Exception as e:
            print(f"Logo load fail {path}: {e}")
            continue
    # Fallback: draw yellow circle with blue sqrt
    print("Logo file not found, using fallback drawn logo")
    img = Image.new("RGBA", (size, size), (0,0,0,0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((0,0,size,size), fill=BRAND["YELLOW"])
    # Draw sqrt
    cx,cy = size//2, size//2
    r = size//2
    x1 = cx - r*0.35
    y1 = cy + r*0.05
    x2 = cx - r*0.05
    y2 = cy + r*0.35
    x3 = cx + r*0.45
    y3 = cy - r*0.30
    w = max(6, int(r*0.14))
    draw.line([(x1,y1),(x2,y2)], fill=BRAND["BLUE"], width=w, joint="round")
    draw.line([(x2,y2),(x3,y3)], fill=BRAND["BLUE"], width=w, joint="round")
    return img

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

def save_sessions():
    try:
        # Convert sessions to serializable (remove non-serializable)
        data = {}
        for uid, sess in sessions.items():
            # Only save if not finished and within time
            if sess.get('finished'):
                continue
            data[str(uid)] = {
                'quiz': sess.get('quiz'),
                'answers': sess.get('answers'),
                'q_times': sess.get('q_times'),
                'start_time': sess.get('start_time'),
                'current_q': sess.get('current_q'),
                'username': sess.get('username'),
                'finished': sess.get('finished', False)
            }
        with open(SESSION_FILE, 'w') as f:
            json.dump({'sessions': data, 'best_times': best_times, 'best_overall': best_overall}, f)
    except Exception as e:
        print(f"Save sessions error: {e}")

def load_sessions():
    global sessions, best_times, best_overall
    try:
        if os.path.exists(SESSION_FILE):
            with open(SESSION_FILE, 'r') as f:
                data = json.load(f)
                # Restore sessions
                for uid_str, sess in data.get('sessions', {}).items():
                    try:
                        uid = int(uid_str)
                        # Check if still valid (within 24h and not expired)
                        if time.time() - sess.get('start_time', 0) < 24*3600:
                            sessions[uid] = sess
                            # Ensure q_times exists
                            if 'q_times' not in sess:
                                sess['q_times'] = [0]*len(sess.get('quiz',[]))
                            if 'last_entry' not in sess:
                                sess['last_entry'] = time.time()
                    except: pass
                best_times.update(data.get('best_times', {}))
                best_overall.update(data.get('best_overall', best_overall))
            print(f"Loaded {len(sessions)} sessions from file")
    except Exception as e:
        print(f"Load sessions error: {e}")

load_sessions()

def calculate_score(answers, q_times, quiz):
    correct = 0
    incorrect = 0
    left = 0
    for i, ans in enumerate(answers):
        if ans is None or ans == -1:
            left += 1
        elif ans == quiz[i]['ans']:
            correct += 1
        else:
            incorrect += 1
    total_marks = correct * CORRECT_MARK + incorrect * WRONG_MARK
    total_time = sum(q_times) if q_times else 0
    # If total_time is 0, estimate from overall
    avg_time = total_time / len(quiz) if quiz and total_time>0 else 0
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
    # Subtle dots
    for i in range(0, W, 200):
        for j in range(200, H, 200):
            draw.ellipse((i-20, j-20, i+20, j+20), fill=BRAND["LIGHT_NAVY"])
    # Real logo centered - large
    logo = load_logo_image(320)
    cx,cy = W//2, 420
    # Paste logo with its own shape (circular)
    img.paste(logo, (cx-160, cy-160), logo)
    # Small top left logo
    small_logo = load_logo_image(70)
    img.paste(small_logo, (50, 35), small_logo)
    draw.text((135,50), "VIDYASHALA", fill=BRAND["WHITE"], font=load_font(24, True))
    draw.text((135,80), "BANKING | INSURANCE | SSC", fill=BRAND["YELLOW"], font=load_font(16, True))
    draw.text((W//2, 700), "Take a Diagnostic Test", fill=BRAND["WHITE"], font=load_font(54, True), anchor="mm")
    draw.text((W//2, 770), "7 Minutes • 5 Questions • +1 / -0.25", fill=BRAND["YELLOW"], font=load_font(26, True), anchor="mm")
    draw.rounded_rectangle((W//2-230, 1020-4, W//2+230, 1090+4), radius=32, fill=(0,0,0,60))
    draw.rounded_rectangle((W//2-220, 1020, W//2+220, 1090), radius=30, fill=BRAND["YELLOW"])
    draw.text((W//2, 1055), "TAP TO START ▶", fill=BRAND["NAVY"], font=load_font(32, True), anchor="mm")
    draw.text((W//2, 1200), "Resume Supported • Auto-save Every Second", fill=BRAND["WHITE"], font=load_font(16, True), anchor="mm")
    draw.text((W//2, 1230), "Trusted by 10k+ Aspirants", fill=(255,255,255,150), font=load_font(16, True), anchor="mm")
    buf = io.BytesIO(); img.save(buf, format="PNG"); buf.seek(0); return buf

def generate_question_card_static(q_idx, total, question):
    """STATIC card - NO TIMER INSIDE - to avoid distraction"""
    W,H = 1080, 950
    img = Image.new("RGB", (W,H), BRAND["NAVY"])
    draw = ImageDraw.Draw(img)
    # Subtle background
    for i in range(0, W, 180):
        for j in range(120, H, 180):
            draw.ellipse((i-15, j-15, i+15, j+15), fill=BRAND["LIGHT_NAVY"])
    # Top bar - Q badge + small real logo
    small_logo = load_logo_image(60)
    img.paste(small_logo, (50, 30), small_logo)
    draw.rounded_rectangle((130,35,320,85), radius=16, fill=BRAND["YELLOW"])
    draw.text((225,60), f"Q {q_idx+1} / {total}", fill=BRAND["NAVY"], font=load_font(20, True), anchor="mm")
    draw.text((W-50, 60), "BANKING | INSURANCE", fill=BRAND["YELLOW"], font=load_font(14, True), anchor="rm")
    # Question box - premium white
    q_box_y = 120
    draw.rounded_rectangle((50, q_box_y, W-50, q_box_y+700), radius=24, fill=BRAND["WHITE"])
    # Question text - wrap
    f_q = load_font(36, True)
    words = question.split()
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
    y = q_box_y+40
    if len(lines) > 6:
        lines = lines[:6]
        lines[-1] = lines[-1][:50] + "..."
    for line in lines:
        draw.text((80, y), line, fill=BRAND["NAVY"], font=f_q, anchor="lm")
        y += 58
    # Bottom branding inside card
    draw.text((W//2, H-30), "VIDYASHALA • Focus Mode - Timer in Caption Only", fill=(10,25,49,100), font=load_font(14, True), anchor="mm")
    buf = io.BytesIO(); img.save(buf, format="PNG"); buf.seek(0); return buf

def build_quiz_caption(uid):
    sess = sessions.get(uid)
    if not sess:
        return "Quiz not found"
    quiz = sess['quiz']
    q_idx = sess['current_q']
    answers = sess['answers']
    q_times = sess['q_times']
    start_time = sess['start_time']
    overall_elapsed = time.time() - start_time
    remaining = max(0, TOTAL_QUIZ_TIME - overall_elapsed)
    mins = int(remaining // 60)
    secs = int(remaining % 60)
    mins_e = int(overall_elapsed // 60)
    secs_e = int(overall_elapsed % 60)
    # Progress bar - text only
    progress = overall_elapsed / TOTAL_QUIZ_TIME
    progress = min(progress, 1.0)
    filled = int(progress*12)
    empty = 12 - filled
    bar = "█"*filled + "░"*empty
    # Answered count
    answered = sum(1 for a in answers if a is not None and a != -1)
    # Time per current Q
    current_q_time = time.time() - sess.get('last_entry', time.time())
    # Caption - ONLY timer and progress changes here, not image
    caption = f"🧭 Q{q_idx+1}/{len(quiz)} | ⏱ {mins:02d}:{secs:02d} left (Total {TOTAL_QUIZ_TIME//60}:00)\n"
    caption += f"{bar} {int(progress*100)}% | Elapsed: {mins_e:02d}:{secs_e:02d}\n"
    caption += f"✅ Answered: {answered}/{len(quiz)} | Current Q Time: {int(current_q_time)}s\n"
    caption += f"📌 +1 Correct, -0.25 Wrong, 0 Left | Auto-submit at 00:00\n"
    # Show if current Q answered
    if answers[q_idx] is not None and answers[q_idx] != -1:
        opt = quiz[q_idx]['opts'][answers[q_idx]]
        caption += f"✏️ Your Ans Q{q_idx+1}: {chr(65+answers[q_idx])}. {opt[:30]}\n"
    caption += "👇 Use palette to jump, select option below"
    return caption

def build_quiz_keyboard(uid):
    sess = sessions.get(uid)
    if not sess:
        return None
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
    quiz = sess['quiz']
    answers = sess['answers']
    current_q = sess['current_q']
    q_idx = current_q
    markup = InlineKeyboardMarkup(row_width=5)
    # Row 1: Question palette - shows status
    palette = []
    for i in range(len(quiz)):
        if i == current_q:
            label = f"•Q{i+1}•"
        elif answers[i] is not None and answers[i] != -1:
            label = f"Q{i+1}✅"
        else:
            label = f"Q{i+1}"
        palette.append(InlineKeyboardButton(label, callback_data=f"nav_q_{i}"))
    # Add palette in rows of 5
    for i in range(0, len(palette), 5):
        markup.row(*palette[i:i+5])
    # Row 2: Navigation Back / Next
    nav_row = []
    if current_q > 0:
        nav_row.append(InlineKeyboardButton("◀️ Back", callback_data="nav_prev"))
    if current_q < len(quiz)-1:
        nav_row.append(InlineKeyboardButton("Next ▶️", callback_data="nav_next"))
    if nav_row:
        markup.row(*nav_row)
    # Rows 3-7: Options - 5 clickable options
    emojis = ["🅰️","🅱️","🅲","🅳","🅴"]
    for i, opt in enumerate(quiz[q_idx]['opts']):
        if not opt:
            continue
        is_selected = answers[q_idx] == i
        prefix = "✅ " if is_selected else ""
        btn_text = f"{prefix}{emojis[i]} {opt}"
        # Truncate if too long for button
        if len(btn_text) > 30:
            btn_text = btn_text[:27] + "..."
        markup.row(InlineKeyboardButton(btn_text, callback_data=f"ans_{q_idx}_{i}"))
    # Last row: Submit
    markup.row(InlineKeyboardButton("📤 Submit Test", callback_data="submit_test"))
    return markup

def generate_question_result_card(q_idx, quiz, answers, q_times, best_times):
    W,H = 1080, 1350
    img = Image.new("RGB", (W,H), BRAND["NAVY"])
    draw = ImageDraw.Draw(img)
    for i in range(0, W, 200):
        for j in range(0, H, 200):
            draw.ellipse((i-15, j-15, i+15, j+15), fill=BRAND["LIGHT_NAVY"])
    # Real logo
    small_logo = load_logo_image(64)
    img.paste(small_logo, (50, 35), small_logo)
    draw.text((125, 45), "VIDYASHALA", fill=BRAND["WHITE"], font=load_font(20, True))
    draw.text((125, 70), f"Q{q_idx+1} ANALYSIS", fill=BRAND["YELLOW"], font=load_font(16, True))
    ans = answers[q_idx] if q_idx < len(answers) else None
    correct_ans = quiz[q_idx]['ans']
    if ans is None or ans == -1:
        status_text = "⏭ LEFT"
        status_color = BRAND["GRAY"]
    elif ans == correct_ans:
        status_text = "✅ CORRECT"
        status_color = BRAND["GREEN"]
    else:
        status_text = "❌ WRONG"
        status_color = BRAND["RED"]
    draw.rounded_rectangle((W-250, 35, W-50, 95), radius=20, fill=status_color)
    draw.text((W-150, 65), status_text, fill=BRAND["WHITE"], font=load_font(20, True), anchor="mm")
    q_box_y = 120
    draw.rounded_rectangle((50, q_box_y, W-50, q_box_y+180), radius=20, fill=BRAND["WHITE"])
    f_q = load_font(26, True)
    q_text = quiz[q_idx]['q']
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
    y = q_box_y+25
    for line in lines[:3]:
        draw.text((80, y), line, fill=BRAND["NAVY"], font=f_q, anchor="lm")
        y+=40
    y_cards = q_box_y+210
    if ans is None or ans == -1:
        your_opt_text = "Not Attempted"
        your_letter = "-"
    else:
        your_opt_text = quiz[q_idx]['opts'][ans] if ans < len(quiz[q_idx]['opts']) else "?"
        your_letter = chr(65+ans)
    correct_opt_text = quiz[q_idx]['opts'][correct_ans]
    correct_letter = chr(65+correct_ans)
    draw.rounded_rectangle((50, y_cards, W//2-15, y_cards+120), radius=18, fill=status_color)
    draw.text((70, y_cards+20), "YOUR ANSWER", fill=BRAND["WHITE"], font=load_font(14, True))
    draw.text((70, y_cards+50), f"{your_letter}. {your_opt_text[:28]}", fill=BRAND["WHITE"], font=load_font(20, True))
    draw.text((70, y_cards+85), f"Time: {q_times[q_idx]:.1f}s", fill=BRAND["WHITE"], font=load_font(16, True))
    draw.rounded_rectangle((W//2+15, y_cards, W-50, y_cards+120), radius=18, fill=BRAND["GREEN"])
    draw.text((W//2+35, y_cards+20), "CORRECT ANSWER", fill=BRAND["WHITE"], font=load_font(14, True))
    draw.text((W//2+35, y_cards+50), f"{correct_letter}. {correct_opt_text[:28]}", fill=BRAND["WHITE"], font=load_font(20, True))
    best = best_times.get(q_idx)
    if best:
        draw.text((W//2+35, y_cards+85), f"Topper: {best[0]:.1f}s by {best[1][:12]}", fill=BRAND["WHITE"], font=load_font(14, True))
    else:
        draw.text((W//2+35, y_cards+85), "You are Topper!", fill=BRAND["WHITE"], font=load_font(14, True))
    y_table = y_cards+150
    draw.rounded_rectangle((50, y_table, W-50, y_table+200), radius=18, fill=BRAND["WHITE"])
    draw.text((80, y_table+20), "⏱ TIME ANALYSIS", fill=BRAND["NAVY"], font=load_font(18, True))
    draw.line([(80, y_table+45),(W-80, y_table+45)], fill=BRAND["LIGHT_GRAY"], width=2)
    draw.text((80, y_table+70), "Your Time:", fill=BRAND["GRAY"], font=load_font(16, True))
    draw.text((W-80, y_table+70), f"{q_times[q_idx]:.1f}s", fill=BRAND["NAVY"], font=load_font(16, True), anchor="rm")
    if best:
        draw.text((80, y_table+105), "Topper's Time:", fill=BRAND["GRAY"], font=load_font(16, True))
        draw.text((W-80, y_table+105), f"{best[0]:.1f}s by @{best[1]}", fill=BRAND["GREEN"], font=load_font(16, True), anchor="rm")
        diff = q_times[q_idx] - best[0]
        diff_text = f"{'+' if diff>0 else ''}{diff:.1f}s {'slower' if diff>0 else 'faster'}" if ans not in [None, -1] else "Not attempted"
        draw.text((80, y_table+140), "Difference:", fill=BRAND["GRAY"], font=load_font(16, True))
        draw.text((W-80, y_table+140), diff_text, fill=BRAND["RED"] if diff>0 else BRAND["GREEN"], font=load_font(16, True), anchor="rm")
    y_marks = y_table+230
    if ans is None or ans == -1:
        marks_text = "0 (Left)"
        marks_color = BRAND["GRAY"]
    elif ans == correct_ans:
        marks_text = "+1.00"
        marks_color = BRAND["GREEN"]
    else:
        marks_text = "-0.25"
        marks_color = BRAND["RED"]
    draw.rounded_rectangle((50, y_marks, W-50, y_marks+80), radius=18, fill=marks_color)
    draw.text((W//2, y_marks+40), f"Marks: {marks_text}", fill=BRAND["WHITE"], font=load_font(26, True), anchor="mm")
    draw.text((W//2, H-40), "Use tabs below for other Qs", fill=(255,255,255,100), font=load_font(14, True), anchor="mm")
    buf = io.BytesIO(); img.save(buf, format="PNG"); buf.seek(0); return buf

def generate_final_summary_card(uid, quiz, answers, q_times, best_times, best_overall):
    W,H = 1080, 1350
    img = Image.new("RGB", (W,H), BRAND["NAVY"])
    draw = ImageDraw.Draw(img)
    for i in range(0, W, 200):
        for j in range(0, H, 200):
            draw.ellipse((i-20, j-20, i+20, j+20), fill=BRAND["LIGHT_NAVY"])
    small_logo = load_logo_image(64)
    img.paste(small_logo, (50, 35), small_logo)
    draw.text((125, 45), "VIDYASHALA", fill=BRAND["WHITE"], font=load_font(20, True))
    draw.text((125, 70), "DIAGNOSTIC REPORT", fill=BRAND["YELLOW"], font=load_font(16, True))
    draw.text((W//2, 130), "FINAL SCORE CARD", fill=BRAND["WHITE"], font=load_font(36, True), anchor="mm")
    draw.text((W//2, 165), "7-Minute Combined Timer • Premium Analysis", fill=BRAND["YELLOW"], font=load_font(16, True), anchor="mm")
    score = calculate_score(answers, q_times, quiz)
    cx,cy = W//2, 260
    draw.ellipse((cx-90, cy-90, cx+90, cy+90), fill=BRAND["YELLOW"])
    draw.text((cx, cy-15), f"{score['total_marks']:.2f}", fill=BRAND["NAVY"], font=load_font(48, True), anchor="mm")
    draw.text((cx, cy+25), f"/ {len(quiz)}", fill=BRAND["NAVY"], font=load_font(20, True), anchor="mm")
    y_stats = 370
    draw.rounded_rectangle((50, y_stats, 350, y_stats+110), radius=18, fill=BRAND["GREEN"])
    draw.text((200, y_stats+25), "✅ CORRECT", fill=BRAND["WHITE"], font=load_font(16, True), anchor="mm")
    draw.text((200, y_stats+65), str(score['correct']), fill=BRAND["WHITE"], font=load_font(36, True), anchor="mm")
    draw.rounded_rectangle((390, y_stats, 690, y_stats+110), radius=18, fill=BRAND["RED"])
    draw.text((540, y_stats+25), "❌ WRONG", fill=BRAND["WHITE"], font=load_font(16, True), anchor="mm")
    draw.text((540, y_stats+65), str(score['incorrect']), fill=BRAND["WHITE"], font=load_font(36, True), anchor="mm")
    draw.rounded_rectangle((730, y_stats, 1030, y_stats+110), radius=18, fill=BRAND["GRAY"])
    draw.text((880, y_stats+25), "⏭ LEFT", fill=BRAND["WHITE"], font=load_font(16, True), anchor="mm")
    draw.text((880, y_stats+65), str(score['left']), fill=BRAND["WHITE"], font=load_font(36, True), anchor="mm")
    y_break = y_stats+130
    draw.rounded_rectangle((50, y_break, W-50, y_break+100), radius=18, fill=BRAND["WHITE"])
    draw.text((80, y_break+20), "📊 MARKS BREAKDOWN (+1 / -0.25 / 0)", fill=BRAND["NAVY"], font=load_font(16, True))
    draw.text((80, y_break+50), f"Correct: {score['correct']} x 1.0 = +{score['correct']*1.0:.2f}", fill=BRAND["GREEN"], font=load_font(14, True))
    draw.text((80, y_break+75), f"Wrong: {score['incorrect']} x -0.25 = {score['incorrect']*-0.25:.2f}", fill=BRAND["RED"], font=load_font(14, True))
    draw.text((W-80, y_break+60), f"Total: {score['total_marks']:.2f}", fill=BRAND["NAVY"], font=load_font(22, True), anchor="rm")
    y_time = y_break+120
    draw.rounded_rectangle((50, y_time, W-50, y_time+140), radius=18, fill=BRAND["WHITE"])
    draw.text((80, y_time+15), "⏱ TIME ANALYSIS (7min combined)", fill=BRAND["NAVY"], font=load_font(16, True))
    draw.text((80, y_time+45), f"Total Time Used: {score['total_time']:.1f}s / {TOTAL_QUIZ_TIME}s", fill=BRAND["NAVY"], font=load_font(14, True))
    draw.text((80, y_time+70), f"Avg per Q: {score['avg_time']:.1f}s", fill=BRAND["NAVY"], font=load_font(14, True))
    topper_total_time = sum([t for t,_ in best_times.values()]) if best_times else score['total_time']
    topper_avg = topper_total_time / len(quiz) if quiz and topper_total_time>0 else 0
    draw.text((80, y_time+95), f"Topper Avg: {topper_avg:.1f}s | Topper Total: {topper_total_time:.1f}s", fill=BRAND["GRAY"], font=load_font(12, True))
    y_comp = y_time+160
    draw.rounded_rectangle((50, y_comp, W-50, y_comp+160), radius=18, fill=BRAND["LIGHT_NAVY"])
    draw.text((80, y_comp+15), "🏆 COMPARISON WITH TOPPER", fill=BRAND["YELLOW"], font=load_font(16, True))
    topper_marks = best_overall["marks"]
    topper_user = best_overall["user"]
    draw.text((80, y_comp+45), f"Topper: @{topper_user} - {topper_marks:.2f} marks", fill=BRAND["WHITE"], font=load_font(14, True))
    diff_marks = score['total_marks'] - topper_marks
    diff_text = f"You are {abs(diff_marks):.2f} marks {'behind' if diff_marks<0 else 'ahead of'} topper"
    draw.text((80, y_comp+70), diff_text, fill=BRAND["YELLOW"], font=load_font(14, True))
    if score['avg_time'] < topper_avg and topper_avg>0:
        speed_text = f"⚡ {topper_avg - score['avg_time']:.1f}s faster per Q than topper avg!"
    else:
        speed_text = f"🐢 {score['avg_time'] - topper_avg:.1f}s slower per Q than topper avg"
    draw.text((80, y_comp+95), speed_text, fill=BRAND["WHITE"], font=load_font(14, True))
    acc = (score['correct']/len(quiz)*100) if quiz else 0
    draw.text((80, y_comp+120), f"Accuracy: {acc:.1f}% ({score['correct']}/{len(quiz)}) | Saved & Resumable", fill=BRAND["WHITE"], font=load_font(14, True))
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
    draw.text((W//2, y_footer+35), msg, fill=BRAND["WHITE"] if color!=BRAND["YELLOW"] else BRAND["NAVY"], font=load_font(20, True), anchor="mm")
    draw.text((W//2, H-30), "Tap tabs below for Q-wise analysis | Resume supported", fill=(255,255,255,100), font=load_font(12, True), anchor="mm")
    buf = io.BytesIO(); img.save(buf, format="PNG"); buf.seek(0); return buf

def build_result_tabs(quiz_len, current_idx=None):
    from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
    markup = InlineKeyboardMarkup(row_width=5)
    buttons = []
    for i in range(quiz_len):
        label = f"Q{i+1}"
        if current_idx == i:
            label = f"•{label}•"
        buttons.append(InlineKeyboardButton(label, callback_data=f"res_q_{i}"))
    for i in range(0, len(buttons), 5):
        markup.row(*buttons[i:i+5])
    markup.row(InlineKeyboardButton("📊 FINAL SUMMARY", callback_data="res_summary"))
    markup.row(InlineKeyboardButton("🔄 Retake Test", callback_data="retake"))
    return markup

def show_question(uid, q_idx, edit=False):
    sess = sessions.get(uid)
    if not sess: return
    quiz = sess['quiz']
    if q_idx <0 or q_idx >= len(quiz): return
    # Update time for previous question
    now = time.time()
    prev_q = sess['current_q']
    if 'last_entry' in sess:
        time_spent = now - sess['last_entry']
        # Add to previous question time if not same
        if prev_q != q_idx:
            sess['q_times'][prev_q] += time_spent
    sess['current_q'] = q_idx
    sess['last_entry'] = now
    save_sessions()
    card = generate_question_card_static(q_idx, len(quiz), quiz[q_idx]['q'])
    caption = build_quiz_caption(uid)
    keyboard = build_quiz_keyboard(uid)
    try:
        chat_id, msg_id = sess.get('msg_chat_id'), sess.get('msg_id')
        if edit and chat_id and msg_id and bot:
            from telebot.types import InputMediaPhoto
            bot.edit_message_media(media=InputMediaPhoto(card, caption=caption), chat_id=chat_id, message_id=msg_id, reply_markup=keyboard)
        else:
            # Should not happen in new flow, but handle
            if bot:
                msg = bot.send_photo(uid, card, caption=caption, reply_markup=keyboard)
                sess['msg_chat_id'] = msg.chat.id
                sess['msg_id'] = msg.message_id
    except Exception as e:
        print(f"show_question error: {e}")
        # Fallback caption edit
        try:
            if bot and chat_id and msg_id:
                bot.edit_message_caption(caption=caption, chat_id=chat_id, message_id=msg_id, reply_markup=keyboard)
        except: pass

def overall_timer_loop(uid):
    """Only updates caption with timer/progress - does NOT refresh image (non-distracting)"""
    while active_overall_timers.get(uid, False):
        try:
            sess = sessions.get(uid)
            if not sess or sess.get('finished'):
                break
            start_time = sess['start_time']
            overall_elapsed = time.time() - start_time
            remaining = TOTAL_QUIZ_TIME - overall_elapsed
            if remaining <= 0:
                print(f"Overall time up for {uid}, auto-submitting")
                auto_submit_quiz(uid)
                break
            # Update caption only - no image refresh
            chat_id = sess.get('msg_chat_id')
            msg_id = sess.get('msg_id')
            if chat_id and msg_id and bot:
                caption = build_quiz_caption(uid)
                keyboard = build_quiz_keyboard(uid)
                try:
                    bot.edit_message_caption(caption=caption, chat_id=chat_id, message_id=msg_id, reply_markup=keyboard)
                except Exception as e:
                    # Ignore if same content or rate limit
                    pass
            # Also update current question time accumulation
            # (we add 1 sec to current q time each loop for accurate tracking)
            sess['q_times'][sess['current_q']] += 1
            if int(overall_elapsed) % 5 == 0:
                save_sessions()
        except Exception as e:
            print(f"overall_timer error {uid}: {e}")
        time.sleep(2)  # Update every 2 seconds - less distracting

def auto_submit_quiz(uid):
    sess = sessions.get(uid)
    if not sess: return
    # Stop timer
    active_overall_timers[uid] = False
    # Mark all unanswered as left (-1)
    for i in range(len(sess['answers'])):
        if sess['answers'][i] is None:
            sess['answers'][i] = -1
    # Finalize current q time
    now = time.time()
    if 'last_entry' in sess:
        sess['q_times'][sess['current_q']] += now - sess['last_entry']
    sess['finished'] = True
    save_sessions()
    # Send final results
    send_final_results(uid)

def send_final_results(uid):
    sess = sessions.get(uid)
    if not sess: return
    quiz = sess['quiz']
    answers = sess['answers']
    q_times = sess['q_times']
    # Ensure all answered
    for i in range(len(answers)):
        if answers[i] is None:
            answers[i] = -1
    score = calculate_score(answers, q_times, quiz)
    # Update best overall
    global best_overall
    if score['total_marks'] > best_overall['marks'] or (score['total_marks'] == best_overall['marks'] and score['total_time'] < best_overall['time']):
        best_overall = {"marks": score['total_marks'], "time": score['total_time'], "user": sess.get('username','user')}
    # Update best times per Q
    for i, ans in enumerate(answers):
        if ans is not None and ans != -1 and ans == quiz[i]['ans']:
            cur = best_times.get(i)
            if not cur or q_times[i] < cur[0]:
                best_times[i] = (q_times[i], sess.get('username','user'))
    save_sessions()
    card = generate_final_summary_card(uid, quiz, answers, q_times, best_times, best_overall)
    markup = build_result_tabs(len(quiz), current_idx=None)
    try:
        chat_id = sess.get('msg_chat_id')
        msg_id = sess.get('msg_id')
        if chat_id and msg_id and bot:
            from telebot.types import InputMediaPhoto
            bot.edit_message_media(media=InputMediaPhoto(card, caption=f"✅ AUTO-SUBMITTED! Final: {score['total_marks']:.2f}/{len(quiz)} | {score['correct']}C {score['incorrect']}W {score['left']}L | Time: {score['total_time']:.1f}s"), chat_id=chat_id, message_id=msg_id, reply_markup=markup)
            result_msg[uid] = (chat_id, msg_id, quiz, answers, q_times)
        else:
            msg = bot.send_photo(uid, card, caption=f"Final: {score['total_marks']:.2f}", reply_markup=markup)
            result_msg[uid] = (msg.chat.id, msg.message_id, quiz, answers, q_times)
    except Exception as e:
        print(f"Send final results error: {e}")
        try:
            msg = bot.send_photo(uid, card, caption=f"Final: {score['total_marks']:.2f}", reply_markup=markup)
            result_msg[uid] = (msg.chat.id, msg.message_id, quiz, answers, q_times)
        except: pass
    # Stop timer
    active_overall_timers[uid] = False

def start_new_quiz(uid, username, chat_id_for_msg=None):
    quiz = get_quiz()
    sess = {
        'quiz': quiz,
        'answers': [None]*len(quiz),
        'q_times': [0]*len(quiz),
        'start_time': time.time(),
        'current_q': 0,
        'last_entry': time.time(),
        'username': username,
        'finished': False,
        'msg_chat_id': None,
        'msg_id': None
    }
    sessions[uid] = sess
    save_sessions()
    # Send first question as new message
    card = generate_question_card_static(0, len(quiz), quiz[0]['q'])
    caption = build_quiz_caption(uid)
    keyboard = build_quiz_keyboard(uid)
    try:
        msg = bot.send_photo(uid, card, caption=caption, reply_markup=keyboard)
        sess['msg_chat_id'] = msg.chat.id
        sess['msg_id'] = msg.message_id
        save_sessions()
        # Start overall timer thread
        active_overall_timers[uid] = True
        threading.Thread(target=overall_timer_loop, args=(uid,), daemon=True).start()
    except Exception as e:
        print(f"start_new_quiz error: {e}")

if bot:
    @bot.message_handler(commands=['start'])
    def handle_start(message):
        uid = message.from_user.id
        username = message.from_user.username or message.from_user.first_name
        # Check for existing unfinished session
        existing = sessions.get(uid)
        if existing and not existing.get('finished'):
            remaining = TOTAL_QUIZ_TIME - (time.time() - existing['start_time'])
            if remaining > 0:
                # Offer continue
                from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("▶️ Continue Quiz", callback_data="continue_quiz"))
                markup.add(InlineKeyboardButton("🔄 Restart New Quiz", callback_data="restart_new"))
                bot.send_message(uid, f"📚 You have an unfinished quiz!\nQ{existing['current_q']+1}/{len(existing['quiz'])} | Time left: {int(remaining//60)}:{int(remaining%60):02d}\nYour progress is saved. Continue?", reply_markup=markup)
                return
        if "quiz" in message.text:
            quiz = get_quiz()
            sessions[uid] = {
                'quiz': quiz,
                'answers': [None]*len(quiz),
                'q_times': [0]*len(quiz),
                'start_time': 0,
                'current_q': 0,
                'last_entry': 0,
                'username': username,
                'finished': False
            }
            # Show cover
            card = generate_launch_card()
            from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
            markup = InlineKeyboardMarkup().add(InlineKeyboardButton("▶️ TAP TO START THE TEST (7min)", callback_data="start_test_full"))
            bot.send_photo(uid, card, caption=f"DIAGNOSTIC READY ({len(quiz)} Qs)\n7 Minutes Total • +1 / -0.25 • Resume Supported", reply_markup=markup)
        else:
            bot.send_message(uid,"Go to @vidyashalatest and tap Take Diagnostic Test")

    @bot.message_handler(commands=['quiz'])
    def post_card(message):
        from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
        username=bot.get_me().username
        markup=InlineKeyboardMarkup().add(InlineKeyboardButton("🎯 Take Diagnostic Test (7min)", url=f"https://t.me/{username}?start=quiz"))
        caption="Take a Diagnostic Test\n7 Minutes Total • +1 / -0.25 • Resume Supported\nPremium new UI"
        card=generate_launch_card()
        try:
            bot.send_photo("@vidyashalatest", card, caption=caption, reply_markup=markup)
            bot.reply_to(message, "Posted to @vidyashalatest - New 7min + resume version ✅")
        except Exception as e:
            bot.reply_to(message, f"Make bot admin in channel: {e}")

    @bot.callback_query_handler(func=lambda c: True)
    def handle_all(call):
        uid=call.from_user.id
        data = call.data
        username = call.from_user.username or call.from_user.first_name
        if data == "start_test_full" or data == "start_test":
            # Start fresh 7min quiz
            start_new_quiz(uid, username)
            bot.answer_callback_query(call.id, "Test started! 7min timer")
        elif data == "continue_quiz":
            sess = sessions.get(uid)
            if not sess:
                bot.answer_callback_query(call.id, "No saved quiz")
                return
            # Restore timer
            remaining = TOTAL_QUIZ_TIME - (time.time() - sess['start_time'])
            if remaining <=0:
                auto_submit_quiz(uid)
                bot.answer_callback_query(call.id, "Time over, auto-submitting")
                return
            # Resume showing current Q
            sess['last_entry'] = time.time()
            show_question(uid, sess['current_q'], edit=False)
            # Actually need to send new photo if msg_id invalid, but try edit
            # For continue, we send new message
            card = generate_question_card_static(sess['current_q'], len(sess['quiz']), sess['quiz'][sess['current_q']]['q'])
            caption = build_quiz_caption(uid)
            keyboard = build_quiz_keyboard(uid)
            try:
                msg = bot.send_photo(uid, card, caption=caption, reply_markup=keyboard)
                sess['msg_chat_id'] = msg.chat.id
                sess['msg_id'] = msg.message_id
                active_overall_timers[uid] = True
                threading.Thread(target=overall_timer_loop, args=(uid,), daemon=True).start()
                bot.answer_callback_query(call.id, "Resumed!")
            except Exception as e:
                print(f"continue error: {e}")
        elif data == "restart_new" or data == "retake":
            start_new_quiz(uid, username)
            bot.answer_callback_query(call.id, "New test started!")
        elif data.startswith("nav_q_"):
            try:
                q_idx = int(data.split("_")[-1])
                if uid not in sessions: return
                show_question(uid, q_idx, edit=True)
                bot.answer_callback_query(call.id, f"Q{q_idx+1}")
            except Exception as e:
                print(f"nav_q error: {e}")
        elif data == "nav_next":
            sess = sessions.get(uid)
            if not sess: return
            if sess['current_q'] < len(sess['quiz'])-1:
                show_question(uid, sess['current_q']+1, edit=True)
                bot.answer_callback_query(call.id, "Next")
        elif data == "nav_prev":
            sess = sessions.get(uid)
            if not sess: return
            if sess['current_q'] >0:
                show_question(uid, sess['current_q']-1, edit=True)
                bot.answer_callback_query(call.id, "Back")
        elif data.startswith("ans_"):
            try:
                _,q_idx,opt_idx = data.split("_")
                q_idx, opt_idx = int(q_idx), int(opt_idx)
                sess = sessions.get(uid)
                if not sess: return
                # Only allow answer for current question or any question (new spec: user can select as per choice)
                # We allow answer for any q_idx, but update current_q's answer if they are on that q
                # For simplicity, set answer for q_idx
                sess['answers'][q_idx] = opt_idx
                # If answering current question, stay on same question but update UI to show selected
                # Update time
                now = time.time()
                # For simplicity, don't add time here, timer loop adds
                save_sessions()
                # Refresh keyboard to show selected
                if sess['current_q'] == q_idx:
                    # Stay on same Q, just update keyboard/caption
                    caption = build_quiz_caption(uid)
                    keyboard = build_quiz_keyboard(uid)
                    try:
                        bot.edit_message_caption(caption=caption, chat_id=sess['msg_chat_id'], message_id=sess['msg_id'], reply_markup=keyboard)
                    except: pass
                else:
                    # If answered different Q via palette, also update
                    pass
                bot.answer_callback_query(call.id, f"Selected {chr(65+opt_idx)} for Q{q_idx+1}")
            except Exception as e:
                print(f"ans error: {e}")
        elif data == "submit_test":
            # Confirm submit
            from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("✅ Yes, Submit", callback_data="confirm_submit"))
            markup.add(InlineKeyboardButton("❌ Cancel", callback_data="cancel_submit"))
            bot.send_message(uid, "Are you sure you want to submit? You cannot change after submit.", reply_markup=markup)
            bot.answer_callback_query(call.id, "Confirm submit")
        elif data == "confirm_submit":
            auto_submit_quiz(uid)
            bot.answer_callback_query(call.id, "Submitted!")
        elif data == "cancel_submit":
            bot.answer_callback_query(call.id, "Cancelled")
            try:
                bot.delete_message(uid, call.message.message_id)
            except: pass
        elif data.startswith("res_q_"):
            try:
                q_idx = int(data.split("_")[-1])
                if uid not in result_msg: return
                chat_id, msg_id, quiz, answers, q_times = result_msg[uid]
                card = generate_question_result_card(q_idx, quiz, answers, q_times, best_times)
                markup = build_result_tabs(len(quiz), current_idx=q_idx)
                from telebot.types import InputMediaPhoto
                bot.edit_message_media(media=InputMediaPhoto(card, caption=f"Q{q_idx+1} Analysis - Tap tabs below"), chat_id=chat_id, message_id=msg_id, reply_markup=markup)
                bot.answer_callback_query(call.id, f"Q{q_idx+1} details")
            except Exception as e:
                print(f"res_q error: {e}")
        elif data == "res_summary":
            try:
                if uid not in result_msg: return
                chat_id, msg_id, quiz, answers, q_times = result_msg[uid]
                card = generate_final_summary_card(uid, quiz, answers, q_times, best_times, best_overall)
                markup = build_result_tabs(len(quiz), current_idx=None)
                from telebot.types import InputMediaPhoto
                score = calculate_score(answers, q_times, quiz)
                bot.edit_message_media(media=InputMediaPhoto(card, caption=f"Final Summary: {score['total_marks']:.2f}/{len(quiz)} | {score['correct']}C {score['incorrect']}W {score['left']}L"), chat_id=chat_id, message_id=msg_id, reply_markup=markup)
                bot.answer_callback_query(call.id, "Summary")
            except Exception as e:
                print(f"res_summary error: {e}")

@app.route('/')
def home():
    mode = "webhook" if RENDER_URL else "polling"
    return f"Vidyashala bot OK - 7min total + resume + real logo - mode:{mode}"

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
