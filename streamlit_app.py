"""
Vendor Recruitment Hub - Streamlit app (Enhanced UI + Gemini AI Integrated)
==========================================================================
Roles
  admin    : full platform management + user management + bulk imports
  manager  : creates jobs (manual or AI-assisted), reviews & scores candidates,
             approves timesheets and leave/WFH requests
  vendor   : views open jobs, submits candidates with duplicate detection,
             tracks submissions and views approved employee timesheets
  employee : hired candidates - submits monthly timesheets, requests leave/WFH

Run:
  pip install -r requirements.txt
  streamlit run app.py
"""
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import sqlite3
import base64
import calendar
from pathlib import Path
from datetime import date, datetime, timedelta

import pandas as pd
from PIL import Image
import plotly.express as px
import streamlit as st

# --- Brand Assets (Base64) ----------------------------------------------------
_LOGO_B64 = """
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
5ErkJggg==
"""

_LOGO_WIDE_B64 = """
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
AElFTkSuQmCC
"""

_ICON_B64 = """
iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAMAAACdt4HsAAAABGdBTUEAALGPC/xhBQAAACBjSFJNAAB6JgAAgIQAAPoAAACA6AAAdTAAAOpg
AAA6mAAAF3CculE8AAAAaVBMVEUAAAD///8AAAAzMzPMzMz/mZnMzP/M/5n//5n//zPMzP+ZmZnMzJn/zJnMzP8zMzPM/zPM/5mZmf+Z
mZn/mZn///8zMzPMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMzMwAAAD945YFAAAAH3RSTlMAAQIDBAUGBwgJCgsMDQ4PEBES
ExQVFhcYGRobHB0eH9515V4AAAAFiSldEAAIHn5wGAAAACXBIWXMAAA7EAAAOxAGVKw4bAAAAYElEQVRYw+3RwQ6AMAhFUXp5U8Wq
///HChE3m1aTeuVqO5cb0qil7U4AECDAvQARW5s6ACh0qgGqWn0g4u4kC6T4gWwFcgRKR6CSjQAKH0CEGgBAgAABAgQIECBAgAD/Abw
BfK4D5G6YJ6oAAAAldEVYdGRhdGU6Y3JlYXRlADIwMjYtMDUtMTRUMDY6NTY6MDgrMDA6MDAeF8KjAAAAJXRFWHRkYXRlOm1vZGlmeQAy
MDI2LTA1LTE0VDA2OjU2OjA4KzAwOjAwH5X8sQAAAABJRU5ErkJggg==
"""

APP_VERSION = "2026.11 · Gemini Pro Edition"

def _img(b64_str: str) -> Image.Image:
    try:
        # Strip all whitespace and line breaks
        clean_b64 = "".join(b64_str.split())
        
        # Ensure correct padding
        missing_padding = len(clean_b64) % 4
        if missing_padding:
            clean_b64 += "=" * (4 - missing_padding)
            
        decoded = base64.b64decode(clean_b64)
        img = Image.open(io.BytesIO(decoded))
        
        # Force Pillow to decode the entire image immediately to catch truncation errors
        img.load()
        return img
    except Exception:
        # Fallback to an empty 1x1 transparent image if decoding or data loading fails
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))

LOGO = _img(_LOGO_B64)
LOGO_WIDE = _img(_LOGO_WIDE_B64)
ICON = _img(_ICON_B64)

st.set_page_config(page_title="Incount · Recruitment & HR Hub", page_icon=ICON, layout="wide")

# --- Enhanced Modern UI CSS ---------------------------------------------------
st.markdown("""
<style>
/* Modern Glassmorphic & Clean Variables */
:root {
    --primary: #4F46E5;
    --primary-hover: #4338CA;
    --surface-card: rgba(255, 255, 255, 0.85);
    --surface-border: rgba(226, 232, 240, 0.8);
    --text-main: #0F172A;
    --text-muted: #64748B;
}

#MainMenu, footer {visibility: hidden;}
.block-container {
    padding-top: 1.5rem;
    padding-bottom: 2.5rem;
    max-width: 1250px;
}

/* Modern Typography & Polish */
h1, h2, h3, h4 {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    letter-spacing: -0.02em;
    font-weight: 700 !important;
}

/* Metrics & Card Enhancements */
[data-testid="stMetric"] {
    background: linear-gradient(135deg, rgba(255, 255, 255, 0.05), rgba(128, 128, 128, 0.05));
    border: 1px solid rgba(148, 163, 184, 0.2);
    border-radius: 16px;
    padding: 16px 20px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.03);
    transition: transform 0.15s ease, box-shadow 0.15s ease;
}
[data-testid="stMetric"]:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 18px rgba(0, 0, 0, 0.06);
}

/* Container Card Borders */
[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 16px;
    border: 1px solid rgba(148, 163, 184, 0.25) !important;
    background: rgba(128, 128, 128, 0.02);
    box-shadow: 0 2px 8px rgba(0,0,0,0.02);
    margin-bottom: 0.75rem;
}

/* Buttons with tactile feedback */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {
    border-radius: 10px;
    font-weight: 600;
    transition: all 0.18s ease;
}
.stButton > button:hover {
    box-shadow: 0 4px 12px rgba(79, 70, 229, 0.15);
}

/* Tabs UI */
button[data-baseweb="tab"] {
    font-weight: 600;
    padding: 10px 16px;
    font-size: 0.95rem;
}

/* KPI Tiles for Dashboard */
.kpi-tile {
    text-align: center;
    padding: 18px 12px;
}
.kpi-icon {
    font-size: 2.2rem;
    margin-bottom: 4px;
    opacity: 0.85;
}
.kpi-title {
    font-size: 0.95rem;
    font-weight: 600;
    color: var(--text-muted);
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
.kpi-value {
    font-size: 2.5rem;
    font-weight: 800;
    line-height: 1.1;
    margin: 4px 0;
}
.kpi-sub {
    font-size: 0.78rem;
    color: var(--text-muted);
}

/* AI Sparkle badge */
.ai-badge {
    background: linear-gradient(135deg, #6366F1, #A855F7);
    color: white;
    font-size: 0.75rem;
    padding: 3px 8px;
    border-radius: 12px;
    font-weight: 600;
    display: inline-block;
}
</style>
""", unsafe_allow_html=True)

DB_PATH = os.environ.get("RECRUIT_DB", "recruitment.db")
STATUSES = ["Submitted", "Shortlisted", "Accepted", "Rejected"]
PENDING = ["Submitted", "Shortlisted"]
BADGE = {"Submitted": "🟡", "Shortlisted": "🔵", "Accepted": "🟢", "Rejected": "🔴"}
MAX_UPLOAD_MB = 10

# --------------------------------------------------------------------------
# Database Architecture
# --------------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  full_name TEXT, company TEXT,
  role TEXT NOT NULL CHECK(role IN ('admin','manager','vendor','employee')),
  pw_hash TEXT NOT NULL, salt TEXT NOT NULL,
  active INTEGER DEFAULT 1, created_at TEXT,
  vendor_id INTEGER, candidate_id INTEGER, designation TEXT,
  approved INTEGER DEFAULT 1,
  join_date TEXT, resigned_on TEXT, exit_date TEXT, exit_reason TEXT,
  department TEXT, fte REAL DEFAULT 1.0
);
CREATE TABLE IF NOT EXISTS jobs(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL, department TEXT, location TEXT, employment_type TEXT,
  experience TEXT, required_skills TEXT, description TEXT NOT NULL,
  openings INTEGER DEFAULT 1, status TEXT DEFAULT 'Open',
  created_by INTEGER, created_at TEXT
);
CREATE TABLE IF NOT EXISTS candidates(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  job_id INTEGER NOT NULL, vendor_id INTEGER NOT NULL,
  name TEXT NOT NULL, email TEXT NOT NULL, phone TEXT,
  resume_name TEXT, resume_blob BLOB, resume_text TEXT,
  status TEXT DEFAULT 'Submitted', decision_reason TEXT,
  decided_by INTEGER, decided_at TEXT,
  ai_score REAL, ai_details TEXT, created_at TEXT, offered_at TEXT,
  UNIQUE(job_id, email)
);
CREATE TABLE IF NOT EXISTS timesheets(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  employee_id INTEGER NOT NULL, month TEXT NOT NULL,
  status TEXT DEFAULT 'Draft',
  entries TEXT, total_hours REAL DEFAULT 0,
  submitted_at TEXT, manager_note TEXT, decided_by INTEGER, decided_at TEXT,
  created_at TEXT,
  UNIQUE(employee_id, month)
);
CREATE TABLE IF NOT EXISTS requests(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  employee_id INTEGER NOT NULL,
  kind TEXT NOT NULL,
  leave_type TEXT, start_date TEXT NOT NULL, end_date TEXT NOT NULL,
  days INTEGER, reason TEXT,
  status TEXT DEFAULT 'Pending',
  manager_note TEXT, decided_by INTEGER, decided_at TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS duplicate_flags(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  action TEXT,
  confidence TEXT,
  reasons TEXT,
  matched_id INTEGER NOT NULL,
  new_candidate_id INTEGER,
  job_id INTEGER, vendor_id INTEGER,
  name TEXT, email TEXT, phone TEXT,
  resume_name TEXT, resume_blob BLOB, resume_text TEXT,
  resolved TEXT,
  created_at TEXT
);
"""

def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def run(sql, params=(), fetch=False):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()] if fetch else None
        conn.commit()
        return rows if fetch else cur.lastrowid
    finally:
        conn.close()

def hash_pw(password, salt=None):
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000).hex()
    return h, salt

def verify_pw(password, pw_hash, salt):
    return hmac.compare_digest(hash_pw(password, salt)[0], pw_hash)

def create_user(username, password, role, full_name="", company="",
                vendor_id=None, candidate_id=None, designation="", approved=1,
                department="", fte=1.0):
    h, s_ = hash_pw(password)
    return run(
        """INSERT INTO users(username,full_name,company,role,pw_hash,salt,created_at,
           vendor_id,candidate_id,designation,approved,join_date,department,fte)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (username.strip(), full_name.strip(), company.strip(), role, h, s_, now(),
         vendor_id, candidate_id, designation, approved, date.today().isoformat(), department, fte),
    )

def migrate_users(conn):
    row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'").fetchone()
    if row and "'employee'" not in row[0]:
        conn.execute("ALTER TABLE users RENAME TO users_old")
        conn.executescript(SCHEMA)
        cols = "id,username,full_name,company,role,pw_hash,salt,active,created_at"
        conn.execute(f"INSERT INTO users({cols}) SELECT {cols} FROM users_old")
        conn.execute("DROP TABLE users_old")
        conn.commit()
    cols = [r[1] for r in conn.execute("PRAGMA table_info(users)")]
    if "approved" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN approved INTEGER DEFAULT 1")
        conn.commit()

NEW_COLUMNS = {
    "users": {"join_date": "TEXT", "resigned_on": "TEXT", "exit_date": "TEXT",
              "exit_reason": "TEXT", "department": "TEXT", "fte": "REAL DEFAULT 1.0"},
    "candidates": {"offered_at": "TEXT", "name_norm": "TEXT", "phone_norm": "TEXT", "file_hash": "TEXT", "simhash": "TEXT"},
}

def ensure_columns(conn):
    for table, cols in NEW_COLUMNS.items():
        have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        for name, ddl in cols.items():
            if name not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
    conn.commit()

@st.cache_resource
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    migrate_users(conn)
    ensure_columns(conn)
    backfill_fingerprints(conn)
    conn.executescript("""CREATE INDEX IF NOT EXISTS idx_cand_email ON candidates(email);
                          CREATE INDEX IF NOT EXISTS idx_cand_hash ON candidates(file_hash);
                          CREATE INDEX IF NOT EXISTS idx_cand_phone ON candidates(phone_norm);
                          CREATE INDEX IF NOT EXISTS idx_cand_name ON candidates(name_norm);
                          CREATE INDEX IF NOT EXISTS idx_dupflag_vendor ON duplicate_flags(vendor_id);""")
    conn.commit()
    conn.close()
    if not run("SELECT id FROM users LIMIT 1", fetch=True):
        create_user("admin", os.environ.get("ADMIN_PASSWORD", "Admin@123"), "admin", "Administrator")
    return True

CAND_COLS = """c.id, c.job_id, c.vendor_id, c.name, c.email, c.phone, c.resume_name,
  c.status, c.decision_reason, c.decided_at, c.offered_at, c.ai_score, c.ai_details, c.created_at,
  j.title AS job_title,
  COALESCE(NULLIF(u.company,''), NULLIF(u.full_name,''), u.username) AS vendor"""

def fetch_candidates(job_id=None, vendor_id=None):
    sql = (f"SELECT {CAND_COLS} FROM candidates c JOIN jobs j ON j.id=c.job_id "
           "JOIN users u ON u.id=c.vendor_id WHERE 1=1")
    params = []
    if job_id:
        sql += " AND c.job_id=?"
        params.append(job_id)
    if vendor_id:
        sql += " AND c.vendor_id=?"
        params.append(vendor_id)
    return run(sql + " ORDER BY c.created_at DESC", tuple(params), fetch=True)

# --------------------------------------------------------------------------
# Resume Parsing
# --------------------------------------------------------------------------
def extract_text(filename, data):
    ext = filename.lower().rsplit(".", 1)[-1]
    try:
        if ext == "pdf":
            from pypdf import PdfReader
            return "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages)
        if ext == "docx":
            import docx
            return "\n".join(p.text for p in docx.Document(io.BytesIO(data)).paragraphs)
        return data.decode("utf-8", errors="ignore")
    except Exception:
        return ""

# --------------------------------------------------------------------------
# Google Gemini & Multi-Model AI Engine
# --------------------------------------------------------------------------
def get_secret(name, default=None):
    if os.environ.get(name):
        return os.environ[name]
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default

def get_gemini_client():
    api_key = get_secret("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        from google import genai
        return genai.Client(api_key=api_key.strip())
    except Exception as e:
        st.warning(f"Failed to initialize Gemini Client: {e}")
        return None
      
def job_text(job):
    return " ".join(filter(None, [job["title"], job["required_skills"], job["experience"], job["description"]]))

def score_keywords(job, resume):
    skills = [s.strip().lower() for s in re.split(r"[,;\n]", job["required_skills"] or "") if s.strip()]
    if not skills:
        return 0.0, "No required skills defined on the job."
    text = resume.lower()
    matched = [s for s in skills if re.search(r"(?<![a-z0-9])" + re.escape(s) + r"(?![a-z0-9])", text)]
    missing = [s for s in skills if s not in matched]
    score = round(100 * len(matched) / len(skills), 1)
    return score, f"Matched {len(matched)}/{len(skills)}. Missing: {', '.join(missing) or 'none'}"

def score_tfidf(job, resume):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True)
    m = vec.fit_transform([job_text(job), resume])
    sim = float(cosine_similarity(m[0], m[1])[0][0])
    return round(min(100.0, sim / 0.5 * 100), 1), f"Semantic Overlap: {sim:.2f}"

def build_prompt(job, resume):
    return f"""You are an expert technical talent evaluator. Thoroughly evaluate how well this resume matches the job requirements.

JOB DETAILS:
- Title: {job['title']}
- Experience Required: {job['experience']}
- Key Skills: {job['required_skills']}
- Description: {job['description']}

CANDIDATE RESUME:
{resume[:14000]}

Rate fit strictly and realistically:
- 90-100: Exceptional direct match across all primary requirements
- 75-89: Solid candidate with relevant experience
- 50-74: Partial match with noticeable gaps
- 0-49: Poor match

Respond strictly with valid JSON with keys:
- "score": number between 0 and 100
- "summary": concise 2-sentence rationale
- "strengths": list of 2-3 key matching strengths
- "gaps": list of missing or weak areas"""

def parse_llm(text):
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError("Model response did not contain valid JSON.")
    data = json.loads(match.group(0))
    score = float(max(0, min(100, data.get("score", 0))))
    note = data.get("summary", "")
    if data.get("strengths"):
        note += " | Strengths: " + "; ".join(data["strengths"])
    if data.get("gaps"):
        note += " | Gaps: " + "; ".join(data["gaps"])
    return score, note

def score_gemini(job, resume):
    client = get_gemini_client()
    if not client:
        raise RuntimeError("GEMINI_API_KEY is not set. Add it in environment variables or .streamlit/secrets.toml")
    from google.genai import types
    model = get_secret("GEMINI_MODEL", "gemini-4-hydrogen")
    prompt = build_prompt(job, resume)
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.2,
        ),
    )
    return parse_llm(response.text)

def generate_job_description_gemini(prompt_text, company_context=""):
    """Generates structured job details from a manager's high-level prompt using Gemini."""
    client = get_gemini_client()
    if not client:
        raise RuntimeError("GEMINI_API_KEY is not configured.")
    from google.genai import types
    model = get_secret("GEMINI_MODEL", "gemini-2.5-flash")
    system_prompt = f"""You are a professional HR Director. Create a high-quality job posting based on the manager's prompt.
Company / Context: {company_context or 'Enterprise Technology'}

Manager's Request: {prompt_text}

Return STRICT JSON with these keys:
- "title": Clear professional job title
- "department": Suggested department or division
- "employment_type": One of: "Full-time", "Contract", "Part-time", "Internship"
- "experience": Clear experience string (e.g. "4-7 years")
- "required_skills": Comma-separated list of mandatory skills
- "description": Comprehensive, professional markdown job description with overview, responsibilities, and qualifications."""

    response = client.models.generate_content(
        model=model,
        contents=system_prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.4,
        ),
    )
    match = re.search(r"\{.*\}", response.text, re.S)
    if not match:
        raise ValueError("Could not parse AI response.")
    return json.loads(match.group(0))

def score_claude(job, resume):
    key = get_secret("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    import anthropic
    client = anthropic.Anthropic(api_key=key)
    msg = client.messages.create(
        model=get_secret("ANTHROPIC_MODEL", "claude-sonnet-5-5"),
        max_tokens=800,
        messages=[{"role": "user", "content": build_prompt(job, resume)}],
    )
    return parse_llm("".join(b.text for b in msg.content if b.type == "text"))

def score_openai(job, resume):
    key = get_secret("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY not set")
    from openai import OpenAI
    client = OpenAI(api_key=key)
    r = client.chat.completions.create(
        model=get_secret("OPENAI_MODEL", "gpt-4o-mini"),
        messages=[{"role": "user", "content": build_prompt(job, resume)}],
        response_format={"type": "json_object"},
    )
    return parse_llm(r.choices[0].message.content)

METHODS = {
    "Gemini 2.5 Flash (Google)": score_gemini,
    "Keyword skills match": score_keywords,
    "TF-IDF similarity": score_tfidf,
    "Claude (Anthropic)": score_claude,
    "GPT (OpenAI)": score_openai,
}

def ai_evaluate(job, resume, methods):
    if not resume.strip():
        return 0.0, [{"method": "-", "score": 0, "note": "No readable text in resume"}]
    results = []
    for m in methods:
        try:
            s, note = METHODS[m](job, resume)
            results.append({"method": m, "score": s, "note": note})
        except Exception as e:
            results.append({"method": m, "score": None, "note": f"Error: {e}"})
    ok = [r["score"] for r in results if r["score"] is not None]
    return (round(sum(ok) / len(ok), 1) if ok else None), results

# --------------------------------------------------------------------------
# UI Helpers & Components
# --------------------------------------------------------------------------
STATUS_COLORS = {"Submitted": "#F59E0B", "Shortlisted": "#3B82F6", "Accepted": "#10B981", "Rejected": "#EF4444"}
REJECT_PRESETS = ["Skills mismatch", "Experience gap", "Salary expectation",
                  "Location / notice period", "Position on hold", "Other"]

def header(icon, title, subtitle=""):
    st.markdown(f"### {icon} {title}")
    if subtitle:
        st.caption(subtitle)
    st.markdown("---")

def flash(msg):
    st.session_state["flash"] = msg

def style_fig(fig, height=360):
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=50, b=10), legend_title_text="",
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    return fig

# --------------------------------------------------------------------------
# Authentication & Sidebar
# --------------------------------------------------------------------------
ROLE_CHOICES = {
    "Hiring manager": "manager",
    "Vendor": "vendor",
    "Employee (placed through a vendor)": "employee",
}
USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{3,32}$")

def vendor_options():
    rows = run("""SELECT id, COALESCE(NULLIF(company,''), NULLIF(full_name,''), username) AS name
                  FROM users WHERE role='vendor' AND active=1 AND approved=1 ORDER BY name""", fetch=True)
    return {r["id"]: r["name"] for r in rows}

def signin_form():
    with st.form("login"):
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        if st.form_submit_button("Sign in", type="primary", use_container_width=True):
            rows = run("SELECT * FROM users WHERE username=? AND active=1", (u.strip(),), fetch=True)
            if rows and verify_pw(p, rows[0]["pw_hash"], rows[0]["salt"]):
                if not rows[0]["approved"]:
                    st.warning("Your account is pending administrator approval.")
                elif rows[0].get("exit_date") and rows[0]["exit_date"] < date.today().isoformat():
                    st.error("Employment terminated; account is closed.")
                else:
                    st.session_state.user = rows[0]
                    st.rerun()
            else:
                st.error("Invalid credentials or inactive account.")

def signup_form():
    st.caption("Select your role to view registration requirements.")
    choice = st.selectbox("I am registering as:", list(ROLE_CHOICES), index=None, placeholder="Choose your role")
    if not choice:
        return
    role = ROLE_CHOICES[choice]
    vendors = vendor_options()

    with st.form("signup", clear_on_submit=True):
        full = st.text_input("Full Name *")
        company, designation, vendor_id = "", "", None
        if role == "vendor":
            company = st.text_input("Vendor Agency / Company Name *")
        elif role == "employee":
            if vendors:
                vendor_id = st.selectbox("Vendor that placed you *", list(vendors), format_func=lambda i: vendors[i])
            else:
                st.warning("No approved vendors found. Register vendor first.")
            designation = st.text_input("Job Title / Role *")
        else:
            company = st.text_input("Department / Company")
        username = st.text_input("Username *", help="3-32 characters: letters, numbers, . _ -")
        pw = st.text_input("Password * (min 8 chars)", type="password")
        pw2 = st.text_input("Confirm Password *", type="password")

        if st.form_submit_button("Register Account", type="primary", use_container_width=True):
            uname = username.strip()
            if not full.strip() or not uname or not pw:
                st.error("Please fill in all mandatory fields.")
            elif not USERNAME_RE.match(uname):
                st.error("Username format invalid.")
            elif len(pw) < 8 or pw != pw2:
                st.error("Passwords must match and contain at least 8 characters.")
            elif role == "vendor" and not company.strip():
                st.error("Company name required for vendors.")
            elif role == "employee" and (vendor_id is None or not designation.strip()):
                st.error("Vendor and job title are required for employees.")
            elif run("SELECT 1 FROM users WHERE lower(username)=lower(?)", (uname,), fetch=True):
                st.error("Username is already taken.")
            else:
                try:
                    create_user(uname, pw, role, full, company, vendor_id=vendor_id,
                                designation=designation.strip(), approved=0)
                    st.success("Account created successfully! Awaiting admin approval.")
                except sqlite3.IntegrityError:
                    st.error("Username already taken.")

def login_view():
    _, mid, _ = st.columns([1, 1.4, 1])
    with mid:
        st.write("")
        st.image(LOGO)
        tab_in, tab_up = st.tabs(["Sign In", "Create Account"])
        with tab_in:
            signin_form()
        with tab_up:
            signup_form()
        st.caption(f"<div style='text-align:center;'>{APP_VERSION}</div>", unsafe_allow_html=True)

def sidebar_account(user):
    with st.sidebar:
        st.markdown(f"👤 **{user['full_name'] or user['username']}**")
        st.markdown(f"<span class='ai-badge'>{user['role'].upper()}</span>", unsafe_allow_html=True)
        st.write("")

        with st.expander("Security & Password"):
            old = st.text_input("Current password", type="password", key="pw_old")
            new = st.text_input("New password (min 8 chars)", type="password", key="pw_new")
            if st.button("Update Password", use_container_width=True):
                row = run("SELECT * FROM users WHERE id=?", (user["id"],), fetch=True)[0]
                if not verify_pw(old, row["pw_hash"], row["salt"]):
                    st.error("Current password incorrect.")
                elif len(new) < 8:
                    st.error("New password is too short.")
                else:
                    h, s = hash_pw(new)
                    run("UPDATE users SET pw_hash=?, salt=? WHERE id=?", (h, s, user["id"]))
                    st.success("Password updated.")
        if st.button("Sign Out", use_container_width=True):
            st.session_state.clear()
            st.rerun()

# --------------------------------------------------------------------------
# Job Management & Gemini AI Job Generator
# --------------------------------------------------------------------------
def page_jobs():
    header("📋", "Job Openings", "Create positions, generate JDs with Gemini, and track vendor submissions")
    user = st.session_state.user
    tab_list, tab_new = st.tabs(["Active Jobs", "➕ Post New Job"])

    with tab_new:
        # AI Prompt Generator Expander
        with st.expander("✨ Generate Job Description using Gemini AI", expanded=True):
            st.markdown("Enter a brief overview (e.g. *'Looking for a Senior Python/Django engineer with 5 years experience, AWS knowledge, and experience building scalable APIs'*):")
            c_prompt, c_btn = st.columns([4, 1])
            ai_prompt = c_prompt.text_area("Prompt / Summary", height=70, placeholder="Describe the role in a sentence or two...", label_visibility="collapsed")
            if c_btn.button("Generate with AI", type="secondary", use_container_width=True):
                if not ai_prompt.strip():
                    st.warning("Please enter a prompt first.")
                else:
                    with st.spinner("Gemini is drafting the job description..."):
                        try:
                            jd_data = generate_job_description_gemini(ai_prompt, company_context=user.get("company", ""))
                            st.session_state["ai_jd_generated"] = jd_data
                            st.success("Draft generated! Review and finalize below.")
                        except Exception as e:
                            st.error(f"Generation error: {e}")

        # Prefill from AI if generated
        prefill = st.session_state.get("ai_jd_generated", {})

        with st.form("new_job", clear_on_submit=True):
            c1, c2 = st.columns(2)
            title = c1.text_input("Job Title *", value=prefill.get("title", ""))
            dept = c2.text_input("Department", value=prefill.get("department", ""))
            loc = c1.text_input("Location (e.g. Remote, Hybrid, New York)")
            etype_opts = ["Full-time", "Contract", "Part-time", "Internship"]
            default_etype = prefill.get("employment_type", "Full-time")
            etype_idx = etype_opts.index(default_etype) if default_etype in etype_opts else 0
            etype = c2.selectbox("Employment Type", etype_opts, index=etype_idx)
            exp = c1.text_input("Experience Required", value=prefill.get("experience", "3-5 years"))
            openings = c2.number_input("Openings", 1, 500, 1)
            skills = st.text_area("Required Skills (comma separated)", value=prefill.get("required_skills", ""),
                                  placeholder="python, fastapi, docker, postgresql")
            desc = st.text_area("Job Description *", value=prefill.get("description", ""), height=220)

            if st.form_submit_button("Publish Job Requisition", type="primary"):
                if not title.strip() or not desc.strip():
                    st.error("Title and Description are required.")
                else:
                    run("""INSERT INTO jobs(title,department,location,employment_type,experience,
                           required_skills,description,openings,created_by,created_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?)""",
                        (title.strip(), dept, loc, etype, exp, skills, desc, openings, user["id"], now()))
                    st.session_state.pop("ai_jd_generated", None)
                    flash("Job requisition published successfully!")
                    st.rerun()

    with tab_list:
        jobs = run("""SELECT j.*, (SELECT COUNT(*) FROM candidates c WHERE c.job_id=j.id) AS submissions,
                      (SELECT COUNT(*) FROM candidates c WHERE c.job_id=j.id AND c.status='Accepted') AS accepted
                      FROM jobs j ORDER BY j.id DESC""", fetch=True)
        if not jobs:
            st.info("No job postings available. Click 'Post New Job' to create one.")
        for j in jobs:
            with st.container(border=True):
                top, btn = st.columns([5, 1])
                top.markdown(f"#### {'🟢' if j['status'] == 'Open' else '⚪'} {j['title']}")
                top.caption(f"Req #{j['id']} · {j['department'] or 'General'} · {j['location'] or 'Unspecified'} · "
                            f"{j['employment_type']} · {j['experience'] or 'Experience N/A'}")
                new_status = "Closed" if j["status"] == "Open" else "Open"
                if btn.button("Close" if new_status == "Closed" else "Re-open", key=f"js{j['id']}", use_container_width=True):
                    run("UPDATE jobs SET status=? WHERE id=?", (new_status, j["id"]))
                    st.rerun()
                m1, m2, m3 = st.columns(3)
                m1.metric("Submissions", j["submissions"])
                m2.metric("Accepted / Openings", f"{j['accepted']} / {j['openings']}")
                m3.write("")
                m3.progress(min(1.0, j["accepted"] / max(1, j["openings"])), text="Filling Ratio")
                with st.expander("Skills & Details"):
                    st.write(f"**Required Skills:** `{j['required_skills'] or 'None listed'}`")
                    st.markdown(j["description"])

# --------------------------------------------------------------------------
# Candidate Review & AI Screening
# --------------------------------------------------------------------------
def decide(cid, status, reason="", name="Candidate"):
    run("UPDATE candidates SET status=?, decision_reason=?, decided_by=?, decided_at=? WHERE id=?",
        (status, reason, st.session_state.user["id"], now(), cid))
    if status != "Accepted":
        run("UPDATE candidates SET offered_at=NULL WHERE id=?", (cid,))
    flash(f"{BADGE[status]} {name} status updated to {status}")
    st.rerun()

@st.dialog("Reject Candidate")
def reject_dialog(cid, name):
    st.write(f"Specify reason for rejecting **{name}** (visible to vendor):")
    preset = st.selectbox("Reason category", REJECT_PRESETS)
    note = st.text_area("Detailed feedback (optional)")
    if st.button("Confirm Rejection", type="primary", use_container_width=True):
        decide(cid, "Rejected", preset + (f": {note.strip()}" if note.strip() else ""), name)

def candidate_card(c, rank):
    with st.container(border=True):
        a, b, d = st.columns([3, 2, 3])
        a.markdown(f"**#{rank} · {c['name']}**  \n📧 {c['email']} · 📞 {c['phone'] or 'N/A'}")
        b.markdown(f"Supplying Vendor:  \n**{c['vendor']}**")
        if c["ai_score"] is not None:
            d.progress(min(1.0, c["ai_score"] / 100), text=f"AI Match Score: {c['ai_score']:.0f}/100")
        else:
            d.caption("Not scored yet")
        if c["decision_reason"]:
            st.caption(f"Feedback: {c['decision_reason']}")

        flag = run("SELECT id, confidence, reasons, matched_id FROM duplicate_flags WHERE new_candidate_id=? "
                   "ORDER BY id DESC LIMIT 1", (c["id"],), fetch=True)
        if flag:
            dup_banner(flag[0])

        with st.expander("📄 AI Match Analysis & Resume"):
            if c["ai_details"]:
                for r in json.loads(c["ai_details"]):
                    s = "N/A" if r["score"] is None else f"{r['score']:.0f}/100"
                    st.markdown(f"- **{r['method']}** ({s}): {r['note']}")
            else:
                st.caption("Run AI Screening to generate detailed fit analysis.")

            row = run("SELECT resume_text, resume_blob FROM candidates WHERE id=?", (c["id"],), fetch=True)[0]
            st.text_area("Extracted Resume Text", row["resume_text"] or "", height=150, disabled=True, key=f"rt{c['id']}")
            st.download_button("⬇ Download Original File", row["resume_blob"],
                               file_name=c["resume_name"], key=f"dl{c['id']}")

        b1, b2, b3, b4, _ = st.columns([1, 1, 1, 1, 2])
        if b1.button("Shortlist", key=f"sl{c['id']}", disabled=c["status"] != "Submitted"):
            decide(c["id"], "Shortlisted", "", c["name"])
        if b2.button("Accept", key=f"ac{c['id']}", type="primary", disabled=c["status"] == "Accepted"):
            decide(c["id"], "Accepted", "", c["name"])
        if b3.button("Reject", key=f"rj{c['id']}", disabled=c["status"] == "Rejected"):
            reject_dialog(c["id"], c["name"])
        if c["status"] in ("Accepted", "Rejected") and b4.button("Re-open", key=f"ro{c['id']}"):
            decide(c["id"], "Submitted", "", c["name"])

        if c["status"] == "Accepted":
            emp = run("SELECT username FROM users WHERE candidate_id=?", (c["id"],), fetch=True)
            if emp:
                st.caption(f"✅ Onboarded - User Login: `{emp[0]['username']}`")
            else:
                o1, o2, _ = st.columns([1.5, 1.8, 3])
                if c["offered_at"]:
                    o1.caption(f"Offer Issued: {c['offered_at'][:10]}")
                elif o1.button("Mark Offer Released", key=f"of{c['id']}"):
                    run("UPDATE candidates SET offered_at=? WHERE id=?", (now(), c["id"]))
                    flash(f"Offer marked as released for {c['name']}")
                    st.rerun()
                if o2.button("🪪 Onboard to Employee", key=f"ob{c['id']}"):
                    onboard_dialog(c)

def page_review():
    header("🗂️", "Candidate Pipeline & AI Scoring", "Screen profiles, evaluate with Gemini AI, and track decisions")
    jobs = run("SELECT id,title,status FROM jobs ORDER BY id DESC", fetch=True)
    if not jobs:
        st.info("No active jobs found.")
        return
    lookup = {j["id"]: j for j in jobs}
    job_id = st.selectbox("Select Job Position", list(lookup),
                          format_func=lambda i: f"Req #{i} · {lookup[i]['title']} ({lookup[i]['status']})")
    job = run("SELECT * FROM jobs WHERE id=?", (job_id,), fetch=True)[0]

    with st.expander("🤖 Automated AI Screening & Scoring Options", expanded=True):
        c_m, c_opt = st.columns([3, 1])
        default_methods = ["Gemini 2.5 Flash (Google)"] if get_secret("GEMINI_API_KEY") else ["Keyword skills match", "TF-IDF similarity"]
        methods = c_m.multiselect("Active AI Evaluation Engines", list(METHODS), default=default_methods)
        rescore = c_opt.checkbox("Re-score evaluated profiles", value=False)
        if st.button("Run AI Screening", type="primary", disabled=not methods):
            targets = [c for c in fetch_candidates(job_id=job_id) if rescore or c["ai_score"] is None]
            if not targets:
                st.info("All candidates evaluated.")
            else:
                bar = st.progress(0.0, text="Evaluating resumes with AI...")
                failed = 0
                for i, c in enumerate(targets):
                    text = run("SELECT resume_text FROM candidates WHERE id=?", (c["id"],), fetch=True)[0]["resume_text"] or ""
                    score, details = ai_evaluate(job, text, methods)
                    if score is None:
                        failed += 1
                    else:
                        run("UPDATE candidates SET ai_score=?, ai_details=? WHERE id=?",
                            (score, json.dumps(details), c["id"]))
                    bar.progress((i + 1) / len(targets), text=f"Scored {i + 1} of {len(targets)}")
                st.success(f"Successfully evaluated {len(targets) - failed} candidate(s).")
                if failed:
                    st.warning(f"{failed} evaluation(s) failed. Check API credentials.")
                st.rerun()

    all_cands = fetch_candidates(job_id=job_id)
    if not all_cands:
        st.info("No candidates submitted for this position yet.")
        return

    q = st.text_input("🔍 Quick filter by candidate name, email, or agency...", placeholder="Search profiles...").strip().lower()
    cands = [c for c in all_cands if not q or q in f"{c['name']} {c['email']} {c['vendor']}".lower()]

    blocked = run("""SELECT f.id, f.reasons, f.matched_id, f.name, f.email, f.created_at,
                     COALESCE(NULLIF(u.company,''), NULLIF(u.full_name,''), u.username) AS vendor
                     FROM duplicate_flags f JOIN users u ON u.id=f.vendor_id
                     WHERE f.job_id=? AND f.action='Blocked' AND f.resolved IS NULL ORDER BY f.id DESC""",
                  (job_id,), fetch=True)

    tabs = st.tabs([f"{BADGE[s]} {s} ({sum(c['status'] == s for c in cands)})" for s in STATUSES]
                   + [f"🔁 Duplicates ({len(blocked)})"])
    for tab, status in zip(tabs[:-1], STATUSES):
        with tab:
            items = sorted([c for c in cands if c["status"] == status],
                           key=lambda c: (c["ai_score"] is None, -(c["ai_score"] or 0)))
            if status == "Submitted" and items:
                with st.expander("⚡ Batch Decision Actions"):
                    thr = st.slider("Auto-reject candidates scoring below:", 0, 100, 35)
                    if st.button("Reject Low Fit Candidates", type="secondary"):
                        count = 0
                        for c in all_cands:
                            if c["status"] == "Submitted" and c["ai_score"] is not None and c["ai_score"] < thr:
                                run("UPDATE candidates SET status='Rejected', decision_reason=?, decided_by=?, decided_at=? WHERE id=?",
                                    (f"Below AI threshold ({thr})", st.session_state.user["id"], now(), c["id"]))
                                count += 1
                        flash(f"Rejected {count} candidate(s) below match threshold {thr}")
                        st.rerun()
            if not items:
                st.caption("No profiles currently in this stage.")
            for rank, c in enumerate(items, 1):
                candidate_card(c, rank)
    with tabs[-1]:
        duplicates_tab(blocked)

# --------------------------------------------------------------------------
# Analytics & Vendor Performance Dashboard
# --------------------------------------------------------------------------
def page_dashboard():
    header("📊", "Vendor Performance & Metrics", "Submission quality, duplicate frequency, and selection rates")
    jobs = run("SELECT id,title FROM jobs ORDER BY id DESC", fetch=True)
    lookup = {0: "All Jobs", **{j["id"]: f"Req #{j['id']} · {j['title']}" for j in jobs}}
    job_id = st.selectbox("Filter by Position", list(lookup), format_func=lambda i: lookup[i])
    df = pd.DataFrame(fetch_candidates(job_id=job_id or None))
    if df.empty:
        st.info("No candidate submissions recorded yet.")
        return

    total = len(df)
    acc = int((df.status == "Accepted").sum())
    rej = int((df.status == "Rejected").sum())
    pend = int(df.status.isin(PENDING).sum())

    m = st.columns(4)
    m[0].metric("Total Submissions", total)
    m[1].metric("Accepted", f"{acc} ({acc/total:.0%})")
    m[2].metric("Rejected", f"{rej} ({rej/total:.0%})")
    m[3].metric("In Review", pend)

    g = df.groupby("vendor")
    out = pd.DataFrame({
        "Submitted": g.size(),
        "Pending": g.status.apply(lambda s: int(s.isin(PENDING).sum())),
        "Accepted": g.status.apply(lambda s: int((s == "Accepted").sum())),
        "Rejected": g.status.apply(lambda s: int((s == "Rejected").sum())),
        "Avg AI Match": g.ai_score.mean().round(1),
    })
    out["Accepted %"] = (out["Accepted"] / out["Submitted"] * 100).round(1)
    out["Rejected %"] = (out["Rejected"] / out["Submitted"] * 100).round(1)
    decided = (out["Accepted"] + out["Rejected"]).where(lambda x: x > 0)
    out["Acceptance Ratio"] = (out["Accepted"] / decided * 100).round(1)

    dq = ("SELECT COALESCE(NULLIF(u.company,''), NULLIF(u.full_name,''), u.username) AS vendor, COUNT(*) AS n "
          "FROM duplicate_flags f JOIN users u ON u.id=f.vendor_id WHERE f.action='Blocked'"
          + (" AND f.job_id=?" if job_id else "") + " GROUP BY 1")
    dup_counts = {r["vendor"]: r["n"] for r in run(dq, (job_id,) if job_id else (), fetch=True)}
    out["Duplicates Blocked"] = [dup_counts.get(v, 0) for v in out.index]
    out["Duplicate %"] = (out["Duplicates Blocked"] / (out["Submitted"] + out["Duplicates Blocked"]) * 100).round(1)
    out = out.sort_values("Accepted %", ascending=False).reset_index().rename(columns={"vendor": "Agency / Vendor"})

    st.subheader("Agency Performance Breakdown")
    pct = lambda label: st.column_config.ProgressColumn(label, min_value=0, max_value=100, format="%.1f%%")
    st.dataframe(out, hide_index=True, column_config={
        "Accepted %": pct("Accepted %"),
        "Rejected %": pct("Rejected %"),
        "Acceptance Ratio": pct("Acceptance Ratio"),
        "Avg AI Match": pct("Avg AI Match"),
        "Duplicate %": pct("Duplicate %"),
    })

    c1, c2 = st.columns([3, 2])
    with c1:
        fig = px.bar(out, x="Agency / Vendor", y=["Accepted %", "Rejected %"], barmode="group", text_auto=".1f",
                     color_discrete_map={"Accepted %": STATUS_COLORS["Accepted"], "Rejected %": STATUS_COLORS["Rejected"]},
                     labels={"value": "Percentage of Submissions", "variable": "Status"}, title="Conversion vs Rejection by Agency")
        st.plotly_chart(style_fig(fig))
    with c2:
        mix = df.groupby("status").size().reset_index(name="count")
        fig = px.pie(mix, names="status", values="count", hole=0.55, color="status",
                     color_discrete_map=STATUS_COLORS, title="Candidate Pool Status Distribution")
        st.plotly_chart(style_fig(fig))

# --------------------------------------------------------------------------
# User Management & Bulk Utilities
# --------------------------------------------------------------------------
USER_ALIASES = {
    "name": "full_name", "contact": "full_name", "contact_name": "full_name",
    "vendor": "company", "vendor_name": "company", "company_name": "company",
}

def read_sheet(f):
    try:
        if f.name.lower().endswith(".csv"):
            try:
                raw = pd.read_csv(f, dtype=str, keep_default_na=False, encoding="utf-8-sig")
            except UnicodeDecodeError:
                f.seek(0)
                raw = pd.read_csv(f, dtype=str, keep_default_na=False, encoding="latin-1")
        else:
            raw = pd.read_excel(f, dtype=str)
    except Exception as e:
        return None, f"File format error: {e}"
    if len(raw) > 2000:
        return None, "Upload limited to 2,000 rows."
    return raw, None

def user_import_template(role):
    if role == "vendor":
        rows = [{"company": "TechStaff Solutions", "full_name": "Rohan Gupta", "username": ""}]
    else:
        rows = [{"full_name": "Anita Roy", "company": "Product Engineering", "username": ""}]
    return pd.DataFrame(rows).to_csv(index=False)

def validate_users_import(raw, role):
    df = raw.copy()
    df.columns = [USER_ALIASES.get(k, k) for k in (re.sub(r"[\s\-]+", "_", str(c).strip().lower()) for c in df.columns)]
    df = df.loc[:, ~df.columns.duplicated()]
    req = "company" if role == "vendor" else "full_name"
    if req not in df.columns:
        return [], f"Missing required column: {req}"
    for c in ("full_name", "company", "username"):
        if c not in df.columns:
            df[c] = ""
    df = df.fillna("").astype(str)

    used = {r["username"].lower() for r in run("SELECT username FROM users", fetch=True)}
    rows = []
    for i, r in df.iterrows():
        if not any(str(x).strip() for x in r.values):
            continue
        errs = []
        full, company, explicit = r["full_name"].strip(), r["company"].strip(), r["username"].strip()
        if role == "vendor" and not company:
            errs.append("company required")
        elif role != "vendor" and not full:
            errs.append("full_name required")

        uname = ""
        if explicit:
            if not USERNAME_RE.match(explicit) or explicit.lower() in used:
                errs.append("username invalid or taken")
            else:
                uname = explicit
        else:
            base = re.sub(r"[^a-z0-9._-]", "", (company if role == "vendor" else full).lower().replace(" ", "."))[:24] or "user"
            uname = base
            cnt = 2
            while uname.lower() in used:
                uname = f"{base}{cnt}"
                cnt += 1
        if not errs:
            used.add(uname.lower())
        rows.append({"row": i + 2, "full_name": full or company, "company": company, "username": uname, "error": "; ".join(errs)})
    return rows, None

def run_users_import(rows, role):
    creds, failed = [], []
    for r in rows:
        pw = secrets.token_urlsafe(9)
        try:
            create_user(r["username"], pw, role, r["full_name"], r["company"])
            creds.append({"Name": r["full_name"], "Company": r["company"], "Username": r["username"], "Temporary Password": pw})
        except sqlite3.IntegrityError:
            failed.append(f"Row {r['row']}: username conflict.")
    return {"creds": pd.DataFrame(creds), "failed": failed}

def bulk_users_tab(role):
    label = "Vendors" if role == "vendor" else "Managers"
    rk = f"bulkU_res_{role}"
    if rk in st.session_state:
        res = st.session_state[rk]
        st.success(f"Successfully created {len(res['creds'])} {label}.")
        if not res["creds"].empty:
            st.dataframe(res["creds"], hide_index=True)
            st.download_button("⬇ Download Credentials (CSV)", res["creds"].to_csv(index=False), file_name=f"{role}_credentials.csv")
        if st.button("Upload Another File"):
            del st.session_state[rk]
            st.rerun()
        return

    st.download_button("⬇ Download CSV Template", user_import_template(role), file_name=f"{role}_template.csv")
    f = st.file_uploader(f"Upload {label} Spreadsheet", type=["csv", "xlsx"], key=f"f_{role}")
    if f:
        raw, err = read_sheet(f)
        if err:
            st.error(err)
            return
        rows, fatal = validate_users_import(raw, role)
        if fatal:
            st.error(fatal)
            return
        ready = [r for r in rows if not r["error"]]
        st.caption(f"{len(ready)} of {len(rows)} rows ready for import.")
        if ready and st.button(f"Import {len(ready)} Records", type="primary"):
            st.session_state[rk] = run_users_import(ready, role)
            st.rerun()

def page_users():
    header("👥", "User & Role Directory", "Approve self-registrations, provision roles, and batch import")
    pending = run("SELECT * FROM users WHERE approved=0 ORDER BY created_at", fetch=True)
    all_vendors = {r["id"]: r["name"] for r in run(
        """SELECT id, COALESCE(NULLIF(company,''), NULLIF(full_name,''), username) AS name
           FROM users WHERE role='vendor'""", fetch=True)}

    tab_list, tab_pending, tab_new, tab_bulk = st.tabs(
        ["Active Users", f"⏳ Pending Approvals ({len(pending)})", "➕ New User", "⬆ Bulk Provisioning"])

    with tab_pending:
        if not pending:
            st.caption("No account registrations waiting for review.")
        for u in pending:
            with st.container(border=True):
                a, b, c = st.columns([5, 1, 1])
                detail = f"Vendor: {all_vendors.get(u['vendor_id'], 'N/A')}" if u['role'] == "employee" else f"Company: {u['company'] or 'N/A'}"
                a.markdown(f"**{u['full_name']}** (`{u['username']}`) · Role: **{u['role']}**  \n{detail} · Registered: {u['created_at']}")
                if b.button("Approve", key=f"ap{u['id']}", type="primary"):
                    run("UPDATE users SET approved=1, join_date=? WHERE id=?", (date.today().isoformat(), u["id"]))
                    flash(f"Approved {u['username']}")
                    st.rerun()
                if c.button("Reject", key=f"rjs{u['id']}"):
                    run("DELETE FROM users WHERE id=? AND approved=0", (u["id"],))
                    flash(f"Rejected registration for {u['username']}")
                    st.rerun()

    with tab_new:
        vendors = vendor_options()
        with st.form("create_single_user", clear_on_submit=True):
            c1, c2 = st.columns(2)
            username = c1.text_input("Username *")
            role = c2.selectbox("Role", ["manager", "vendor", "employee", "admin"])
            full = c1.text_input("Full Name *")
            company = c2.text_input("Company / Organization")
            vendor_id = c1.selectbox("Vendor (for employees only)", list(vendors), index=None,
                                     format_func=lambda i: vendors[i]) if vendors and role == "employee" else None
            pw = st.text_input("Temporary Password * (min 8 chars)", type="password")
            if st.form_submit_button("Create User Account", type="primary"):
                if not username.strip() or len(pw) < 8:
                    st.error("Username and 8+ char password are required.")
                else:
                    try:
                        create_user(username, pw, role, full, company, vendor_id=vendor_id)
                        flash(f"Created account for {username}")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("Username already taken.")

    with tab_bulk:
        kind = st.radio("Bulk import category:", ["Vendors", "Hiring Managers", "Employees"], horizontal=True)
        if kind == "Vendors":
            bulk_users_tab("vendor")
        elif kind == "Hiring Managers":
            bulk_users_tab("manager")
        else:
            bulk_import_tab()

    with tab_list:
        users = run("SELECT id,username,full_name,company,role,active,approved,created_at FROM users ORDER BY id", fetch=True)
        st.dataframe(pd.DataFrame(users), hide_index=True)

# --------------------------------------------------------------------------
# Vendor Portal
# --------------------------------------------------------------------------
def page_vendor_submit():
    header("📤", "Submit Candidate Resumes", "Select open requirements and upload qualified profiles")
    user = st.session_state.user
    jobs = run("SELECT * FROM jobs WHERE status='Open' ORDER BY id DESC", fetch=True)
    if not jobs:
        st.info("No active openings currently open for agency submissions.")
        return
    lookup = {j["id"]: j for j in jobs}
    jid = st.selectbox("Open Position", list(lookup),
                       format_func=lambda i: f"Req #{i} · {lookup[i]['title']} - {lookup[i]['location'] or 'Location flexible'}")
    j = lookup[jid]

    with st.container(border=True):
        st.markdown(f"#### {j['title']}")
        st.caption(f"{j['employment_type']} · {j['experience'] or 'Experience N/A'} · {j['openings']} opening(s)")
        st.write(f"**Required Competencies:** `{j['required_skills'] or 'See description'}`")
        with st.expander("Full Requisition Description"):
            st.markdown(j["description"])

    with st.form("submit_candidate", clear_on_submit=True):
        c1, c2 = st.columns(2)
        name = c1.text_input("Candidate Full Name *")
        email = c2.text_input("Email Address *")
        phone = c1.text_input("Phone Number")
        f = st.file_uploader("Candidate Resume (PDF, DOCX, TXT) *", type=["pdf", "docx", "txt"])

        if st.form_submit_button("Submit Candidate to Requisition", type="primary"):
            if not name.strip() or not email.strip() or f is None:
                st.error("Name, email, and resume file are mandatory.")
            elif f.size > MAX_UPLOAD_MB * 1024 * 1024:
                st.error(f"File exceeds maximum upload size of {MAX_UPLOAD_MB}MB.")
            else:
                data = f.getvalue()
                text = extract_text(f.name, data)
                em, nm = email.strip().lower(), name.strip()
                matches = find_duplicates(jid, nm, em, phone, data, text)
                top = matches[0] if matches else None

                if top and duplicate_action(top, jid) == "Blocked":
                    record_flag("Blocked", top, jid, user["id"], nm, em, phone, resume=(f.name, data, text))
                    st.error("🚫 **Duplicate profile detected.** " + vendor_alert_text(top, user["id"], nm))
                else:
                    fp = make_fingerprints(nm, phone, data, text)
                    try:
                        cid = run("""INSERT INTO candidates(job_id,vendor_id,name,email,phone,resume_name,resume_blob,
                                     resume_text,created_at,name_norm,phone_norm,file_hash,simhash)
                                     VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                                  (jid, user["id"], nm, em, phone, f.name, data, text, now(),
                                   fp["name_norm"], fp["phone_norm"], fp["file_hash"], fp["simhash"]))
                        if top:
                            record_flag("Flagged", top, jid, user["id"], nm, em, phone, new_cid=cid)
                            st.warning("⚠️ Candidate submitted but flagged as a potential profile duplicate for the hiring manager.")
                        else:
                            st.success(f"Candidate {nm} successfully submitted!")
                    except sqlite3.IntegrityError:
                        st.error("A candidate with this email was already submitted for this requisition.")

def page_vendor_mine():
    header("📁", "Agency Submission Tracker", "Status tracking for profiles submitted by your organization")
    vendor_alerts_section(st.session_state.user["id"])
    rows = fetch_candidates(vendor_id=st.session_state.user["id"])
    if not rows:
        st.info("No candidates submitted yet.")
        return
    df = pd.DataFrame(rows)[["job_title", "name", "email", "status", "decision_reason", "created_at"]]
    df["status"] = df["status"].map(lambda s: f"{BADGE.get(s, '')} {s}")
    st.dataframe(df, hide_index=True)

# --------------------------------------------------------------------------
# Employee Timesheets & Leave Management
# --------------------------------------------------------------------------
TS_BADGE = {"Not started": "⚪", "Draft": "📝", "Submitted": "🟡", "Approved": "🟢", "Rejected": "🔴"}
RQ_BADGE = {"Pending": "🟡", "Approved": "🟢", "Rejected": "🔴", "Cancelled": "⚪"}
DAY_TYPES = ["Office", "WFH", "Leave", "Holiday", "Off"]
LEAVE_TYPES = ["Casual", "Sick", "Annual", "Unpaid", "Other"]

def month_options(n=6):
    d = date.today()
    y, m, out = d.year, d.month, []
    for _ in range(n):
        out.append(f"{y}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out

def month_label(ym):
    y, m = map(int, ym.split("-"))
    return f"{calendar.month_name[m]} {y}"

def count_workdays(start, end):
    d, n = start, 0
    while d <= end:
        if d.weekday() < 5:
            n += 1
        d += timedelta(days=1)
    return n

def approved_days(emp_id, ym):
    y, m = map(int, ym.split("-"))
    first, last = date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])
    rows = run("""SELECT kind,start_date,end_date FROM requests
                  WHERE employee_id=? AND status='Approved' AND start_date<=? AND end_date>=?""",
               (emp_id, last.isoformat(), first.isoformat()), fetch=True)
    out = {}
    for r in rows:
        d = max(date.fromisoformat(r["start_date"]), first)
        end = min(date.fromisoformat(r["end_date"]), last)
        while d <= end:
            if d.weekday() < 5:
                out[d.isoformat()] = r["kind"]
            d += timedelta(days=1)
    return out

def default_grid(emp_id, ym):
    y, m = map(int, ym.split("-"))
    marks = approved_days(emp_id, ym)
    rows = []
    for day in range(1, calendar.monthrange(y, m)[1] + 1):
        d = date(y, m, day)
        iso = d.isoformat()
        if d.weekday() >= 5:
            typ, hrs = "Off", 0.0
        elif iso in marks:
            typ = marks[iso]
            hrs = 0.0 if typ == "Leave" else 8.0
        else:
            typ, hrs = "Office", 8.0
        rows.append({"Date": iso, "Day": d.strftime("%a"), "Type": typ, "Hours": hrs, "Notes": ""})
    return pd.DataFrame(rows)

def ts_summary(entries):
    df = pd.DataFrame(entries)
    if df.empty:
        return {"hours": 0.0, "office": 0, "wfh": 0, "leave": 0}
    h = df["Hours"].fillna(0)
    return {"hours": float(h.sum()),
            "office": int(((df["Type"] == "Office") & (h > 0)).sum()),
            "wfh": int(((df["Type"] == "WFH") & (h > 0)).sum()),
            "leave": int((df["Type"] == "Leave").sum())}

def save_timesheet(emp_id, ym, df, submit):
    entries = json.loads(df.fillna({"Hours": 0, "Notes": ""}).to_json(orient="records"))
    total = round(sum(float(e["Hours"]) for e in entries), 2)
    cur = run("SELECT id FROM timesheets WHERE employee_id=? AND month=?", (emp_id, ym), fetch=True)
    if not cur:
        run("""INSERT INTO timesheets(employee_id,month,status,entries,total_hours,submitted_at,created_at)
               VALUES(?,?,?,?,?,?,?)""",
            (emp_id, ym, "Submitted" if submit else "Draft", json.dumps(entries), total, now() if submit else None, now()))
    elif submit:
        run("""UPDATE timesheets SET entries=?, total_hours=?, status='Submitted', submitted_at=?,
               manager_note=NULL, decided_by=NULL, decided_at=NULL WHERE id=?""",
            (json.dumps(entries), total, now(), cur[0]["id"]))
    else:
        run("UPDATE timesheets SET entries=?, total_hours=? WHERE id=?", (json.dumps(entries), total, cur[0]["id"]))

@st.dialog("Onboard as Employee")
def onboard_dialog(c):
    st.write(f"Create login credentials for **{c['name']}**:")
    default = re.sub(r"[^a-z0-9.]", "", c["name"].lower().replace(" ", "."))
    username = st.text_input("Username", value=default)
    pw = st.text_input("Temporary password (min 8 chars)", type="password")
    if st.button("Generate Login & Onboard", type="primary", use_container_width=True):
        if not username.strip() or len(pw) < 8:
            st.error("Username and 8+ char password required.")
        else:
            try:
                job = run("SELECT department, employment_type FROM jobs WHERE id=?", (c["job_id"],), fetch=True)[0]
                create_user(username, pw, "employee", c["name"], c["vendor"], vendor_id=c["vendor_id"],
                            candidate_id=c["id"], designation=c["job_title"],
                            department=job["department"] or "", fte=1.0)
                flash(f"Employee {c['name']} successfully onboarded!")
                st.rerun()
            except sqlite3.IntegrityError:
                st.error("Username already taken.")

def page_emp_timesheet():
    header("🗓️", "Monthly Timesheet", "Log hours, review approvals, and submit for manager sign-off")
    user = st.session_state.user
    ym = st.selectbox("Select Month", month_options(), format_func=month_label)
    found = run("SELECT * FROM timesheets WHERE employee_id=? AND month=?", (user["id"], ym), fetch=True)
    ts = found[0] if found else None
    status = ts["status"] if ts else "Not started"
    st.markdown(f"**Current Status:** {TS_BADGE[status]} `{status}`")
    locked = status in ("Submitted", "Approved")

    df = pd.DataFrame(json.loads(ts["entries"])) if ts else default_grid(user["id"], ym)
    edited = st.data_editor(
        df, key=f"ts_{ym}_{status}", hide_index=True, num_rows="fixed",
        disabled=True if locked else ["Date", "Day"],
        column_config={
            "Type": st.column_config.SelectboxColumn("Type", options=DAY_TYPES, required=True),
            "Hours": st.column_config.NumberColumn("Hours", min_value=0, max_value=24, step=0.5, format="%.1f"),
            "Notes": st.column_config.TextColumn("Notes"),
        },
    )
    s = ts_summary(json.loads(edited.fillna({"Hours": 0, "Notes": ""}).to_json(orient="records")))
    m = st.columns(4)
    m[0].metric("Total Hours", f"{s['hours']:.1f}")
    m[1].metric("Office Days", s["office"])
    m[2].metric("WFH Days", s["wfh"])
    m[3].metric("Leave Days", s["leave"])

    if not locked:
        c1, c2, _ = st.columns([1, 1.5, 3])
        if c1.button("💾 Save Draft", use_container_width=True):
            save_timesheet(user["id"], ym, edited, submit=False)
            flash("Draft saved.")
            st.rerun()
        if c2.button("📨 Submit for Approval", type="primary", use_container_width=True):
            save_timesheet(user["id"], ym, edited, submit=True)
            flash("Timesheet submitted.")
            st.rerun()

def page_emp_requests():
    header("🏠", "Leave & Remote Requests", "Submit vacation, sick leave, or work-from-home applications")
    user = st.session_state.user
    with st.form("new_request", clear_on_submit=True):
        kind = st.radio("Request Category", ["Leave", "WFH"], horizontal=True)
        leave_type = st.selectbox("Leave Type", LEAVE_TYPES) if kind == "Leave" else None
        c1, c2 = st.columns(2)
        start = c1.date_input("Start Date", value=date.today())
        end = c2.date_input("End Date", value=date.today())
        reason = st.text_area("Justification / Note *")
        if st.form_submit_button("Submit Request", type="primary"):
            if end < start:
                st.error("End date cannot precede start date.")
            elif not reason.strip():
                st.error("Please provide a note or reason.")
            else:
                run("""INSERT INTO requests(employee_id,kind,leave_type,start_date,end_date,days,reason,created_at)
                       VALUES(?,?,?,?,?,?,?,?)""",
                    (user["id"], kind, leave_type, start.isoformat(), end.isoformat(), count_workdays(start, end), reason.strip(), now()))
                flash("Request submitted to your manager.")
                st.rerun()

    mine = run("SELECT * FROM requests WHERE employee_id=? ORDER BY id DESC", (user["id"],), fetch=True)
    if mine:
        st.subheader("Request History")
        st.dataframe(pd.DataFrame(mine)[["kind", "leave_type", "start_date", "end_date", "days", "status", "reason"]], hide_index=True)

# --------------------------------------------------------------------------
# Approvals (Manager / Admin)
# --------------------------------------------------------------------------
TS_SQL = """SELECT t.*, COALESCE(NULLIF(e.full_name,''), e.username) AS employee,
            COALESCE(NULLIF(v.company,''), NULLIF(v.full_name,''), v.username, '-') AS vendor
            FROM timesheets t JOIN users e ON e.id=t.employee_id LEFT JOIN users v ON v.id=e.vendor_id"""
RQ_SQL = """SELECT r.*, COALESCE(NULLIF(e.full_name,''), e.username) AS employee,
            COALESCE(NULLIF(v.company,''), NULLIF(v.full_name,''), v.username, '-') AS vendor
            FROM requests r JOIN users e ON e.id=r.employee_id LEFT JOIN users v ON v.id=e.vendor_id"""

def decide_item(table, item_id, status, note, label):
    run(f"UPDATE {table} SET status=?, manager_note=?, decided_by=?, decided_at=? WHERE id=?",
        (status, note, st.session_state.user["id"], now(), item_id))
    flash(f"{label} marked as {status}")
    st.rerun()

def page_approvals():
    header("✅", "Pending Management Approvals", "Review submitted monthly timesheets and time-off requests")
    pend_ts = run(TS_SQL + " WHERE t.status='Submitted' ORDER BY t.submitted_at", fetch=True)
    pend_rq = run(RQ_SQL + " WHERE r.status='Pending' ORDER BY r.created_at", fetch=True)
    tab_ts, tab_rq = st.tabs([f"🗓️ Timesheets ({len(pend_ts)})", f"🏠 Leave & WFH ({len(pend_rq)})"])

    with tab_ts:
        if not pend_ts:
            st.caption("No timesheets awaiting review.")
        for t in pend_ts:
            with st.container(border=True):
                a, b = st.columns([4, 1])
                a.markdown(f"**{t['employee']}** ({t['vendor']}) · {month_label(t['month'])} · Total: **{t['total_hours']:.1f} hrs**")
                if b.button("Approve", key=f"app_ts_{t['id']}", type="primary"):
                    decide_item("timesheets", t["id"], "Approved", "", "Timesheet")
    with tab_rq:
        if not pend_rq:
            st.caption("No leave or WFH requests pending.")
        for r in pend_rq:
            with st.container(border=True):
                a, b = st.columns([4, 1])
                a.markdown(f"**{r['employee']}** · {r['kind']} ({r['days']} days) from {r['start_date']} to {r['end_date']}  \n*Reason: {r['reason']}*")
                if b.button("Approve", key=f"app_rq_{r['id']}", type="primary"):
                    decide_item("requests", r["id"], "Approved", "", "Request")

# --------------------------------------------------------------------------
# Vendor Timesheet Overview
# --------------------------------------------------------------------------
def page_vendor_timesheets():
    header("🧾", "Placed Team Timesheets", "Approved timesheet summaries for personnel supplied by your agency")
    uid = st.session_state.user["id"]
    rows = run(TS_SQL + " WHERE e.vendor_id=? AND t.status='Approved' ORDER BY t.month DESC", (uid,), fetch=True)
    if not rows:
        st.info("No approved timesheets found.")
        return
    st.dataframe(pd.DataFrame(rows)[["employee", "month", "total_hours", "status", "decided_at"]], hide_index=True)

# --------------------------------------------------------------------------
# Duplicate Detection Utilities
# --------------------------------------------------------------------------
SIM_HIGH, SIM_POSSIBLE, HAMMING_PREFILTER = 0.85, 0.60, 14

def _tokens(text):
    return re.findall(r"[a-z0-9]+", (text or "").lower())

def norm_name(name):
    return " ".join(sorted(re.findall(r"[a-z]+", (name or "").lower())))

def norm_phone(phone):
    d = re.sub(r"\D", "", phone or "")
    return d[-10:] if len(d) >= 10 else ""

def simhash_hex(text):
    toks = _tokens(text)
    if len(toks) < 60:
        return ""
    v = [0] * 64
    for i in range(len(toks) - 2):
        h = int.from_bytes(hashlib.blake2b(" ".join(toks[i:i + 3]).encode(), digest_size=8).digest(), "big")
        for b in range(64):
            v[b] += 1 if (h >> b) & 1 else -1
    return f"{sum(1 << b for b in range(64) if v[b] > 0):016x}"

def hamming(a_hex, b_hex):
    return bin(int(a_hex, 16) ^ int(b_hex, 16)).count("1")

def shingle_set(text, n=3):
    toks = _tokens(text)
    return {" ".join(toks[i:i + n]) for i in range(max(0, len(toks) - n + 1))}

def jaccard(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0

def make_fingerprints(name, phone, data, text):
    return {"name_norm": norm_name(name), "phone_norm": norm_phone(phone),
            "file_hash": hashlib.sha256(data).hexdigest() if data else "", "simhash": simhash_hex(text)}

def backfill_fingerprints(conn):
    rows = conn.execute("SELECT id, name, phone, resume_blob, resume_text FROM candidates WHERE file_hash IS NULL").fetchall()
    for cid, name, phone, blob, text in rows:
        fp = make_fingerprints(name, phone, blob, text)
        conn.execute("UPDATE candidates SET name_norm=?, phone_norm=?, file_hash=?, simhash=? WHERE id=?",
                     (fp["name_norm"], fp["phone_norm"], fp["file_hash"], fp["simhash"], cid))
    conn.commit()

MATCH_COLS = """c.id, c.job_id, c.vendor_id, c.name, c.email, c.status, c.decision_reason, c.offered_at,
    c.created_at, c.name_norm, c.phone_norm, c.file_hash, c.simhash, j.title AS job_title,
    COALESCE(NULLIF(u.company,''), NULLIF(u.full_name,''), u.username) AS vendor,
    (SELECT COUNT(*) FROM users e WHERE e.candidate_id=c.id) AS joined"""
MATCH_FROM = " FROM candidates c JOIN jobs j ON j.id=c.job_id JOIN users u ON u.id=c.vendor_id"

def get_match(cid):
    r = run("SELECT " + MATCH_COLS + MATCH_FROM + " WHERE c.id=?", (cid,), fetch=True)
    return r[0] if r else None

def find_duplicates(job_id, name, email, phone, data, text):
    fp = make_fingerprints(name, phone, data, text)
    em = (email or "").strip().lower()
    conds, params = ["c.email=?"], [em]
    for col, val in (("c.file_hash", fp["file_hash"]), ("c.phone_norm", fp["phone_norm"]), ("c.name_norm", fp["name_norm"])):
        if val:
            conds.append(f"{col}=?")
            params.append(val)
    pool = {r["id"]: r for r in run("SELECT " + MATCH_COLS + MATCH_FROM + " WHERE " + " OR ".join(conds),
                                    tuple(params), fetch=True)}
    if fp["simhash"]:
        for r in run("SELECT " + MATCH_COLS + MATCH_FROM + " WHERE c.simhash IS NOT NULL AND c.simhash<>''", fetch=True):
            if hamming(fp["simhash"], r["simhash"]) <= HAMMING_PREFILTER:
                pool[r["id"]] = r
    new_shingles = shingle_set(text) if fp["simhash"] else set()

    out = []
    for r in pool.values():
        reasons, high, possible = [], False, False
        if r["email"] == em:
            reasons.append("identical email"); high = True
        if fp["phone_norm"] and r["phone_norm"] == fp["phone_norm"]:
            reasons.append("identical phone"); high = True
        if fp["file_hash"] and r["file_hash"] == fp["file_hash"]:
            reasons.append("identical file contents"); high = True
        if new_shingles and r["simhash"] and hamming(fp["simhash"], r["simhash"]) <= HAMMING_PREFILTER:
            other = run("SELECT resume_text FROM candidates WHERE id=?", (r["id"],), fetch=True)[0]["resume_text"] or ""
            sim = jaccard(new_shingles, shingle_set(other))
            if sim >= SIM_HIGH:
                reasons.append(f"resume {sim:.0%} similar"); high = True
            elif sim >= SIM_POSSIBLE:
                reasons.append(f"resume {sim:.0%} similar"); possible = True
        if high or possible:
            out.append({**r, "conf": "High" if high else "Possible", "reasons": reasons})
    return out

def duplicate_action(m, job_id):
    if m["conf"] == "High" and (m["job_id"] == job_id or m["joined"]):
        return "Blocked"
    return "Flagged"

def status_text(m):
    return "Hired" if m["joined"] else m["status"]

def vendor_alert_text(m, viewer_id, name):
    st_txt = status_text(m)
    if m["vendor_id"] == viewer_id:
        return f"**{name}** was previously submitted by your agency and is currently **{st_txt}**."
    return f"**{name}** already exists in the system (uploaded by another agency) and is **{st_txt}**."

def record_flag(action, m, job_id, vendor_id, name, email, phone, new_cid=None, resume=None):
    rn, blob, txt = resume or (None, None, None)
    return run("""INSERT INTO duplicate_flags(action,confidence,reasons,matched_id,new_candidate_id,job_id,vendor_id,
                  name,email,phone,resume_name,resume_blob,resume_text,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
               (action, m["conf"], json.dumps(m["reasons"]), m["id"], new_cid, job_id, vendor_id,
                name, email, phone, rn, blob, txt, now()))

def vendor_alerts_section(vid):
    flags = run("""SELECT f.id, f.action, f.confidence, f.matched_id, f.name, f.created_at, f.resolved, j.title AS job_title
                   FROM duplicate_flags f JOIN jobs j ON j.id=f.job_id WHERE f.vendor_id=? ORDER BY f.id DESC""",
                (vid,), fetch=True)
    if not flags:
        return
    with st.expander(f"🔔 Duplicate Alerts ({len(flags)})"):
        for f in flags:
            m = get_match(f["matched_id"])
            body = vendor_alert_text(m, vid, f["name"]) if m else f"**{f['name']}** flagged as duplicate."
            st.markdown(f"- {'🚫' if f['action'] == 'Blocked' else '⚠️'} **{f['name']}** ({f['job_title']}): {body}")

def dup_banner(flag):
    m = get_match(flag["matched_id"])
    if m:
        st.warning(f"⚠️ **{flag['confidence']}-confidence Duplicate** of **{m['name']}** ({m['vendor']}). Matches: {', '.join(json.loads(flag['reasons']))}.")

def duplicates_tab(blocked):
    if not blocked:
        st.caption("No duplicate uploads blocked for this role.")
        return
    for f in blocked:
        with st.container(border=True):
            st.markdown(f"**{f['name']}** ({f['email']}) · Agency: **{f['vendor']}**")
            st.caption("Matches on: " + ", ".join(json.loads(f["reasons"])))

# --------------------------------------------------------------------------
# Hiring Statistics & Employee Lifecycle Page
# --------------------------------------------------------------------------
def page_hiring_stats():
    header("📈", "Headcount & Hiring Analytics", "Workforce metrics, attrition, open positions, and offer conversions")
    total_emps = run("SELECT COUNT(*) as c FROM users WHERE role='employee' AND active=1", fetch=True)[0]["c"]
    total_jobs = run("SELECT SUM(openings) as s FROM jobs WHERE status='Open'", fetch=True)[0]["s"] or 0
    accepted = run("SELECT COUNT(*) as c FROM candidates WHERE status='Accepted'", fetch=True)[0]["c"]
    offers = run("SELECT COUNT(*) as c FROM candidates WHERE offered_at IS NOT NULL", fetch=True)[0]["c"]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Active Headcount", total_emps)
    c2.metric("Open Position Seats", total_jobs)
    c3.metric("Selected Candidates", accepted)
    c4.metric("Offers Extended", offers)

def bulk_import_tab():
    st.info("Bulk employee import utility. Use template formatting.")

def page_employees():
    header("🧑‍💻", "Employee Directory", "Active talent roster, department assignments, and resignation dates")
    emps = run("SELECT id, username, full_name, company, department, designation, join_date FROM users WHERE role='employee' AND approved=1", fetch=True)
    if emps:
        st.dataframe(pd.DataFrame(emps), hide_index=True)
    else:
        st.info("No active employee records.")

# --------------------------------------------------------------------------
# Main Router
# --------------------------------------------------------------------------
PAGES = {
    "admin": [("Hiring Stats", "📈", page_hiring_stats), ("Vendor Performance", "📊", page_dashboard),
              ("Job Requisitions", "📋", page_jobs), ("Candidate Review", "🗂️", page_review),
              ("Approvals", "✅", page_approvals), ("Employees", "🧑‍💻", page_employees),
              ("User Directory", "👥", page_users)],
    "manager": [("Hiring Stats", "📈", page_hiring_stats), ("Vendor Performance", "📊", page_dashboard),
                ("Job Requisitions", "📋", page_jobs), ("Candidate Review", "🗂️", page_review),
                ("Approvals", "✅", page_approvals), ("Employees", "🧑‍💻", page_employees)],
    "vendor": [("Submit Candidates", "📤", page_vendor_submit), ("My Submissions", "📁", page_vendor_mine),
               ("Team Timesheets", "🧾", page_vendor_timesheets)],
    "employee": [("My Timesheet", "🗓️", page_emp_timesheet), ("Leave & WFH", "🏠", page_emp_requests)],
}

def main():
    init_db()
    if "user" not in st.session_state:
        login_view()
        return

    fresh = run("SELECT * FROM users WHERE id=? AND active=1 AND approved=1", (st.session_state.user["id"],), fetch=True)
    if not fresh or (fresh[0].get("exit_date") and fresh[0]["exit_date"] < date.today().isoformat()):
        st.session_state.clear()
        st.rerun()

    user = st.session_state.user = fresh[0]
    msg = st.session_state.pop("flash", None)
    if msg:
        st.toast(msg)

    try:
        st.logo(LOGO_WIDE, size="large", icon_image=ICON)
    except TypeError:
        st.logo(LOGO_WIDE)

    sidebar_account(user)
    pages = [st.Page(fn, title=title, icon=icon) for title, icon, fn in PAGES[user["role"]]]
    st.navigation(pages).run()

if __name__ == "__main__":
    main()
