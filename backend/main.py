from fastapi import (
    FastAPI,
    UploadFile,
    File,
    Request,
    BackgroundTasks,
    Form,
    Depends,
    HTTPException,
    status
)
from fastapi.responses import (
    RedirectResponse,
    HTMLResponse,
    JSONResponse,
    StreamingResponse
)
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from typing import List
import os
import sqlite3
import smtplib
import uuid
import time
import json
import csv
import io
import hashlib
import binascii
import secrets
import glob
import threading
from email.message import EmailMessage
from email import message_from_bytes, policy
from gemini_engine import run_full_pipeline
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# -------------------------------------------------
# APP SETUP
# -------------------------------------------------
app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "super-secret-key-change-me"), max_age=None)
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# -------------------------------------------------
# STORAGE
# -------------------------------------------------
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Serve uploaded images
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

DB_PATH = os.path.join(os.path.dirname(__file__), "lifestyle_index.db")
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cur = conn.cursor()
cur.execute(
    "CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER, username TEXT, event_type TEXT, session_id TEXT)"
)
cur.execute(
    "CREATE TABLE IF NOT EXISTS api_usage (id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER, username TEXT, session_id TEXT, input_tokens INTEGER, output_tokens INTEGER, total_tokens INTEGER)"
)
conn.commit()

def record_event(username: str, event_type: str, session_id: str | None = None):
    try:
        cur.execute(
            "INSERT INTO events (ts, username, event_type, session_id) VALUES (?, ?, ?, ?)",
            (int(time.time()), username, event_type, session_id),
        )
        conn.commit()
    except Exception:
        pass

def record_api_usage(username: str, session_id: str, usage: dict):
    try:
        input_tokens = int(usage.get("input_tokens") or 0)
        output_tokens = int(usage.get("output_tokens") or 0)
        total_tokens = int(usage.get("total_tokens") or (input_tokens + output_tokens))
        cur.execute(
            "INSERT INTO api_usage (ts, username, session_id, input_tokens, output_tokens, total_tokens) VALUES (?, ?, ?, ?, ?, ?)",
            (int(time.time()), username, session_id, input_tokens, output_tokens, total_tokens),
        )
        conn.commit()
    except Exception:
        pass

USER_EMAILS = {
    "admin": os.getenv("ADMIN_EMAIL", "admin@example.com"),
    "jeyasri": "jeyasri@example.com",
    "jadagesh": "jadagesh@example.com",
    "beno": "beno@example.com",
    "satish": "satish@example.com",
    "george": "george@example.com",
    "dhanush": "dhanush.moolemane@iiflsamasta.com",
}

def get_user_stats(username: str) -> dict:
    cur.execute("SELECT COUNT(*) FROM events WHERE username=? AND event_type='login'", (username,))
    logins = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM events WHERE username=? AND event_type='upload'", (username,))
    uploads = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM events WHERE username=? AND event_type='report_generated'", (username,))
    reports = cur.fetchone()[0]
    cur.execute("SELECT COALESCE(SUM(total_tokens),0), COALESCE(SUM(input_tokens),0), COALESCE(SUM(output_tokens),0) FROM api_usage WHERE username=?", (username,))
    t = cur.fetchone() or (0, 0, 0)
    cur.execute("SELECT MAX(ts) FROM events WHERE username=?", (username,))
    last_ts = cur.fetchone()[0]
    last_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(int(last_ts))) if last_ts else "-"
    cur.execute("SELECT DISTINCT session_id FROM events WHERE username=? AND session_id IS NOT NULL ORDER BY ts DESC LIMIT 20", (username,))
    sessions = [row[0] for row in cur.fetchall()]
    return {
        "username": username,
        "logins": logins,
        "uploads": uploads,
        "reports": reports,
        "tokens": {"total": t[0], "input": t[1], "output": t[2]},
        "last_activity": last_str,
        "sessions": sessions,
    }

def build_user_report_document(username: str) -> tuple[bytes, str, str]:
    stats = get_user_stats(username)
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.units import inch
        from reportlab.lib import colors
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=letter, topMargin=0.5*inch)
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle('T', parent=styles['Heading1'], fontSize=22, textColor=colors.HexColor('#667fea'), alignment=1)
        story = []
        story.append(Paragraph(f"User Activity Report: {username}", title_style))
        story.append(Spacer(1, 0.3*inch))
        data_table = [
            ['Metric', 'Value'],
            ['Logins', str(stats['logins'])],
            ['Uploads', str(stats['uploads'])],
            ['Reports Generated', str(stats['reports'])],
            ['API Tokens Total', str(stats['tokens']['total'])],
            ['API Tokens Input', str(stats['tokens']['input'])],
            ['API Tokens Output', str(stats['tokens']['output'])],
            ['Last Activity', stats['last_activity']],
        ]
        table = Table(data_table, colWidths=[2.5*inch, 3.0*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#667fea')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 13),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(table)
        if stats['sessions']:
            story.append(Spacer(1, 0.2*inch))
            story.append(Paragraph("<b>Recent Sessions</b>", styles['Heading2']))
            for sid in stats['sessions']:
                story.append(Paragraph(sid, styles['BodyText']))
        doc.build(story)
        buf.seek(0)
        return (buf.getvalue(), "application/pdf", f"{username}-activity-report.pdf")
    except Exception:
        text = f"""User Activity Report: {username}
Logins: {stats['logins']}
Uploads: {stats['uploads']}
Reports Generated: {stats['reports']}
API Tokens Total: {stats['tokens']['total']}
API Tokens Input: {stats['tokens']['input']}
API Tokens Output: {stats['tokens']['output']}
Last Activity: {stats['last_activity']}
"""
        return (text.encode('utf-8'), "text/plain", f"{username}-activity-report.txt")

def _save_to_outbox(msg: EmailMessage) -> str:
    """Save an EmailMessage to the outbox folder and return the file path."""
    outdir = os.path.join(os.path.dirname(__file__), "outbox")
    os.makedirs(outdir, exist_ok=True)
    fname = f"{int(time.time())}-{uuid.uuid4()}.eml"
    path = os.path.join(outdir, fname)
    with open(path, "wb") as f:
        f.write(msg.as_bytes())
    return path


def _smtp_send(msg: EmailMessage) -> tuple[bool, str | None]:
    """
    Attempt to deliver msg via the configured SMTP server.
    Returns (True, None) on success or (False, error_string) on failure.
    Does NOT save to outbox – that is always handled by the caller.
    """
    host     = os.getenv("SMTP_HOST")
    port     = int(os.getenv("SMTP_PORT") or "587")
    user     = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASS")

    if not host:
        debug_enabled = os.getenv("SMTP_DEBUG", "").lower() in ("1", "true", "yes")
        if debug_enabled:
            debug_host = os.getenv("SMTP_DEBUG_HOST", "localhost")
            debug_port = int(os.getenv("SMTP_DEBUG_PORT", "1025"))
            try:
                with smtplib.SMTP(debug_host, debug_port, timeout=5) as s:
                    s.send_message(msg)
                    return (True, None)
            except Exception as e:
                return (False, f"debug-smtp-failed: {e}")
        return (False, "no-smtp-config")

    use_ssl = os.getenv("SMTP_USE_SSL", "").lower() in ("1", "true", "yes") or port == 465
    try:
        if use_ssl:
            with smtplib.SMTP_SSL(host, port, timeout=20) as s:
                if user and password:
                    try:
                        s.login(user, password)
                    except smtplib.SMTPAuthenticationError as e:
                        return (False, f"SMTP auth failed: {e}")
                    except Exception as e:
                        return (False, f"SMTP login failed: {e}")
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=20) as s:
                try:
                    s.starttls()
                except Exception as e:
                    print(f"Warning: starttls failed: {e}")
                if user and password:
                    try:
                        s.login(user, password)
                    except smtplib.SMTPAuthenticationError as e:
                        return (False, f"SMTP auth failed: {e}")
                    except Exception as e:
                        return (False, f"SMTP login failed: {e}")
                s.send_message(msg)
        return (True, None)
    except Exception as e:
        return (False, str(e))


def send_email_with_attachment(to_email: str, subject: str, body_text: str, attachment_bytes: bytes, attachment_filename: str, attachment_mimetype: str) -> tuple[bool, str | None]:
    """Send an email with an attachment.
    Always saves a copy to outbox/ first, then attempts SMTP delivery.
    Returns (True, None) on successful SMTP send,
            (True, "saved-to-outbox:<path>") when saved but not yet sent,
            (False, error) on outbox save failure.
    """
    from_addr = os.getenv("SMTP_FROM") or os.getenv("SMTP_USER") or "noreply@example.com"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"]    = from_addr
    msg["To"]      = to_email
    msg.set_content(body_text)
    maintype, subtype = (attachment_mimetype.split("/", 1) + ["octet-stream"])[:2]
    msg.add_attachment(attachment_bytes, maintype=maintype, subtype=subtype, filename=attachment_filename)

    # Always persist to outbox first
    try:
        eml_path = _save_to_outbox(msg)
        print(f"Email saved to outbox: {eml_path} → to={to_email} subject={subject!r}")
    except Exception as e:
        print(f"Failed to save email to outbox: {e}")
        return (False, f"outbox-save-failed: {e}")

    # Then attempt live SMTP delivery
    ok, err = _smtp_send(msg)
    if ok:
        # Sent – remove the outbox copy so the retry loop doesn't re-send it
        try:
            os.remove(eml_path)
        except Exception:
            pass
        print(f"Email sent via SMTP → {to_email}")
        return (True, None)
    else:
        # SMTP failed / not configured – leave outbox copy for retry
        print(f"SMTP not available ({err}); email queued in outbox: {eml_path}")
        return (True, f"saved-to-outbox:{eml_path}")

# -------------------------------------------------
# IN-MEMORY STATE (session-based)
# -------------------------------------------------
PROCESS_STATUS = {}   # session_id → PROCESSING | DONE | ERROR
RESULT_STORE = {}     # session_id → result dict
SESSION_USERS = {}
PASSWORD_RESET_TOKENS: dict = {}

# Default mapping used to seed legacy usernames (stored in DB for real-time updates)
DEFAULT_USERNAME_MAP = [
    ("chirag.h@iiflsamasta.com", "chirag"),
    ("sathish.palanisamy@iiflsamasta.com", "sathish"),
    ("nalinik@iiflsamasta.com", "nalini"),
    ("jeyasri.m@iiflsamasta.com", "jeyasri"),
    ("jagadeesha@iiflsamasta.com", "jagadesh"),
    ("shraddha@iiflsamasta.com", "shraddha"),
    ("lakshmipathi.v@iiflsamasta.com", "lakshmipathi"),
    ("christuraja.a@iiflsamasta.com", "christuraja"),
    ("ranjith.devadiga@iiflsamasta.com", "ranjith"),
    ("sanandaganesh.g@iiflsamasta.com", "sanandaganesh"),
    ("gourav.hulbatte@iiflsamasta.com", "gourav"),
    ("mv.madan@iiflsamasta.com", "madanmv"),
    ("p.deepakumar@iiflsamasta.com", "deepakumar"),
    ("benothomas.bobby@iiflsamasta.com", "beno"),
    ("george.prasad@iiflsamasta.com", "george"),
    ("manoj.malipatil@iiflsamasta.com", "manoj"),
]


def ensure_unique_username(base: str) -> str:
    """Return a unique username by appending a numeric suffix if needed."""
    base = (base or '').strip() or 'user'
    final = base
    attempt = 0
    while True:
        cur.execute("SELECT COUNT(*) FROM users WHERE username = ?", (final,))
        if cur.fetchone()[0] == 0:
            return final
        attempt += 1
        final = f"{base}{attempt}"
        if attempt > 100:
            return f"{base}-{int(time.time())}"

# -------------------------------------------------
# BACKGROUND PROCESSOR
# -------------------------------------------------
def process_images(session_id: str, session_path: str):
    """
    Process images with Gemini Vision API for real scoring.
    """
    try:
        print(f"\n[{session_id}] Starting analysis...")
        
        # Get image paths
        image_files = [f for f in os.listdir(session_path) 
                      if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))]
        
        if not image_files:
            raise ValueError("No images found in session folder")
        
        image_paths = [os.path.join(session_path, f) for f in image_files]
        print(f"[{session_id}] Found {len(image_paths)} images: {image_files}")
        
        # Run Gemini analysis
        print(f"[{session_id}] Running Gemini Vision analysis...")
        result = run_full_pipeline(image_paths)
        
        analysis = result.get("analysis", {})
        scoring = result.get("scoring", {})
        
        # Determine risk level based on normalized score
        norm_score = scoring.get("normalized_score", 50)
        if norm_score >= 70:
            risk_level = "Low Risk"
        elif norm_score >= 50:
            risk_level = "Medium Risk"
        else:
            risk_level = "High Risk"
        
        # Store results
        RESULT_STORE[session_id] = {
            "overall_score": scoring.get("final_score", 75),
            "normalized_score": norm_score,
            "risk_level": risk_level,
            "exterior_score": scoring.get("exterior_score", 0),
            "interior_score": scoring.get("interior_score", 0),
            "adjusted_exterior_score": scoring.get("adjusted_exterior_score", 0),
            "category_scores": scoring.get("category_scores", {}),
            "analysis": analysis,
            "images": [f"/uploads/{session_id}/{img}" for img in image_files]
        }
        
        PROCESS_STATUS[session_id] = "DONE"
        print(f"[{session_id}] Analysis complete!")
        try:
            user = SESSION_USERS.get(session_id)
            if user:
                record_event(user, "report_generated", session_id)
                usage = result.get("usage") or {}
                if usage:
                    record_api_usage(user, session_id, usage)
        except Exception:
            pass
        
    except Exception as e:
        print(f"[{session_id}] Error: {str(e)}")
        PROCESS_STATUS[session_id] = "ERROR"
        RESULT_STORE[session_id] = {
            "error": str(e)
        }

# -------------------------------------------------
# AUTHENTICATION
# -------------------------------------------------

class NotAuthenticated(Exception):
    pass

@app.exception_handler(NotAuthenticated)
async def not_authenticated_handler(request: Request, exc: NotAuthenticated):
    return RedirectResponse(url="/login")

def get_current_user(request: Request):
    user = request.session.get("user")
    if not user:
        raise NotAuthenticated()
    return user
def get_admin_user(request: Request):
    user = request.session.get("user")
    if not user or user != "admin":
        raise NotAuthenticated()
    return user

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    # Admin backdoor (existing default)
    if username == "admin" and password == "password":
        request.session["user"] = "admin"
        try:
            record_event("admin", "login", None)
        except Exception:
            pass
        return RedirectResponse(url="/admin", status_code=303)

    # Lookup user by username, name or email
    try:
        cur.execute("SELECT id, username, name, email, role, is_active, password_hash FROM users WHERE username = ? OR name = ? OR email = ? LIMIT 1", (username, username, username))
        row = cur.fetchone()
        if not row:
            # Try fallback: see if username is an email local part (before @)
            if "@" not in username:
                cur.execute("SELECT id, username, name, email, role, is_active, password_hash FROM users WHERE email LIKE ? LIMIT 1", (f"%{username}%",))
                row = cur.fetchone()
        if not row:
            return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid username or password"})

        # Correctly unpack DB row (id, username, name, email, role, is_active, password_hash)
        uid, db_username, name, email, role, is_active, password_hash = row
        # Choose a stable session identity (prefer username, fall back to email, then provided input)
        session_identity = db_username or email or username

        if not bool(is_active):
            return templates.TemplateResponse("login.html", {"request": request, "error": "Account is deactivated. Contact admin."})

        # If password set, verify it
        if password_hash and verify_password(password, password_hash):
            request.session["user"] = session_identity
            try:
                record_event(session_identity, "login", None)
            except Exception:
                pass
            # update last_active
            cur.execute("UPDATE users SET last_active = ? WHERE id = ?", (time.strftime('%Y-%m-%d %H:%M:%S'), uid))
            conn.commit()
            return RedirectResponse(url="/", status_code=303)
        elif not password_hash and password == "password123":
            # allow legacy login and store hash
            new_hash = hash_password(password)
            cur.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, uid))
            conn.commit()
            request.session["user"] = session_identity
            try:
                record_event(session_identity, "login", None)
            except Exception:
                pass
            cur.execute("UPDATE users SET last_active = ? WHERE id = ?", (time.strftime('%Y-%m-%d %H:%M:%S'), uid))
            conn.commit()
            return RedirectResponse(url="/", status_code=303)
        else:
            return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid username or password"})
    except Exception as e:
        print(f"Login error: {e}")
        return templates.TemplateResponse("login.html", {"request": request, "error": "Login error"})

@app.api_route("/logout", methods=["GET", "POST"])
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)

# -------------------------------------------------
# ROUTES
# -------------------------------------------------

# Landing / Upload page
@app.get("/", response_class=HTMLResponse)
def index(request: Request, user: str = Depends(get_current_user)):
    return templates.TemplateResponse(
        "index.html",
        {"request": request}
    )

# Upload handler
@app.post("/upload")
async def upload_images(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    pincode: str = Form(default=""),
    postoffice: str = Form(default=""),
    district: str = Form(default=""),
    state: str = Form(default=""),
    user: str = Depends(get_current_user)
):
    print("FILES RECEIVED:", len(files))
    session_id = str(uuid.uuid4())
    session_path = os.path.join(UPLOAD_DIR, session_id)
    os.makedirs(session_path, exist_ok=True)

    PROCESS_STATUS[session_id] = "PROCESSING"
    try:
        SESSION_USERS[session_id] = user
        record_event(user, "upload", session_id)
    except Exception:
        pass

    # Save uploaded files
    for file in files:
        file_path = os.path.join(session_path, file.filename)
        with open(file_path, "wb") as f:
            f.write(await file.read())

    # Store location info in session
    LOCATION_DATA = {}  # Will be used to store location per session
    if not hasattr(upload_images, "_locations"):
        upload_images._locations = {}
    upload_images._locations[session_id] = {
        "pincode": pincode,
        "postoffice": postoffice,
        "district": district,
        "state": state
    }

    # Run processing in background
    background_tasks.add_task(
        process_images,
        session_id,
        session_path
    )

    return RedirectResponse(
        url=f"/processing?session_id={session_id}",
        status_code=303
    )

@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request, user: str = Depends(get_admin_user)):
    cur.execute("SELECT username, event_type, COUNT(*) FROM events GROUP BY username, event_type")
    rows = cur.fetchall()
    per_user = {}
    for uname, etype, count in rows:
        if uname not in per_user:
            per_user[uname] = {"login": 0, "upload": 0, "report_generated": 0}
        per_user[uname][etype] = count
    cur.execute("SELECT COALESCE(SUM(total_tokens),0), COALESCE(SUM(input_tokens),0), COALESCE(SUM(output_tokens),0) FROM api_usage")
    token_totals = cur.fetchone() or (0, 0, 0)
    cur.execute("SELECT COUNT(*) FROM events WHERE event_type='login'")
    total_logins = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM events WHERE event_type='upload'")
    total_uploads = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM events WHERE event_type='report_generated'")
    total_reports = cur.fetchone()[0]
    cur.execute("SELECT ts, username, event_type, session_id FROM events ORDER BY ts DESC")
    events_rows = cur.fetchall()
    events = []
    for ts_val, uname, etype, sid in events_rows:
        try:
            ts_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(int(ts_val)))
        except Exception:
            ts_str = str(ts_val)
        events.append({"ts": ts_str, "username": uname, "event_type": etype, "session_id": sid})
    
    # Get users for user management section
    try:
        cur.execute("SELECT id, username, name, email, role, is_active, last_active FROM users ORDER BY created_at DESC")
        users_rows = cur.fetchall()
        users = [
            {
                "id": row[0],
                "username": row[1],
                "name": row[2],
                "email": row[3],
                "role": row[4],
                "is_active": bool(row[5]),
                "last_active": row[6]
            }
            for row in users_rows
        ]
    except Exception as e:
        print(f"Error fetching users: {e}")
        users = []
    
    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "per_user": per_user,
            "total_logins": total_logins,
            "total_uploads": total_uploads,
            "total_reports": total_reports,
            "total_tokens": token_totals[0],
            "input_tokens": token_totals[1],
            "output_tokens": token_totals[2],
            "events": events,
            "users": users,
        },
    )

@app.get("/admin/stats")
def admin_stats(user: str = Depends(get_admin_user)):
    cur.execute("SELECT username, event_type, COUNT(*) FROM events GROUP BY username, event_type")
    rows = cur.fetchall()
    per_user = {}
    for uname, etype, count in rows:
        if uname not in per_user:
            per_user[uname] = {"login": 0, "upload": 0, "report_generated": 0}
        per_user[uname][etype] = count
    cur.execute("SELECT COALESCE(SUM(total_tokens),0), COALESCE(SUM(input_tokens),0), COALESCE(SUM(output_tokens),0) FROM api_usage")
    token_totals = cur.fetchone() or (0, 0, 0)
    cur.execute("SELECT COUNT(*) FROM events WHERE event_type='login'")
    total_logins = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM events WHERE event_type='upload'")
    total_uploads = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM events WHERE event_type='report_generated'")
    total_reports = cur.fetchone()[0]
    return JSONResponse({
        "per_user": per_user,
        "totals": {
            "logins": total_logins,
            "uploads": total_uploads,
            "reports": total_reports
        },
        "tokens": {
            "total": token_totals[0],
            "input": token_totals[1],
            "output": token_totals[2]
        }
    })

@app.get("/admin/export-user-pdf")
def admin_export_user_pdf(username: str, user: str = Depends(get_admin_user)):
    content, mimetype, filename = build_user_report_document(username)
    return StreamingResponse(iter([content]), media_type=mimetype, headers={"Content-Disposition": f"attachment; filename={filename}"})


def build_user_report_csv(username: str) -> tuple[bytes, str, str]:
    """Return CSV bytes for a single user's activity summary."""
    stats = get_user_stats(username)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["username", "logins", "uploads", "reports", "tokens_total", "tokens_input", "tokens_output", "last_activity"])
    writer.writerow([
        stats.get("username"),
        stats.get("logins"),
        stats.get("uploads"),
        stats.get("reports"),
        stats.get("tokens", {}).get("total"),
        stats.get("tokens", {}).get("input"),
        stats.get("tokens", {}).get("output"),
        stats.get("last_activity"),
    ])
    data = out.getvalue().encode("utf-8")
    return (data, "text/csv", f"{username}-activity-report.csv")


@app.get("/admin/export-user-csv")
def admin_export_user_csv(username: str, user: str = Depends(get_admin_user)):
    content, mimetype, filename = build_user_report_csv(username)
    return StreamingResponse(iter([content]), media_type=mimetype, headers={"Content-Disposition": f"attachment; filename={filename}"})


def build_all_users_csv() -> tuple[bytes, str, str]:
    """Generate CSV summarizing all users (registered in users table)."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["username", "logins", "uploads", "reports", "tokens_total", "tokens_input", "tokens_output", "last_activity"])
    try:
        cur.execute("SELECT username FROM users")
        user_rows = [r[0] for r in cur.fetchall()]
    except Exception:
        user_rows = []
    # Fallback: include any usernames that appear in events but not in users
    try:
        cur.execute("SELECT DISTINCT username FROM events")
        event_users = [r[0] for r in cur.fetchall()]
    except Exception:
        event_users = []
    all_users = sorted(set(user_rows + event_users))
    for u in all_users:
        stats = get_user_stats(u)
        writer.writerow([
            stats.get("username"),
            stats.get("logins"),
            stats.get("uploads"),
            stats.get("reports"),
            stats.get("tokens", {}).get("total"),
            stats.get("tokens", {}).get("input"),
            stats.get("tokens", {}).get("output"),
            stats.get("last_activity"),
        ])
    data = out.getvalue().encode("utf-8")
    return (data, "text/csv", "all-users-activity-report.csv")


@app.get("/admin/export-all-users-csv")
def admin_export_all_users_csv(user: str = Depends(get_admin_user)):
    content, mimetype, filename = build_all_users_csv()
    return StreamingResponse(iter([content]), media_type=mimetype, headers={"Content-Disposition": f"attachment; filename={filename}"})


def build_all_users_pdf() -> tuple[bytes, str, str]:
    """Generate a PDF summarizing all users in a table."""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.units import inch
        from reportlab.lib import colors
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=letter, topMargin=0.5*inch)
        styles = getSampleStyleSheet()
        story = []
        story.append(Paragraph("All Users Activity Summary", styles['Heading1']))
        story.append(Spacer(1, 0.2*inch))
        # Table header
        data_table = [["User", "Logins", "Uploads", "Reports", "Tokens", "Input", "Output", "Last Activity"]]
        try:
            cur.execute("SELECT username FROM users")
            user_rows = [r[0] for r in cur.fetchall()]
        except Exception:
            user_rows = []
        try:
            cur.execute("SELECT DISTINCT username FROM events")
            event_users = [r[0] for r in cur.fetchall()]
        except Exception:
            event_users = []
        all_users = sorted(set(user_rows + event_users))
        for u in all_users:
            s = get_user_stats(u)
            data_table.append([
                s.get('username'),
                s.get('logins'),
                s.get('uploads'),
                s.get('reports'),
                s.get('tokens', {}).get('total'),
                s.get('tokens', {}).get('input'),
                s.get('tokens', {}).get('output'),
                s.get('last_activity')
            ])
        table = Table(data_table, repeatRows=1, hAlign='LEFT')
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#667fea')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
        ]))
        story.append(table)
        doc.build(story)
        buf.seek(0)
        return (buf.getvalue(), "application/pdf", "all-users-activity-report.pdf")
    except Exception:
        # fallback: plain text
        content = "All Users Activity Summary\n\n"
        try:
            cur.execute("SELECT username FROM users")
            user_rows = [r[0] for r in cur.fetchall()]
        except Exception:
            user_rows = []
        try:
            cur.execute("SELECT DISTINCT username FROM events")
            event_users = [r[0] for r in cur.fetchall()]
        except Exception:
            event_users = []
        all_users = sorted(set(user_rows + event_users))
        for u in all_users:
            s = get_user_stats(u)
            content += f"{s.get('username')} - Logins: {s.get('logins')}, Uploads: {s.get('uploads')}, Reports: {s.get('reports')}, Tokens: {s.get('tokens', {}).get('total')}, Last: {s.get('last_activity')}\n"
        return (content.encode('utf-8'), 'text/plain', 'all-users-activity-report.txt')


@app.get("/admin/export-all-users-pdf")
def admin_export_all_users_pdf(user: str = Depends(get_admin_user)):
    content, mimetype, filename = build_all_users_pdf()
    return StreamingResponse(iter([content]), media_type=mimetype, headers={"Content-Disposition": f"attachment; filename={filename}"})

@app.post("/admin/send-user-report")
async def admin_send_user_report(request: Request, user: str = Depends(get_admin_user)):
    data = await request.json()
    username = data.get("username")
    if not username:
        raise HTTPException(status_code=400, detail="username required")
    content, mimetype, filename = build_user_report_document(username)
    # Resolve recipient email: prefer explicit mapping; if username itself looks like an email, use it; otherwise append @example.com
    to_email = USER_EMAILS.get(username)
    if not to_email:
        to_email = username if "@" in (username or "") else f"{username}@example.com"
    subject = f"Activity Report for {username}"
    body_text = "Please find attached your latest activity report."
    ok, err = send_email_with_attachment(to_email, subject, body_text, content, filename, mimetype)
    if not ok:
        status_code = 400 if err and "SMTP_HOST" in err else 500
        msg = err or "email not configured or send failed"
        print(f"Email send failed for {to_email}: {msg}")
        return JSONResponse({"status": "error", "message": msg}, status_code=status_code)
    # If the function succeeded but saved to outbox, inform the caller
    if err and str(err).startswith("saved-to-outbox"):
        return JSONResponse({"status": "saved", "message": err, "to": to_email})
    return JSONResponse({"status": "sent", "to": to_email})


@app.post("/admin/test-email")
def admin_test_email(user: str = Depends(get_admin_user)):
    """Send a small diagnostic test email to the configured admin address to validate SMTP settings."""
    to_email = os.getenv("ADMIN_EMAIL") or os.getenv("SMTP_FROM") or "admin@example.com"
    subject = "Index-Scoring SMTP Test"
    body_text = "This is a test email from Index-Scoring. If you received this, your SMTP settings are valid." 
    ok, err = send_email_with_attachment(to_email, subject, body_text, b"Test body", "test.txt", "text/plain")
    if not ok:
        status_code = 400 if err and "SMTP_HOST" in err else 500
        msg = err or "send failed"
        print(f"Test email failed: {msg}")
        return JSONResponse({"status": "error", "message": msg}, status_code=status_code)
    if err and str(err).startswith("saved-to-outbox"):
        return JSONResponse({"status": "saved", "message": err, "to": to_email})
    return JSONResponse({"status": "sent", "to": to_email})


@app.get('/admin/smtp-status')
def admin_smtp_status(user: str = Depends(get_admin_user)):
    """Return current SMTP config and attempt a quick connect and login test (if credentials present)."""
    host = os.getenv('SMTP_HOST')
    debug = os.getenv('SMTP_DEBUG', '').lower() in ('1', 'true', 'yes')
    debug_host = os.getenv('SMTP_DEBUG_HOST', 'localhost')
    port = int(os.getenv('SMTP_PORT') or os.getenv('SMTP_DEBUG_PORT', '1025'))

    user = os.getenv('SMTP_USER')
    password = os.getenv('SMTP_PASS')
    use_ssl = os.getenv('SMTP_USE_SSL', '').lower() in ('1', 'true', 'yes') or (int(os.getenv('SMTP_PORT') or port) == 465)

    result = {'smtp_host': host, 'smtp_debug': debug, 'port': port, 'smtp_user_provided': bool(user), 'use_ssl': use_ssl}

    if not host and not debug:
        result['status'] = 'no_config'
        result['message'] = 'SMTP_HOST not configured. Set SMTP_HOST in .env or enable SMTP_DEBUG=1 to test local SMTP.'
        return JSONResponse(result, status_code=400)

    target_host = host if host else debug_host
    try:
        if use_ssl:
            with smtplib.SMTP_SSL(target_host, port, timeout=5) as s:
                # attempt login if credentials provided
                if user and password:
                    try:
                        s.login(user, password)
                        result['status'] = 'ok'
                        result['message'] = f'Connected and authenticated to {target_host}:{port} (SSL)'
                        return JSONResponse(result)
                    except smtplib.SMTPAuthenticationError as e:
                        result['status'] = 'auth_failed'
                        result['message'] = f'SMTP auth failed: {e} (check username / password, or use app-passwords for Zoho)'
                        return JSONResponse(result, status_code=403)
                # no credentials: just connected
                result['status'] = 'ok'
                result['message'] = f'Connected to {target_host}:{port} (SSL)'
                return JSONResponse(result)
        else:
            with smtplib.SMTP(target_host, port, timeout=5) as s:
                try:
                    s.starttls()
                except Exception:
                    pass
                if user and password:
                    try:
                        s.login(user, password)
                        result['status'] = 'ok'
                        result['message'] = f'Connected and authenticated to {target_host}:{port} (STARTTLS)'
                        return JSONResponse(result)
                    except smtplib.SMTPAuthenticationError as e:
                        result['status'] = 'auth_failed'
                        result['message'] = f'SMTP auth failed: {e} (check username / password, or use app-passwords for Zoho)'
                        return JSONResponse(result, status_code=403)
                result['status'] = 'ok'
                result['message'] = f'Connected to {target_host}:{port} (STARTTLS)'
                return JSONResponse(result)
    except Exception as e:
        result['status'] = 'conn_failed'
        result['message'] = str(e)
        return JSONResponse(result, status_code=500)

# -----------------------------
# Outbox management (admin)
# -----------------------------
@app.get("/admin/outbox")
def admin_list_outbox(user: str = Depends(get_admin_user)):
    outdir = os.path.join(os.path.dirname(__file__), "outbox")
    os.makedirs(outdir, exist_ok=True)
    files = sorted(os.listdir(outdir))
    entries = []
    for f in files:
        path = os.path.join(outdir, f)
        try:
            stat = os.stat(path)
            entries.append({"filename": f, "size": stat.st_size, "mtime": int(stat.st_mtime)})
        except Exception:
            continue
    return JSONResponse({"files": entries})

@app.get("/admin/outbox/view")
def admin_view_outbox(filename: str, user: str = Depends(get_admin_user)):
    safe = os.path.basename(filename)
    path = os.path.join(os.path.dirname(__file__), "outbox", safe)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="file not found")
    with open(path, "rb") as f:
        raw = f.read()
    try:
        msg = message_from_bytes(raw, policy=policy.default)
        body = ""
        try:
            b = msg.get_body(preferencelist=("plain",))
            if b:
                body = b.get_content()
        except Exception:
            body = ""
        return JSONResponse({"subject": msg.get("Subject"), "from": msg.get("From"), "to": msg.get("To"), "body_preview": (body or "").strip()[:1000]})
    except Exception:
        return JSONResponse({"raw": raw.decode("utf-8", errors="replace")})

@app.post("/admin/outbox/resend")
async def admin_resend_outbox(request: Request, user: str = Depends(get_admin_user)):
    data = await request.json()
    filename = data.get("filename")
    if not filename:
        raise HTTPException(status_code=400, detail="filename required")
    safe = os.path.basename(filename)
    path = os.path.join(os.path.dirname(__file__), "outbox", safe)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="file not found")
    with open(path, "rb") as f:
        raw = f.read()
    try:
        msg = message_from_bytes(raw, policy=policy.default)
    except Exception as e:
        return JSONResponse({"status": "error", "message": f"failed to parse message: {e}"}, status_code=500)

    # Attempt to send using current SMTP configuration or local debug SMTP
    host = os.getenv("SMTP_HOST") or os.getenv("SMTP_DEBUG_HOST", "localhost")
    port = int(os.getenv("SMTP_PORT") or os.getenv("SMTP_DEBUG_PORT", "1025"))
    try:
        with smtplib.SMTP(host, port, timeout=20) as s:
            try:
                s.starttls()
            except Exception:
                pass
            user = os.getenv("SMTP_USER")
            password = os.getenv("SMTP_PASS")
            if user and password:
                try:
                    s.login(user, password)
                except Exception as e:
                    return JSONResponse({"status": "error", "message": f"SMTP login failed: {e}"}, status_code=500)
            try:
                s.send_message(msg)
            except Exception as e:
                return JSONResponse({"status": "error", "message": f"SMTP send failed: {e}"}, status_code=500)
    except Exception as e:
        return JSONResponse({"status": "error", "message": f"SMTP connection failed: {e}"}, status_code=500)

    # On success remove the outbox file
    try:
        os.remove(path)
    except Exception:
        pass
    return JSONResponse({"status": "resent", "filename": filename})

# ----------------------------------
# Outbox auto-retry background worker
# ----------------------------------

def send_eml_via_smtp(eml_path: str) -> tuple[bool, str | None]:
    """Attempt to send a saved .eml file using current SMTP settings.
    Returns (True, None) on success or (False, error_message) on failure."""
    try:
        with open(eml_path, "rb") as f:
            raw = f.read()
        msg = message_from_bytes(raw, policy=policy.default)
    except Exception as e:
        return (False, f"parse-error:{e}")

    host = os.getenv("SMTP_HOST")
    debug_enabled = os.getenv("SMTP_DEBUG", "").lower() in ("1", "true", "yes")
    if not host and debug_enabled:
        host = os.getenv("SMTP_DEBUG_HOST", "localhost")
    port = int(os.getenv("SMTP_PORT") or os.getenv("SMTP_DEBUG_PORT", "1025"))

    if not host:
        return (False, "no-smtp-config")

    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASS")

    use_ssl = os.getenv('SMTP_USE_SSL', '').lower() in ('1', 'true', 'yes') or (int(os.getenv('SMTP_PORT') or port) == 465)

    # Prefer implicit SSL if configured or port 465 is used
    try:
        if use_ssl:
            try:
                with smtplib.SMTP_SSL(host, port, timeout=30) as s:
                    if user and password:
                        try:
                            s.login(user, password)
                        except smtplib.SMTPAuthenticationError as e:
                            return (False, f"smtp-auth-failed:{e} (check username/password, try SMTP_USE_SSL=1 and port=465 or use an app-specific password for providers like Zoho)")
                        except Exception as e:
                            return (False, f"smtp-login-failed:{e}")
                    try:
                        s.send_message(msg)
                    except Exception as e:
                        return (False, f"smtp-send-failed:{e}")
                return (True, None)
            except Exception as e:
                # If implicit SSL fails, fall through to STARTTLS attempt
                print(f"SMTP_SSL connection failed: {e}. Will try STARTTLS fallback.")

        # Try STARTTLS (common for port 587)
        with smtplib.SMTP(host, port, timeout=30) as s:
            try:
                s.starttls()
            except Exception as e:
                print(f"STARTTLS not available/failed: {e}")
            if user and password:
                try:
                    s.login(user, password)
                except smtplib.SMTPAuthenticationError as e:
                    return (False, f"smtp-auth-failed:{e} (check username/password, use app-specific password if provider requires it)")
                except Exception as e:
                    return (False, f"smtp-login-failed:{e}")
            try:
                s.send_message(msg)
            except Exception as e:
                return (False, f"smtp-send-failed:{e}")
        return (True, None)
    except Exception as e:
        return (False, f"smtp-conn-failed:{e}")


def outbox_retry_loop():
    interval = int(os.getenv("SMTP_OUTBOX_RETRY_INTERVAL", "60"))
    enabled = os.getenv("SMTP_OUTBOX_AUTO_RETRY", "1").lower() in ("1", "true", "yes")
    print(f"Outbox auto-retry enabled={enabled}, interval={interval}s")

    while enabled:
        try:
            smtp_ready = bool(os.getenv("SMTP_HOST")) or os.getenv("SMTP_DEBUG", "").lower() in ("1", "true", "yes")
            if not smtp_ready:
                time.sleep(interval)
                continue

            outdir = os.path.join(os.path.dirname(__file__), "outbox")
            if not os.path.isdir(outdir):
                time.sleep(interval)
                continue

            files = sorted(glob.glob(os.path.join(outdir, "*.eml")))
            for fpath in files:
                try:
                    ok, err = send_eml_via_smtp(fpath)
                    if ok:
                        print(f"Outbox resend succeeded: {fpath}")
                        try:
                            os.remove(fpath)
                        except Exception:
                            pass
                    else:
                        print(f"Outbox resend failed for {fpath}: {err}")
                    # small pause between attempts
                    time.sleep(1)
                except Exception as e:
                    print(f"Outbox worker error for {fpath}: {e}")

            time.sleep(interval)
        except Exception as e:
            print(f"Outbox retry loop error: {e}")
            time.sleep(interval)



# =============================================================================
# DAILY EMAIL SCHEDULER
# =============================================================================
# Runs in a daemon thread.  Two jobs per day (times in IST = UTC+5:30):
#   09:00 IST  → aggregate summary  (who sent how many requests yesterday)
#               sent to all DIGEST_REPORT_EMAILS
#   21:00 IST  → per-user consolidated CSV  (each user gets their own rows)
#               sent to each user individually
# =============================================================================

_IST_OFFSET = 5 * 3600 + 30 * 60  # seconds east of UTC

DIGEST_REPORT_EMAILS = [
    "chirag.h@iiflsamasta.com",
    "sathish.palanisamy@iiflsamasta.com",
    "nalinik@iiflsamasta.com",
    "jeyasri.m@iiflsamasta.com",
]

DIGEST_USER_EMAIL_MAP: dict = {
    "chirag":        "chirag.h@iiflsamasta.com",
    "sathish":       "sathish.palanisamy@iiflsamasta.com",
    "nalini":        "nalinik@iiflsamasta.com",
    "jeyasri":       "jeyasri.m@iiflsamasta.com",
    "jagadesh":      "jagadeesha@iiflsamasta.com",
    "shraddha":      "shraddha@iiflsamasta.com",
    "lakshmipathi":  "lakshmipathi.v@iiflsamasta.com",
    "christuraja":   "christuraja.a@iiflsamasta.com",
    "ranjith":       "ranjith.devadiga@iiflsamasta.com",
    "sanandaganesh": "sanandaganesh.g@iiflsamasta.com",
    "gourav":        "gourav.hulbatte@iiflsamasta.com",
    "madanmv":       "mv.madan@iiflsamasta.com",
    "deepakumar":    "p.deepakumar@iiflsamasta.com",
    "beno":          "benothomas.bobby@iiflsamasta.com",
    "george":        "george.prasad@iiflsamasta.com",
    "manoj":         "manoj.malipatil@iiflsamasta.com",
}


def _ist_hhmm() -> int:
    """Return current IST time as HHMM integer, e.g. 900 or 2100."""
    t = time.gmtime(time.time() + _IST_OFFSET)
    return t.tm_hour * 100 + t.tm_min


def _ist_date(offset_days: int = 0) -> str:
    """Return YYYY-MM-DD in IST. offset_days=-1 gives yesterday."""
    ts = time.time() + _IST_OFFSET + offset_days * 86400
    return time.strftime("%Y-%m-%d", time.gmtime(ts))


def _ist_day_unix_range(date_str: str) -> tuple:
    """Return (start_utc, end_utc) unix timestamps for a full IST calendar day."""
    t = time.strptime(date_str, "%Y-%m-%d")
    start_utc = int(time.mktime(t)) - _IST_OFFSET
    return start_utc, start_utc + 86400


def _digest_morning(target_date: str) -> None:
    """Send aggregate request counts for target_date to all DIGEST_REPORT_EMAILS."""
    print(f"[scheduler] Running 09:00 aggregate for {target_date}")
    start_u, end_u = _ist_day_unix_range(target_date)
    try:
        cur.execute(
            "SELECT username, COUNT(*) FROM events "
            "WHERE event_type='upload' AND ts>=? AND ts<? "
            "GROUP BY username ORDER BY COUNT(*) DESC",
            (start_u, end_u),
        )
        rows = cur.fetchall()
    except Exception as e:
        print(f"[scheduler] DB error in morning aggregate: {e}")
        return

    total = sum(r[1] for r in rows)
    lines = [f"  {u:<22} {c:>5} request(s)" for u, c in rows] or ["  No requests submitted."]
    body = (
        f"Index-Scoring – Daily Request Summary\n"
        f"Date: {target_date} (IST)\n"
        f"{'─'*45}\n\n"
        f"User                       Requests\n"
        f"{'─'*45}\n"
        + "\n".join(lines)
        + f"\n{'─'*45}\n"
        f"Total: {total} request(s)\n\n"
        f"Automated digest sent at 09:00 IST.\n"
    )
    subject = f"[Index-Scoring] Daily Request Summary – {target_date}"
    for email in DIGEST_REPORT_EMAILS:
        ok, err = send_plain_email(email, subject, body)
        if not ok:
            print(f"[scheduler] morning digest failed for {email}: {err}")


def _build_digest_csv(username: str, target_date: str) -> bytes | None:
    """Build CSV bytes for all of username's scored sessions on target_date."""
    start_u, end_u = _ist_day_unix_range(target_date)
    try:
        cur.execute(
            """
            SELECT e.session_id, e.ts, e.username,
                   COALESCE(u.input_tokens,0),
                   COALESCE(u.output_tokens,0),
                   COALESCE(u.total_tokens,0)
            FROM events e
            LEFT JOIN api_usage u
                ON u.session_id=e.session_id AND u.username=e.username
            WHERE e.event_type='report_generated'
              AND e.username=? AND e.ts>=? AND e.ts<?
            ORDER BY e.ts
            """,
            (username, start_u, end_u),
        )
        rows = cur.fetchall()
    except Exception as e:
        print(f"[scheduler] DB error building CSV for {username}: {e}")
        return None

    if not rows:
        return None

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["session_id", "timestamp_ist", "username",
                     "input_tokens", "output_tokens", "total_tokens"])
    for sid, ts, uname, inp, outp, tot in rows:
        ts_ist = time.strftime("%Y-%m-%d %H:%M:%S",
                               time.gmtime(int(ts) + _IST_OFFSET))
        writer.writerow([sid, ts_ist, uname, inp, outp, tot])
    return out.getvalue().encode("utf-8")


def _digest_evening(target_date: str) -> None:
    """Send each user their own consolidated CSV for target_date."""
    print(f"[scheduler] Running 21:00 CSV digest for {target_date}")
    for username, email in DIGEST_USER_EMAIL_MAP.items():
        csv_bytes = _build_digest_csv(username, target_date)
        if csv_bytes is None:
            print(f"[scheduler] No rows for {username} on {target_date} – skipping")
            continue
        filename = f"{username}-scores-{target_date}.csv"
        subject  = f"[Index-Scoring] Your Scores – {target_date}"
        body = (
            f"Hi {username.capitalize()},\n\n"
            f"Your consolidated scoring report for {target_date} is attached.\n"
            f"It contains all entries processed under your account today.\n\n"
            f"Automated digest sent at 21:00 IST.\n"
        )
        ok, err = send_email_with_attachment(
            email, subject, body,
            csv_bytes, filename, "text/csv"
        )
        if not ok:
            print(f"[scheduler] evening CSV failed for {email}: {err}")


def _scheduler_loop() -> None:
    last_morning = ""
    last_evening = ""
    print("[scheduler] Started – waiting for 09:00 / 21:00 IST …")
    while True:
        try:
            hhmm  = _ist_hhmm()
            today = _ist_date(0)

            if hhmm == 900 and last_morning != today:
                last_morning = today
                try:
                    _digest_morning(_ist_date(-1))
                except Exception as e:
                    print(f"[scheduler] morning job error: {e}")

            if hhmm == 2100 and last_evening != today:
                last_evening = today
                try:
                    _digest_evening(today)
                except Exception as e:
                    print(f"[scheduler] evening job error: {e}")

        except Exception as e:
            print(f"[scheduler] loop error: {e}")

        time.sleep(20)


def _start_scheduler() -> None:
    t = threading.Thread(target=_scheduler_loop, daemon=True)
    t.start()
    print("[scheduler] Background scheduler started (09:00 IST aggregate | 21:00 IST CSV)")

@app.on_event("startup")
def start_outbox_retry_worker():
    if os.getenv("SMTP_OUTBOX_AUTO_RETRY", "1").lower() in ("1", "true", "yes"):
        t = threading.Thread(target=outbox_retry_loop, daemon=True)
        t.start()
    # Start the daily digest scheduler (09:00 IST aggregate + 21:00 IST per-user CSV)
    _start_scheduler()


@app.post('/admin/outbox/retry')
def admin_retry_outbox(user: str = Depends(get_admin_user)):
    """Attempt to resend all files from the outbox immediately."""
    outdir = os.path.join(os.path.dirname(__file__), "outbox")
    if not os.path.isdir(outdir):
        return JSONResponse({"results": []})
    files = sorted(glob.glob(os.path.join(outdir, "*.eml")))
    results = []
    for fpath in files:
        ok, err = send_eml_via_smtp(fpath)
        if ok:
            try:
                os.remove(fpath)
            except Exception:
                pass
            results.append({"file": os.path.basename(fpath), "status": "sent"})
        else:
            results.append({"file": os.path.basename(fpath), "status": "failed", "error": err})
    return JSONResponse({"results": results})

# Processing screen
@app.get("/processing", response_class=HTMLResponse)
def processing(request: Request, session_id: str, user: str = Depends(get_current_user)):
    # Get location data if it exists
    location_data = {}
    if hasattr(upload_images, "_locations") and session_id in upload_images._locations:
        location_data = upload_images._locations[session_id]
    
    return templates.TemplateResponse(
        "processing.html",
        {
            "request": request,
            "session_id": session_id,
            "pincode": location_data.get("pincode", ""),
            "postoffice": location_data.get("postoffice", ""),
            "district": location_data.get("district", ""),
            "state": location_data.get("state", "")
        }
    )

# Status polling endpoint
@app.get("/status")
def status(session_id: str, user: str = Depends(get_current_user)):
    return JSONResponse({
        "status": PROCESS_STATUS.get(session_id, "UNKNOWN")
    })

# Result dashboard
@app.get("/result", response_class=HTMLResponse)
def result(request: Request, session_id: str, user: str = Depends(get_current_user)):
    data = RESULT_STORE.get(session_id)
    
    # Get location data if it exists
    location_data = {}
    if hasattr(upload_images, "_locations") and session_id in upload_images._locations:
        location_data = upload_images._locations[session_id]

    # Handle invalid or failed sessions safely
    if not data or "error" in data:
        return templates.TemplateResponse(
            "result.html",
            {
                "request": request,
                "score": "N/A",
                "risk": "Processing Failed",
                "exterior": 0,
                "interior": 0,
                "images": [],
                "normalized_score": 0,
                "category_scores": {},
                "analysis": {},
                "postoffice": location_data.get("postoffice", ""),
                "district": location_data.get("district", ""),
                "state": location_data.get("state", "")
            }
        )

    return templates.TemplateResponse(
        "result.html",
        {
            "request": request,
            "score": data.get("overall_score", 0),
            "normalized_score": data.get("normalized_score", 0),
            "risk": data.get("risk_level", "Unknown"),
            "exterior": data.get("exterior_score", 0),
            "interior": data.get("interior_score", 0),
            "adjusted_exterior": data.get("adjusted_exterior_score", 0),
            "category_scores": data.get("category_scores", {}),
            "analysis": data.get("analysis", {}),
            "images": data.get("images", []),
            "postoffice": location_data.get("postoffice", ""),
            "district": location_data.get("district", ""),
            "state": location_data.get("state", "")
        }
    )

# JSON API endpoint for real-time dashboard updates
@app.get("/result-json")
def result_json(session_id: str, user: str = Depends(get_current_user)):
    """Return the current result data as JSON for client-side polling"""
    data = RESULT_STORE.get(session_id)
    
    # If data doesn't exist or has error, return a safe default
    if not data or "error" in data:
        return JSONResponse({
            "overall_score": 0,
            "normalized_score": 0,
            "risk_level": "Processing Failed",
            "exterior_score": 0,
            "interior_score": 0,
            "adjusted_exterior_score": 0,
            "category_scores": {},
            "analysis": {},
            "images": [],
            "status": "ERROR" if not data else "READY"
        })
    
    # Return the full result data for dashboard updates
    return JSONResponse({
        "overall_score": data.get("overall_score", 0),
        "normalized_score": data.get("normalized_score", 0),
        "risk_level": data.get("risk_level", "Unknown"),
        "exterior_score": data.get("exterior_score", 0),
        "interior_score": data.get("interior_score", 0),
        "adjusted_exterior_score": data.get("adjusted_exterior_score", 0),
        "category_scores": data.get("category_scores", {}),
        "analysis": data.get("analysis", {}),
        "images": data.get("images", []),
        "status": "READY"
    })


# Debug helper: create a sample result and redirect to it (development only)
@app.get("/debug/fill_result")
def debug_fill_result(user: str = Depends(get_current_user)):
    session_id = str(uuid.uuid4())
    PROCESS_STATUS[session_id] = "DONE"
    RESULT_STORE[session_id] = {
        "overall_score": 112,
        "normalized_score": 74,
        "risk_level": "Low Risk",
        "exterior_score": 72,
        "interior_score": 40,
        "adjusted_exterior_score": 70,
        "category_scores": {"roof": 30, "siding": 25, "landscape": 20},
        "analysis": {"roof": ["minor wear"], "interior": ["good flooring"]},
        "images": []
    }
    return RedirectResponse(url=f"/result?session_id={session_id}", status_code=303)


# -------------------------------------------------
# EXPORT AND SHARE ENDPOINTS
# -------------------------------------------------

@app.post("/export-pdf")
async def export_pdf(request: Request, user: str = Depends(get_current_user)):
    """Generate and export PDF report"""
    try:
        data = await request.json()
        
        # Try to import reportlab for PDF generation
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
            from reportlab.lib.units import inch
            from reportlab.lib import colors
        except ImportError:
            # Fallback: Return a simple text document if reportlab is not installed
            return StreamingResponse(
                iter([f"""
Property Risk Assessment Report
{'='*50}

Overall Risk Score: {data.get('score', 'N/A')} / 150
Normalized Score: {data.get('normalized_score', 'N/A')}%
Risk Level: {data.get('risk', 'N/A')}

BREAKDOWN:
- Exterior Condition: {data.get('exterior', 'N/A')} pts
- Interior Systems: {data.get('interior', 'N/A')} pts

PROPERTY DETAILS:
- Post Office: {data.get('postoffice', 'N/A')}
- District: {data.get('district', 'N/A')}
- State: {data.get('state', 'N/A')}

Generated on: {time.strftime('%Y-%m-%d %H:%M:%S')}
"""]),
                media_type="text/plain",
                headers={"Content-Disposition": "attachment; filename=property-assessment.txt"}
            )
        
        # Create PDF using reportlab
        pdf_buffer = io.BytesIO()
        doc = SimpleDocTemplate(pdf_buffer, pagesize=letter, topMargin=0.5*inch)
        story = []
        
        # Styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#667fea'),
            spaceAfter=12,
            alignment=1
        )
        
        # Add content
        story.append(Paragraph("Property Risk Assessment Report", title_style))
        story.append(Spacer(1, 0.3*inch))
        
        # Key metrics
        data_table = [
            ['Metric', 'Value'],
            ['Overall Risk Score', f"{data.get('score', 'N/A')} / 150"],
            ['Normalized Score', f"{data.get('normalized_score', 'N/A')}%"],
            ['Risk Level', data.get('risk', 'N/A')],
            ['Exterior Condition', f"{data.get('exterior', 'N/A')} pts"],
            ['Interior Systems', f"{data.get('interior', 'N/A')} pts"],
        ]
        
        table = Table(data_table, colWidths=[2.5*inch, 2.5*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#667fea')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 14),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        story.append(table)
        story.append(Spacer(1, 0.3*inch))
        
        # Property details
        story.append(Paragraph("<b>Property Details</b>", styles['Heading2']))
        details_text = f"""
        Post Office: {data.get('postoffice', 'N/A')}<br/>
        District: {data.get('district', 'N/A')}<br/>
        State: {data.get('state', 'N/A')}<br/>
        Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}
        """
        story.append(Paragraph(details_text, styles['BodyText']))
        
        # Build PDF
        doc.build(story)
        pdf_buffer.seek(0)
        
        return StreamingResponse(
            iter([pdf_buffer.getvalue()]),
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=property-assessment.pdf"}
        )
    except Exception as e:
        print(f"PDF Export Error: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/export-csv")
async def export_csv(request: Request, user: str = Depends(get_current_user)):
    """Generate and export CSV report"""
    try:
        data = await request.json()
        
        # Create CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write headers and data
        writer.writerow(['Property Risk Assessment Report'])
        writer.writerow([])
        writer.writerow(['Metric', 'Value'])
        writer.writerow(['Overall Risk Score', f"{data.get('score', 'N/A')} / 150"])
        writer.writerow(['Normalized Score', f"{data.get('normalized_score', 'N/A')}%"])
        writer.writerow(['Risk Level', data.get('risk', 'N/A')])
        writer.writerow(['Exterior Condition', f"{data.get('exterior', 'N/A')} pts"])
        writer.writerow(['Interior Systems', f"{data.get('interior', 'N/A')} pts"])
        writer.writerow([])
        writer.writerow(['Property Details'])
        writer.writerow(['Post Office', data.get('postoffice', 'N/A')])
        writer.writerow(['District', data.get('district', 'N/A')])
        writer.writerow(['State', data.get('state', 'N/A')])
        writer.writerow(['Generated', time.strftime('%Y-%m-%d %H:%M:%S')])
        
        # Return as streaming response
        csv_data = output.getvalue()
        return StreamingResponse(
            iter([csv_data]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=property-assessment.csv"}
        )
    except Exception as e:
        print(f"CSV Export Error: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/generate-share-link")
async def generate_share_link(request: Request, user: str = Depends(get_current_user)):
    """Generate a unique share link for the report"""
    try:
        data = await request.json()
        
        # Generate a unique share ID
        share_id = str(uuid.uuid4())
        
        # Store the share data
        SHARE_STORE = {}
        if not hasattr(app, 'share_store'):
            app.share_store = {}
        
        app.share_store[share_id] = {
            'data': data,
            'created_at': time.time(),
            'expires_at': time.time() + (7 * 24 * 60 * 60)  # 7 days
        }
        
        # Generate the share link
        share_link = f"{request.url.scheme}://{request.url.netloc}/shared-report/{share_id}"
        
        return JSONResponse({
            "share_link": share_link,
            "share_id": share_id
        })
    except Exception as e:
        print(f"Share Link Error: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/shared-report/{share_id}")
async def view_shared_report(share_id: str, request: Request):
    """View a shared report"""
    try:
        if not hasattr(app, 'share_store'):
            app.share_store = {}
        
        if share_id not in app.share_store:
            return HTMLResponse("<h1>Report Not Found</h1><p>This shared report does not exist or has expired.</p>", status_code=404)
        
        share_data = app.share_store[share_id]
        
        # Check if expired
        if time.time() > share_data['expires_at']:
            del app.share_store[share_id]
            return HTMLResponse("<h1>Report Expired</h1><p>This shared report has expired (7 days).</p>", status_code=404)
        
        data = share_data['data']
        
        return templates.TemplateResponse(
            "result.html",
            {
                "request": request,
                "score": data.get("score", "N/A"),
                "normalized_score": data.get("normalized_score", 0),
                "risk": data.get("risk", "Unknown"),
                "exterior": data.get("exterior", 0),
                "interior": data.get("interior", 0),
                "category_scores": {},
                "analysis": {},
                "postoffice": data.get("postoffice", ""),
                "district": data.get("district", ""),
                "state": data.get("state", ""),
                "is_shared_view": True
            }
        )
    except Exception as e:
        print(f"View Shared Report Error: {str(e)}")
        return HTMLResponse(f"<h1>Error</h1><p>{str(e)}</p>", status_code=500)


# -------------------------------------------------
# USER MANAGEMENT ROUTES
# -------------------------------------------------

# Initialize users table
def init_users_db():
    try:
        # Create users table if it does not exist (preserve existing users)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                role TEXT DEFAULT 'user',
                is_active BOOLEAN DEFAULT 1,
                password_hash TEXT,
                last_active TEXT,
                created_at INTEGER
            )
        """)
        conn.commit()

        # Ensure password_hash and username columns exist for older DBs
        cur.execute("PRAGMA table_info(users)")
        cols = [r[1] for r in cur.fetchall()]
        if 'password_hash' not in cols:
            try:
                cur.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
                conn.commit()
            except Exception:
                pass
        if 'username' not in cols:
            try:
                cur.execute("ALTER TABLE users ADD COLUMN username TEXT")
                conn.commit()
            except Exception:
                pass

        # Migrate existing users: set username from email local-part if missing
        try:
            cur.execute("SELECT id, email, username FROM users")
            for uid, email, uname in cur.fetchall():
                if not uname or uname.strip() == '':
                    candidate = (email or '').split('@')[0]
                    # ensure uniqueness
                    base = candidate or f'user_{uid[:8]}'
                    final = ensure_unique_username(base)
                    cur.execute("UPDATE users SET username = ? WHERE id = ?", (final, uid))
            conn.commit()
        except Exception:
            pass

        # Ensure username_mappings table exists (persistent mappings for legacy users)
        try:
            cur.execute("CREATE TABLE IF NOT EXISTS username_mappings (email TEXT UNIQUE, username TEXT, created_at INTEGER, updated_at INTEGER)")
            conn.commit()
            # Seed mappings table from DEFAULT_USERNAME_MAP if it's empty
            cur.execute("SELECT COUNT(*) FROM username_mappings")
            if cur.fetchone()[0] == 0:
                for em, un in DEFAULT_USERNAME_MAP:
                    try:
                        cur.execute("INSERT INTO username_mappings (email, username, created_at, updated_at) VALUES (?, ?, ?, ?)", (em, un, int(time.time()), int(time.time())))
                    except Exception:
                        pass
                conn.commit()
        except Exception:
            pass

    except Exception as e:
        print(f"Error initializing users table: {e}")
        conn.commit()
    conn.commit()

# Password hashing helpers

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 200000)
    return f"{salt}${binascii.hexlify(dk).decode()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt, hexhash = stored_hash.split('$', 1)
        dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 200000)
        return binascii.hexlify(dk).decode() == hexhash
    except Exception:
        return False


# Simple plaintext email sender – always saves to outbox, then attempts SMTP
def send_plain_email(to_email: str, subject: str, body_text: str) -> tuple[bool, str | None]:
    """Send a plain-text email.
    Always saves a copy to outbox/ first, then attempts SMTP delivery.
    """
    from_addr = os.getenv("SMTP_FROM") or os.getenv("SMTP_USER") or "noreply@example.com"

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"]    = from_addr
    msg["To"]      = to_email
    msg.set_content(body_text)

    # Always persist to outbox first
    try:
        eml_path = _save_to_outbox(msg)
        print(f"Email saved to outbox: {eml_path} → to={to_email} subject={subject!r}")
    except Exception as e:
        print(f"Failed to save email to outbox: {e}")
        return (False, f"outbox-save-failed: {e}")

    # Attempt live SMTP delivery
    ok, err = _smtp_send(msg)
    if ok:
        try:
            os.remove(eml_path)
        except Exception:
            pass
        print(f"Email sent via SMTP → {to_email}")
        return (True, None)
    else:
        print(f"SMTP not available ({err}); email queued in outbox: {eml_path}")
        return (True, f"saved-to-outbox:{eml_path}")


init_users_db()

@app.get("/admin/users", response_class=HTMLResponse)
async def admin_users_page(request: Request):
    """Render user management page"""
    try:
        session_user = request.session.get("user")
        if not session_user or session_user != "admin":
            return RedirectResponse(url="/login", status_code=302)
        
        cur.execute("SELECT id, username, name, email, role, is_active, last_active FROM users ORDER BY created_at DESC")
        rows = cur.fetchall()
        
        users = [
            {
                "id": row[0],
                "username": row[1],
                "name": row[2],
                "email": row[3],
                "role": row[4],
                "is_active": bool(row[5]),
                "last_active": row[6]
            }
            for row in rows
        ]
        
        return templates.TemplateResponse(
            "users.html",
            {
                "request": request,
                "users": users
            }
        )
    except Exception as e:
        print(f"Error: {str(e)}")
        return HTMLResponse(f"<h1>Error</h1><p>{str(e)}</p>", status_code=500)


@app.get("/admin/users/api")
async def get_users_api(request: Request):
    """Get all users as JSON for API"""
    try:
        session_user = request.session.get("user")
        if not session_user or session_user != "admin":
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        cur.execute("SELECT id, username, name, email, role, is_active, last_active FROM users ORDER BY created_at DESC")
        rows = cur.fetchall()
        
        users = [
            {
                "id": row[0],
                "username": row[1],
                "name": row[2],
                "email": row[3],
                "role": row[4],
                "is_active": bool(row[5]),
                "last_active": row[6]
            }
            for row in rows
        ]
        
        return JSONResponse({"users": users})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/admin/add-user")
async def add_user(request: Request):
    """Add a new user and email initial credentials"""
    try:
        session_user = request.session.get("user")
        if not session_user or session_user != "admin":
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        data = await request.json()
        name = data.get("name")
        email = data.get("email")
        username = data.get("username")
        role = data.get("role", "user")
        password = data.get("password")
        
        if not name or not email:
            return JSONResponse({"message": "Name and email required"}, status_code=400)
        
        # Generate username from provided value, mapping, or email local-part
        if not username or str(username).strip() == '':
            # Check persistent mappings first
            mapped = None
            try:
                cur.execute("SELECT username FROM username_mappings WHERE email = ?", (email,))
                r = cur.fetchone()
                if r:
                    mapped = r[0]
            except Exception:
                mapped = None
            if mapped:
                username = mapped
            else:
                username = (email or '').split('@')[0]
        username = str(username).strip()
        # Ensure username uniqueness
        username = ensure_unique_username(username)


        # Ensure username uniqueness
        base = username or f'user'
        final = base
        attempt = 0
        while True:
            cur.execute("SELECT COUNT(*) FROM users WHERE username = ?", (final,))
            if cur.fetchone()[0] == 0:
                break
            attempt += 1
            final = f"{base}{attempt}"
            if attempt > 100:
                final = f"{base}-{int(time.time())}"
                break
        username = final

        user_id = str(uuid.uuid4())
        # Generate a temporary password if none provided
        if not password:
            password = secrets.token_urlsafe(8)
        password_hash = hash_password(password)

        cur.execute(
            "INSERT INTO users (id, username, name, email, role, is_active, password_hash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, username, name, email, role, 1, password_hash, int(time.time()))
        )
        conn.commit()

        # Send credentials email (best effort)
        subject = "Your account has been created"
        body = f"Hi {name},\n\nAn account has been created for you on Index-Scoring.\n\nUsername: {username}\nTemporary password: {password}\n\nPlease log in and change your password via the Reset Password flow.\n\nIf you did not expect this email, contact your administrator.\n"
        sent, send_msg = send_plain_email(email, subject, body)

        resp = {"status": "success", "user_id": user_id}
        # Include created username, temporary password and login url in response for admin convenience
        resp["username"] = username
        resp["temp_password"] = password
        resp["login_url"] = "/login"
        if sent and send_msg:
            resp["note"] = f"Email saved: {send_msg}"
        elif not sent:
            resp["note"] = f"Email send failed: {send_msg}"

        return JSONResponse(resp)
    except sqlite3.IntegrityError:
        return JSONResponse({"message": "Email already exists"}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/admin/user/{user_id}")
async def get_user(user_id: str, request: Request):
    """Get user details"""
    try:
        session_user = request.session.get("user")
        if not session_user or session_user != "admin":
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        cur.execute("SELECT id, username, name, email, role, is_active FROM users WHERE id = ?", (user_id,))
        row = cur.fetchone()
        
        if not row:
            return JSONResponse({"error": "User not found"}, status_code=404)
        
        return JSONResponse({
            "id": row[0],
            "username": row[1],
            "name": row[2],
            "email": row[3],
            "role": row[4],
            "is_active": bool(row[5])
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.put("/admin/user/{user_id}")
async def update_user(user_id: str, request: Request):
    """Update user details"""
    try:
        session_user = request.session.get("user")
        if not session_user or session_user != "admin":
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        data = await request.json()
        name = data.get("name")
        username = data.get("username")
        email = data.get("email")
        role = data.get("role")
        
        # Build update fields dynamically (only update provided values)
        fields = []
        params = []
        if username is not None:
            username = str(username).strip()
            fields.append("username = ?")
            params.append(username)
        if name is not None:
            fields.append("name = ?")
            params.append(name)
        if email is not None:
            fields.append("email = ?")
            params.append(email)
        if role is not None:
            fields.append("role = ?")
            params.append(role)
        if not fields:
            return JSONResponse({"message": "No fields to update"}, status_code=400)
        params.append(user_id)
        sql = "UPDATE users SET " + ", ".join(fields) + " WHERE id = ?"
        try:
            cur.execute(sql, tuple(params))
            conn.commit()
        except sqlite3.IntegrityError:
            return JSONResponse({"message": "Username or email already exists"}, status_code=400)
        
        return JSONResponse({"status": "success"})
    except sqlite3.IntegrityError:
        return JSONResponse({"message": "Email already exists"}, status_code=400)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/admin/user/{user_id}/deactivate")
async def deactivate_user(user_id: str, request: Request):
    """Deactivate a user"""
    try:
        session_user = request.session.get("user")
        if not session_user or session_user != "admin":
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        cur.execute("UPDATE users SET is_active = 0 WHERE id = ?", (user_id,))
        conn.commit()
        
        return JSONResponse({"status": "success"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/admin/user/{user_id}/activate")
async def activate_user(user_id: str, request: Request):
    """Activate a user"""
    try:
        session_user = request.session.get("user")
        if not session_user or session_user != "admin":
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        cur.execute("UPDATE users SET is_active = 1 WHERE id = ?", (user_id,))
        conn.commit()
        
        return JSONResponse({"status": "success"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/admin/user/{user_id}/reset-password")
async def reset_user_password(user_id: str, request: Request):
    """Send password reset link to user"""
    try:
        session_user = request.session.get("user")
        if not session_user or session_user != "admin":
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        cur.execute("SELECT email, name FROM users WHERE id = ?", (user_id,))
        row = cur.fetchone()
        
        if not row:
            return JSONResponse({"error": "User not found"}, status_code=404)
        
        email, name = row
        reset_token = str(uuid.uuid4())
        expiry = int(time.time()) + 3600  # 1 hour
        PASSWORD_RESET_TOKENS[reset_token] = (user_id, expiry)

        reset_url = f"http://localhost:8000/reset-password?token={reset_token}"
        body = f"Hi {name},\n\nClick here to reset your password:\n{reset_url}\n\nThis link expires in 1 hour.\n"
        sent, err = send_plain_email(email, "Password Reset Request", body)
        if not sent:
            return JSONResponse({"status": "error", "message": err or "send failed"}, status_code=500)
        return JSONResponse({"status": "success", "message": f"Reset link sent to {email}"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.delete("/admin/user/{user_id}")
async def delete_user(user_id: str, request: Request):
    """Delete a user"""
    try:
        session_user = request.session.get("user")
        if not session_user or session_user != "admin":
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        cur.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        
        return JSONResponse({"status": "success"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/admin/seed-usernames")
async def admin_seed_usernames(request: Request, user: str = Depends(get_admin_user)):
    """Seed usernames and passwords for a known set of legacy users so they can log in."""
    try:
        try:
            body = await request.json()
        except Exception:
            body = None

        # Default mapping from provided list (email -> username)
        default_map = [
            ("chirag.h@iiflsamasta.com", "chirag"),
            ("sathish.palanisamy@iiflsamasta.com", "sathish"),
            ("nalinik@iiflsamasta.com", "nalini"),
            ("jeyasri.m@iiflsamasta.com", "jeyasri"),
            ("jagadeesha@iiflsamasta.com", "jagadesh"),
            ("shraddha@iiflsamasta.com", "shraddha"),
            ("lakshmipathi.v@iiflsamasta.com", "lakshmipathi"),
            ("christuraja.a@iiflsamasta.com", "christuraja"),
            ("ranjith.devadiga@iiflsamasta.com", "ranjith"),
            ("sanandaganesh.g@iiflsamasta.com", "sanandaganesh"),
            ("gourav.hulbatte@iiflsamasta.com", "gourav"),
            ("mv.madan@iiflsamasta.com", "madanmv"),
            ("p.deepakumar@iiflsamasta.com", "deepakumar"),
            ("tanuj.s@iiflsamasta.com", "tanuj"),
            ("benothomas.bobby@iiflsamasta.com", "beno"),
            ("george.prasad@iiflsamasta.com", "george"),
            ("manoj.malipatil@iiflsamasta.com", "manoj"),
        ]

        inputs = body.get("users") if body and isinstance(body, dict) and body.get("users") else None
        if inputs and isinstance(inputs, list):
            m = [(it.get("email"), it.get("username")) for it in inputs if it.get("email") and it.get("username")]
        else:
            m = default_map

        results = []
        for email, username in m:
            cur.execute("SELECT id, name, username FROM users WHERE email = ?", (email,))
            row = cur.fetchone()
            if not row:
                results.append({"email": email, "status": "not_found"})
                continue
            uid = row[0]
            # set username and default password 'password123'
            pw = "password123"
            pwhash = hash_password(pw)
            try:
                cur.execute("UPDATE users SET username = ?, password_hash = ? WHERE id = ?", (username, pwhash, uid))
                conn.commit()
                results.append({"email": email, "username": username, "status": "updated", "temp_password": pw})
            except Exception as e:
                results.append({"email": email, "error": str(e)})
        return JSONResponse({"results": results})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/reset-password", response_class=HTMLResponse)
def reset_password_page(request: Request, token: str | None = None):
    """Render a simple password reset form for a token"""
    # validate token existence
    valid = False
    if token and token in PASSWORD_RESET_TOKENS:
        uid, expiry = PASSWORD_RESET_TOKENS[token]
        if int(time.time()) <= expiry:
            valid = True
    return templates.TemplateResponse("reset_password.html", {"request": request, "token": token, "valid": valid})


@app.post("/reset-password")
async def reset_password_action(request: Request):
    data = await request.form()
    token = data.get("token")
    new_password = data.get("new_password")
    if not token or not new_password:
        return templates.TemplateResponse("reset_password.html", {"request": request, "token": token, "valid": False, "error": "Token and new password are required"})
    entry = PASSWORD_RESET_TOKENS.get(token)
    if not entry:
        return templates.TemplateResponse("reset_password.html", {"request": request, "token": token, "valid": False, "error": "Invalid or expired token"})
    uid, expiry = entry
    if int(time.time()) > expiry:
        del PASSWORD_RESET_TOKENS[token]
        return templates.TemplateResponse("reset_password.html", {"request": request, "token": token, "valid": False, "error": "Token expired"})
    # Update password
    new_hash = hash_password(new_password)
    cur.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, uid))
    conn.commit()
    try:
        del PASSWORD_RESET_TOKENS[token]
    except Exception:
        pass
    return templates.TemplateResponse("login.html", {"request": request, "message": "Password updated. Please login."})