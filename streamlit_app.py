"""
Vendor Recruitment Hub - Streamlit app
======================================
Roles
  admin    : everything a manager can do + user management
  manager  : creates jobs, reviews candidates (shortlist / accept / reject),
             runs AI ranking, sees the vendor dashboard
  vendor   : sees open jobs, uploads candidate resumes, tracks own submissions,
             and sees APPROVED timesheets of the employees they supplied
  employee : hired candidate - submits monthly timesheets, requests leave / WFH

Run:
  pip install -r requirements.txt
  streamlit run app.py

First login (change immediately):  admin / Admin@123
(override with the ADMIN_PASSWORD environment variable before first run)

Optional AI keys (environment variables or .streamlit/secrets.toml):
  ANTHROPIC_API_KEY, ANTHROPIC_MODEL (default claude-sonnet-5-5)
  OPENAI_API_KEY,    OPENAI_MODEL    (default gpt-4o-mini)
"""
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import sqlite3
import calendar
from datetime import date, datetime, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

from pathlib import Path

LOGO = Path(__file__).parent / "logo.png"
ICON = Path(__file__).parent / "icon.png"

st.set_page_config(
    page_title="B/S/H/. InCount",
    page_icon=str(ICON) if ICON.exists() else "🧑‍💼",
    layout="wide",
)

st.markdown("""
<style>
#MainMenu, footer {visibility: hidden;}
.block-container {padding-top: 2rem; max-width: 1200px;}
[data-testid="stMetric"] {
    background: var(--secondary-background-color);
    border: 1px solid rgba(128,128,128,.18);
    border-radius: 14px; padding: 14px 18px;
}
[data-testid="stVerticalBlockBorderWrapper"] {border-radius: 14px;}
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {
    border-radius: 10px; font-weight: 600;
}
[data-testid="stSidebar"] {border-right: 1px solid rgba(128,128,128,.18);}
button[data-baseweb="tab"] {font-weight: 600;}
.kpi-icon {font-size: 3rem; text-align: center; padding-top: .8rem; filter: grayscale(1); opacity: .6;}
.kpi-title {text-align: center; font-size: 1.25rem; letter-spacing: .03em; opacity: .85;}
.kpi-value {text-align: center; font-size: 2.8rem; font-weight: 600; line-height: 1.15;}
.kpi-sub {text-align: center; font-size: .8rem; opacity: .6; min-height: 1.2rem;}
[data-testid="stButton"]:has([data-testid="stBaseButton-tertiary"]) {display: flex; justify-content: flex-end;}
[data-testid="stBaseButton-tertiary"] {color: var(--primary-color, #4F46E5) !important; font-weight: 600;}
</style>
""", unsafe_allow_html=True)

DB_PATH = os.environ.get("RECRUIT_DB", "recruitment.db")
STATUSES = ["Submitted", "Shortlisted", "Accepted", "Rejected"]
PENDING = ["Submitted", "Shortlisted"]
BADGE = {"Submitted": "🟡", "Shortlisted": "🔵", "Accepted": "🟢", "Rejected": "🔴"}
MAX_UPLOAD_MB = 5


# --------------------------------------------------------------------------
# Database
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
  approved INTEGER DEFAULT 1,      -- self sign-ups start at 0 until an admin approves
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
  employee_id INTEGER NOT NULL, month TEXT NOT NULL,          -- 'YYYY-MM'
  status TEXT DEFAULT 'Draft',                                -- Draft/Submitted/Approved/Rejected
  entries TEXT, total_hours REAL DEFAULT 0,                   -- entries = JSON list of daily rows
  submitted_at TEXT, manager_note TEXT, decided_by INTEGER, decided_at TEXT,
  created_at TEXT,
  UNIQUE(employee_id, month)
);
CREATE TABLE IF NOT EXISTS requests(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  employee_id INTEGER NOT NULL,
  kind TEXT NOT NULL,                                         -- 'Leave' or 'WFH'
  leave_type TEXT, start_date TEXT NOT NULL, end_date TEXT NOT NULL,
  days INTEGER, reason TEXT,
  status TEXT DEFAULT 'Pending',                              -- Pending/Approved/Rejected/Cancelled
  manager_note TEXT, decided_by INTEGER, decided_at TEXT, created_at TEXT
);
"""


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def run(sql, params=(), fetch=False):
    """Run one SQL statement. Returns list[dict] if fetch else lastrowid."""
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
    """Older databases have a users table that doesn't allow the 'employee' role - rebuild it."""
    row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'").fetchone()
    if row and "'employee'" not in row[0]:
        conn.execute("ALTER TABLE users RENAME TO users_old")
        conn.executescript(SCHEMA)  # recreates users with the new definition
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
    "candidates": {"offered_at": "TEXT"},
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
# Resume parsing
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
# AI scoring methods - each returns (score 0-100, note)
# --------------------------------------------------------------------------
def get_secret(name, default=None):
    if os.environ.get(name):
        return os.environ[name]
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default


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
    # Resume-vs-JD cosine rarely exceeds ~0.5, so rescale to a friendlier 0-100.
    return round(min(100.0, sim / 0.5 * 100), 1), f"Cosine similarity {sim:.2f}"


def build_prompt(job, resume):
    return f"""You are a senior technical recruiter. Compare the resume with the job and score the fit.

JOB TITLE: {job['title']}
EXPERIENCE: {job['experience']}
REQUIRED SKILLS: {job['required_skills']}
JOB DESCRIPTION:
{job['description']}

RESUME:
{resume[:12000]}

Scoring: 90+ exceptional, 70-89 strong, 50-69 partial, below 50 weak fit.
Reply with ONLY a JSON object, no other text:
{{"score": <integer 0-100>, "summary": "<2-3 sentences>", "strengths": ["..."], "gaps": ["..."]}}"""


def parse_llm(text):
    data = json.loads(re.search(r"\{.*\}", text, re.S).group(0))
    score = float(max(0, min(100, data["score"])))
    note = data.get("summary", "")
    if data.get("strengths"):
        note += " | Strengths: " + "; ".join(data["strengths"])
    if data.get("gaps"):
        note += " | Gaps: " + "; ".join(data["gaps"])
    return score, note


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
    "Keyword skills match": score_keywords,   # free, instant, transparent
    "TF-IDF similarity": score_tfidf,         # free, local semantic-ish overlap
    "Claude (Anthropic)": score_claude,       # LLM reasoning, needs API key
    "GPT (OpenAI)": score_openai,             # LLM reasoning, needs API key
}


def ai_evaluate(job, resume, methods):
    """Run chosen methods; final score = average of the ones that succeeded."""
    if not resume.strip():
        return 0.0, [{"method": "-", "score": 0, "note": "No readable text in resume (scanned PDF?)"}]
    results = []
    for m in methods:
        try:
            s, note = METHODS[m](job, resume)
            results.append({"method": m, "score": s, "note": note})
        except Exception as e:
            results.append({"method": m, "score": None, "note": f"Failed: {e}"})
    ok = [r["score"] for r in results if r["score"] is not None]
    return (round(sum(ok) / len(ok), 1) if ok else None), results


# --------------------------------------------------------------------------
# UI helpers
# --------------------------------------------------------------------------
STATUS_COLORS = {"Submitted": "#F59E0B", "Shortlisted": "#3B82F6", "Accepted": "#10B981", "Rejected": "#EF4444"}
REJECT_PRESETS = ["Skills mismatch", "Experience gap", "Salary expectation",
                  "Location / notice period", "Position on hold", "Other"]


def header(icon, title, subtitle=""):
    st.title(f"{icon} {title}")
    if subtitle:
        st.caption(subtitle)


def flash(msg):
    """Show a toast on the next run (survives st.rerun)."""
    st.session_state["flash"] = msg


def style_fig(fig, height=360):
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=50, b=10), legend_title_text="",
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
    return fig


# --------------------------------------------------------------------------
# Auth
# --------------------------------------------------------------------------
ROLE_CHOICES = {
    "Hiring manager": "manager",
    "Vendor": "vendor",
    "Employee (hired through a vendor)": "employee",
}
USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{3,32}$")


def vendor_options():
    """{vendor user id: display name} for approved, active vendors."""
    rows = run("""SELECT id, COALESCE(NULLIF(company,''), NULLIF(full_name,''), username) AS name
                  FROM users WHERE role='vendor' AND active=1 AND approved=1 ORDER BY name""", fetch=True)
    return {r["id"]: r["name"] for r in rows}


def signin_form():
    with st.form("login"):
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        if st.form_submit_button("Sign in", type="primary"):
            rows = run("SELECT * FROM users WHERE username=? AND active=1", (u.strip(),), fetch=True)
            if rows and verify_pw(p, rows[0]["pw_hash"], rows[0]["salt"]):
                if not rows[0]["approved"]:
                    st.warning("Your account is waiting for admin approval. Please check back later.")
                elif rows[0].get("exit_date") and rows[0]["exit_date"] < date.today().isoformat():
                    st.error("Your employment has ended and this account is now closed.")
                else:
                    st.session_state.user = rows[0]
                    st.rerun()
            else:
                st.error("Invalid credentials or inactive account.")


def signup_form():
    st.caption("Pick your role first - the form adapts to it. An admin reviews every new account "
               "before it can be used.")
    choice = st.selectbox("I'm signing up as a...", list(ROLE_CHOICES), index=None,
                          placeholder="Select your role", key="su_role")
    if not choice:
        return
    role = ROLE_CHOICES[choice]
    vendors = vendor_options()

    with st.form("signup", clear_on_submit=True):
        full = st.text_input("Full name *")
        company, designation, vendor_id = "", "", None
        if role == "vendor":
            company = st.text_input("Vendor company name *")
        elif role == "employee":
            if vendors:
                vendor_id = st.selectbox("Vendor that placed you *", list(vendors), index=None,
                                         format_func=lambda i: vendors[i], placeholder="Select your vendor")
            else:
                st.warning("No approved vendors exist yet. Ask your vendor to sign up first.")
            designation = st.text_input("Job title / role *")
        else:
            company = st.text_input("Company / department")
        username = st.text_input("Username *", help="3-32 characters: letters, numbers, . _ -")
        pw = st.text_input("Password * (min 8 characters)", type="password")
        pw2 = st.text_input("Confirm password *", type="password")

        if st.form_submit_button("Create account", type="primary"):
            uname = username.strip()
            if not full.strip() or not uname or not pw:
                st.error("Please fill in all required fields.")
            elif not USERNAME_RE.match(uname):
                st.error("Username must be 3-32 characters: letters, numbers, dot, dash or underscore.")
            elif len(pw) < 8:
                st.error("Password must be at least 8 characters.")
            elif pw != pw2:
                st.error("Passwords do not match.")
            elif role == "vendor" and not company.strip():
                st.error("Vendor company name is required.")
            elif role == "employee" and (vendor_id is None or not designation.strip()):
                st.error("Select the vendor that placed you and enter your job title.")
            elif run("SELECT 1 FROM users WHERE lower(username)=lower(?)", (uname,), fetch=True):
                st.error("That username is already taken.")
            else:
                try:
                    create_user(uname, pw, role, full, company, vendor_id=vendor_id,
                                designation=designation.strip(), approved=0)
                    st.success("Account created! An admin needs to approve it before you can sign in.")
                except sqlite3.IntegrityError:
                    st.error("That username is already taken.")


def login_view():
    _, mid, _ = st.columns([1, 1.3, 1])
    with mid:
        st.write("")
        st.write("")
               if LOGO.exists():
            _, logo_col, _ = st.columns([1, 2, 1])
            logo_col.image(str(LOGO))
            st.markdown("<p style='text-align:center;opacity:.7'>Source, screen and hire - together with your vendors</p>",
                        unsafe_allow_html=True)
        else:
            st.markdown("<h1 style='text-align:center;margin-bottom:0'>🧑‍💼 Recruitment Hub</h1>"
                        "<p style='text-align:center;opacity:.7'>Source, screen and hire - together with your vendors</p>",
                        unsafe_allow_html=True)
                    "<p style='text-align:center;opacity:.7'>Source, screen and hire - together with your vendors</p>",
                    unsafe_allow_html=True)
        tab_in, tab_up = st.tabs(["Sign in", "Sign up"])
        with tab_in:
            signin_form()
        with tab_up:
            signup_form()


def sidebar_account(user):
    with st.sidebar:
        st.markdown(f"### 🧑‍💼 Recruitment Hub\n**{user['full_name'] or user['username']}**  \n`{user['role']}`")
        with st.expander("Change password"):
            old = st.text_input("Current password", type="password", key="pw_old")
            new = st.text_input("New password (min 8 chars)", type="password", key="pw_new")
            if st.button("Update password"):
                row = run("SELECT * FROM users WHERE id=?", (user["id"],), fetch=True)[0]
                if not verify_pw(old, row["pw_hash"], row["salt"]):
                    st.error("Current password is wrong.")
                elif len(new) < 8:
                    st.error("New password is too short.")
                else:
                    h, s = hash_pw(new)
                    run("UPDATE users SET pw_hash=?, salt=? WHERE id=?", (h, s, user["id"]))
                    st.success("Password updated.")
        if st.button("Sign out"):
            st.session_state.clear()
            st.rerun()


# --------------------------------------------------------------------------
# Manager / admin pages
# --------------------------------------------------------------------------
def page_jobs():
    header("📋", "Job openings", "Create roles and track how vendors are responding")
    user = st.session_state.user
    tab_list, tab_new = st.tabs(["All jobs", "➕ New job"])

    with tab_new:
        with st.form("new_job", clear_on_submit=True):
            c1, c2 = st.columns(2)
            title = c1.text_input("Job title *")
            dept = c2.text_input("Department")
            loc = c1.text_input("Location")
            etype = c2.selectbox("Employment type", ["Full-time", "Contract", "Part-time", "Internship"])
            exp = c1.text_input("Experience required (e.g. 5-8 years)")
            openings = c2.number_input("Number of openings", 1, 500, 1)
            skills = st.text_area("Required skills (comma separated) - used by the keyword matcher",
                                  placeholder="python, sql, aws, stakeholder management")
            desc = st.text_area("Job description *", height=200)
            if st.form_submit_button("Publish job", type="primary"):
                if not title.strip() or not desc.strip():
                    st.error("Title and description are required.")
                else:
                    run("""INSERT INTO jobs(title,department,location,employment_type,experience,
                           required_skills,description,openings,created_by,created_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?)""",
                        (title.strip(), dept, loc, etype, exp, skills, desc, openings, user["id"], now()))
                    flash("Job published - vendors can now submit candidates.")
                    st.rerun()

    with tab_list:
        jobs = run("""SELECT j.*, (SELECT COUNT(*) FROM candidates c WHERE c.job_id=j.id) AS submissions,
                      (SELECT COUNT(*) FROM candidates c WHERE c.job_id=j.id AND c.status='Accepted') AS accepted
                      FROM jobs j ORDER BY j.id DESC""", fetch=True)
        if not jobs:
            st.info("No jobs yet - create one in the 'New job' tab.")
        for j in jobs:
            with st.container(border=True):
                top, btn = st.columns([5, 1])
                top.markdown(f"#### {'🟢' if j['status'] == 'Open' else '⚪'} {j['title']}")
                top.caption(f"#{j['id']} · {j['department'] or 'No dept'} · {j['location'] or 'No location'} · "
                            f"{j['employment_type']} · {j['experience'] or 'Experience not set'}")
                new_status = "Closed" if j["status"] == "Open" else "Open"
                if btn.button("Close job" if new_status == "Closed" else "Reopen", key=f"js{j['id']}"):
                    run("UPDATE jobs SET status=? WHERE id=?", (new_status, j["id"]))
                    st.rerun()
                m1, m2, m3 = st.columns(3)
                m1.metric("Submissions", j["submissions"])
                m2.metric("Accepted / openings", f"{j['accepted']} / {j['openings']}")
                m3.write("")
                m3.progress(min(1.0, j["accepted"] / max(1, j["openings"])), text="Positions filled")
                with st.expander("Description & skills"):
                    st.write(f"**Skills:** {j['required_skills'] or '-'}")
                    st.write(j["description"])


def decide(cid, status, reason="", name="Candidate"):
    run("UPDATE candidates SET status=?, decision_reason=?, decided_by=?, decided_at=? WHERE id=?",
        (status, reason, st.session_state.user["id"], now(), cid))
    if status != "Accepted":
        run("UPDATE candidates SET offered_at=NULL WHERE id=?", (cid,))
    flash(f"{BADGE[status]} {name} moved to {status}")
    st.rerun()


@st.dialog("Reject candidate")
def reject_dialog(cid, name):
    st.write(f"Why are you rejecting **{name}**? This feedback is shared with the vendor.")
    preset = st.selectbox("Reason", REJECT_PRESETS)
    note = st.text_area("Additional note (optional)")
    if st.button("Confirm rejection", type="primary"):
        decide(cid, "Rejected", preset + (f": {note.strip()}" if note.strip() else ""), name)


def candidate_card(c, rank):
    with st.container(border=True):
        a, b, d = st.columns([3, 2, 3])
        a.markdown(f"**#{rank} · {c['name']}**  \n{c['email']} · {c['phone'] or '-'}")
        b.markdown(f"Vendor  \n**{c['vendor']}**")
        if c["ai_score"] is not None:
            d.progress(min(1.0, c["ai_score"] / 100), text=f"AI match {c['ai_score']:.0f}/100")
        else:
            d.caption("Not scored yet")
        if c["decision_reason"]:
            st.caption(f"📝 {c['decision_reason']}")

        with st.expander("AI analysis & resume"):
            if c["ai_details"]:
                for r in json.loads(c["ai_details"]):
                    s = "n/a" if r["score"] is None else f"{r['score']:.0f}"
                    st.markdown(f"- **{r['method']}** ({s}): {r['note']}")
            else:
                st.caption("Run AI ranking to see analysis.")
            row = run("SELECT resume_text, resume_blob FROM candidates WHERE id=?", (c["id"],), fetch=True)[0]
            st.text_area("Resume text", row["resume_text"] or "", height=180, disabled=True, key=f"rt{c['id']}")
            st.download_button("⬇ Download original resume", row["resume_blob"],
                               file_name=c["resume_name"], key=f"dl{c['id']}")

        b1, b2, b3, b4, _ = st.columns([1, 1, 1, 1, 2])
        if b1.button("Shortlist", key=f"sl{c['id']}", disabled=c["status"] != "Submitted"):
            decide(c["id"], "Shortlisted", "", c["name"])
        if b2.button("Accept", key=f"ac{c['id']}", type="primary", disabled=c["status"] == "Accepted"):
            decide(c["id"], "Accepted", "", c["name"])
        if b3.button("Reject", key=f"rj{c['id']}", disabled=c["status"] == "Rejected"):
            reject_dialog(c["id"], c["name"])
        if c["status"] in ("Accepted", "Rejected") and b4.button("↩ Reopen", key=f"ro{c['id']}"):
            decide(c["id"], "Submitted", "", c["name"])
        if c["status"] == "Accepted":
            emp = run("SELECT username FROM users WHERE candidate_id=?", (c["id"],), fetch=True)
            if emp:
                st.caption(f"✅ Joined - employee login: `{emp[0]['username']}`")
            else:
                o1, o2, _ = st.columns([1.5, 1.7, 3])
                if c["offered_at"]:
                    o1.caption(f"📝 Offer released {c['offered_at'][:10]}")
                elif o1.button("📝 Offer released", key=f"of{c['id']}"):
                    run("UPDATE candidates SET offered_at=? WHERE id=?", (now(), c["id"]))
                    flash(f"📝 Offer marked as released for {c['name']}")
                    st.rerun()
                if o2.button("🪪 Onboard as employee", key=f"ob{c['id']}"):
                    onboard_dialog(c)


def page_review():
    header("🗂️", "Candidate review", "Rank, shortlist and decide")
    jobs = run("SELECT id,title,status FROM jobs ORDER BY id DESC", fetch=True)
    if not jobs:
        st.info("Create a job first.")
        return
    lookup = {j["id"]: j for j in jobs}
    job_id = st.selectbox("Job", list(lookup),
                          format_func=lambda i: f"#{i} · {lookup[i]['title']} ({lookup[i]['status']})")
    job = run("SELECT * FROM jobs WHERE id=?", (job_id,), fetch=True)[0]

    # ---- AI ranking -------------------------------------------------------
    with st.expander("🤖 AI screening & ranking"):
        methods = st.multiselect("AI methods (if several, scores are averaged)", list(METHODS),
                                 default=["Keyword skills match", "TF-IDF similarity"])
        st.caption("Keyword + TF-IDF run locally and free. Claude / GPT need an API key and give written reasoning.")
        rescore = st.checkbox("Also re-score candidates that already have a score")
        if st.button("Run AI ranking", type="primary", disabled=not methods):
            targets = [c for c in fetch_candidates(job_id=job_id) if rescore or c["ai_score"] is None]
            if not targets:
                st.info("Nothing to score.")
            else:
                bar, failed = st.progress(0.0, text="Scoring..."), 0
                for i, c in enumerate(targets):
                    text = run("SELECT resume_text FROM candidates WHERE id=?", (c["id"],), fetch=True)[0]["resume_text"] or ""
                    score, details = ai_evaluate(job, text, methods)
                    if score is None:
                        failed += 1
                    else:
                        run("UPDATE candidates SET ai_score=?, ai_details=? WHERE id=?",
                            (score, json.dumps(details), c["id"]))
                    bar.progress((i + 1) / len(targets), text=f"Scoring {i + 1}/{len(targets)}")
                st.success(f"Scored {len(targets) - failed} candidate(s).")
                if failed:
                    st.warning(f"{failed} failed - check API keys / installed packages.")

    all_cands = fetch_candidates(job_id=job_id)
    if not all_cands:
        st.info("No candidates submitted for this job yet.")
        return

    q = st.text_input("🔍 Search by name, email or vendor", placeholder="Start typing...").strip().lower()
    cands = [c for c in all_cands if not q or q in f"{c['name']} {c['email']} {c['vendor']}".lower()]

    tabs = st.tabs([f"{BADGE[s]} {s} ({sum(c['status'] == s for c in cands)})" for s in STATUSES])
    for tab, status in zip(tabs, STATUSES):
        with tab:
            items = sorted([c for c in cands if c["status"] == status],
                           key=lambda c: (c["ai_score"] is None, -(c["ai_score"] or 0)))
            if status == "Submitted" and items:
                with st.expander("⚡ Bulk reject low scorers"):
                    thr = st.slider("Reject 'Submitted' candidates scoring below", 0, 100, 30)
                    if st.button("Bulk reject"):
                        n = 0
                        for c in all_cands:
                            if c["status"] == "Submitted" and c["ai_score"] is not None and c["ai_score"] < thr:
                                run("UPDATE candidates SET status='Rejected', decision_reason=?, decided_by=?, decided_at=? WHERE id=?",
                                    (f"Below AI screening threshold ({thr})", st.session_state.user["id"], now(), c["id"]))
                                n += 1
                        flash(f"Rejected {n} candidate(s) below {thr}")
                        st.rerun()
            if not items:
                st.caption("Nothing here yet.")
            for rank, c in enumerate(items, 1):
                candidate_card(c, rank)


def page_dashboard():
    header("📊", "Vendor performance", "Acceptance and rejection rates by vendor")
    jobs = run("SELECT id,title FROM jobs ORDER BY id DESC", fetch=True)
    lookup = {0: "All jobs", **{j["id"]: f"#{j['id']} · {j['title']}" for j in jobs}}
    job_id = st.selectbox("Job filter", list(lookup), format_func=lambda i: lookup[i])
    df = pd.DataFrame(fetch_candidates(job_id=job_id or None))
    if df.empty:
        st.info("No candidate data yet.")
        return

    total = len(df)
    acc, rej = int((df.status == "Accepted").sum()), int((df.status == "Rejected").sum())
    pend = int(df.status.isin(PENDING).sum())
    m = st.columns(4)
    m[0].metric("Submitted", total)
    m[1].metric("Accepted", f"{acc}  ({acc / total:.0%})")
    m[2].metric("Rejected", f"{rej}  ({rej / total:.0%})")
    m[3].metric("Pending", pend)

    g = df.groupby("vendor")
    out = pd.DataFrame({
        "Submitted": g.size(),
        "Pending": g.status.apply(lambda s: int(s.isin(PENDING).sum())),
        "Accepted": g.status.apply(lambda s: int((s == "Accepted").sum())),
        "Rejected": g.status.apply(lambda s: int((s == "Rejected").sum())),
        "Avg AI score": g.ai_score.mean().round(1),
    })
    out["Accepted %"] = (out["Accepted"] / out["Submitted"] * 100).round(1)
    out["Rejected %"] = (out["Rejected"] / out["Submitted"] * 100).round(1)
    decided = (out["Accepted"] + out["Rejected"]).where(lambda x: x > 0)
    out["Acceptance % of decided"] = (out["Accepted"] / decided * 100).round(1)
    out = out.sort_values("Accepted %", ascending=False).reset_index().rename(columns={"vendor": "Vendor"})

    st.subheader("By vendor")
    pct = lambda label: st.column_config.ProgressColumn(label, min_value=0, max_value=100, format="%.1f")
    st.dataframe(out, hide_index=True, column_config={
        "Accepted %": pct("Accepted %"),
        "Rejected %": pct("Rejected %"),
        "Acceptance % of decided": pct("Acceptance % of decided"),
        "Avg AI score": pct("Avg AI score"),
    })
    st.caption("Accepted % / Rejected % are out of everything the vendor submitted; "
               "'Acceptance % of decided' ignores candidates still pending.")

    c1, c2 = st.columns([3, 2])
    with c1:
        fig = px.bar(out, x="Vendor", y=["Accepted %", "Rejected %"], barmode="group", text_auto=".1f",
                     color_discrete_map={"Accepted %": STATUS_COLORS["Accepted"], "Rejected %": STATUS_COLORS["Rejected"]},
                     labels={"value": "% of submitted", "variable": ""}, title="Accepted vs rejected % by vendor")
        st.plotly_chart(style_fig(fig))
    with c2:
        mix = df.groupby("status").size().reset_index(name="count")
        fig = px.pie(mix, names="status", values="count", hole=0.55, color="status",
                     color_discrete_map=STATUS_COLORS, title="Overall status mix")
        st.plotly_chart(style_fig(fig))

    mix_v = df.groupby(["vendor", "status"]).size().reset_index(name="count")
    fig = px.bar(mix_v, x="vendor", y="count", color="status", color_discrete_map=STATUS_COLORS,
                 category_orders={"status": STATUSES}, labels={"vendor": "Vendor", "count": "Candidates"},
                 title="Pipeline by vendor")
    st.plotly_chart(style_fig(fig, 340))

    c3, c4 = st.columns(2)
    with c3:
        st.subheader("Submissions per job")
        st.dataframe(df.groupby("job_title").status.value_counts().unstack(fill_value=0))
    with c4:
        st.subheader("Submissions over time")
        df["day"] = pd.to_datetime(df.created_at).dt.date
        st.line_chart(df.groupby("day").size())


def page_users():
    header("👥", "User management", "Approve sign-ups and manage logins")
    pending = run("SELECT * FROM users WHERE approved=0 ORDER BY created_at", fetch=True)
    all_vendors = {r["id"]: r["name"] for r in run(
        """SELECT id, COALESCE(NULLIF(company,''), NULLIF(full_name,''), username) AS name
           FROM users WHERE role='vendor'""", fetch=True)}
    tab_list, tab_pending, tab_new = st.tabs(["Users", f"🕓 Pending sign-ups ({len(pending)})", "➕ Add user"])

    with tab_pending:
        if not pending:
            st.caption("No sign-ups waiting for approval.")
        for u in pending:
            with st.container(border=True):
                a, b, c = st.columns([5, 1, 1])
                if u["role"] == "employee":
                    detail = f"Vendor: **{all_vendors.get(u['vendor_id'], 'unknown')}** · Title: {u['designation'] or '-'}"
                else:
                    detail = f"Company: {u['company'] or '-'}"
                a.markdown(f"**{u['full_name']}** (`{u['username']}`) · requested role: **{u['role']}**  \n"
                           f"{detail} · signed up {u['created_at']}")
                if b.button("Approve", key=f"ap{u['id']}", type="primary"):
                    run("UPDATE users SET approved=1, join_date=? WHERE id=?", (date.today().isoformat(), u["id"]))
                    flash(f"✅ {u['username']} approved as {u['role']}")
                    st.rerun()
                if c.button("Reject", key=f"rjs{u['id']}"):
                    run("DELETE FROM users WHERE id=? AND approved=0", (u["id"],))
                    flash(f"🗑️ Sign-up from {u['username']} rejected")
                    st.rerun()

    with tab_new:
        vendors = vendor_options()
        with st.form("new_user", clear_on_submit=True):
            c1, c2 = st.columns(2)
            username = c1.text_input("Username *")
            role = c2.selectbox("Role", ["manager", "vendor", "employee", "admin"])
            full = c1.text_input("Full name")
            company = c2.text_input("Vendor company (for vendors)")
            vendor_id = None
            if vendors:
                vendor_id = c1.selectbox("Supplying vendor (employees only)", list(vendors), index=None,
                                         format_func=lambda i: vendors[i], placeholder="Select vendor")
            designation = c2.text_input("Job title (employees only)")
            pw = st.text_input("Temporary password * (min 8 chars)", type="password")
            if st.form_submit_button("Create user", type="primary"):
                if not username.strip() or len(pw) < 8:
                    st.error("Username and a password of 8+ characters are required.")
                elif role == "vendor" and not (company.strip() or full.strip()):
                    st.error("Vendors need a company or full name (shown on the dashboard).")
                elif role == "employee" and vendor_id is None:
                    st.error("Employees must be linked to a supplying vendor.")
                else:
                    try:
                        create_user(username, pw, role, full, company,
                                    vendor_id=vendor_id if role == "employee" else None,
                                    designation=designation if role == "employee" else "")
                        st.success(f"Created {role} '{username}'.")
                    except sqlite3.IntegrityError:
                        st.error("That username already exists.")

    with tab_list:
        users = run("""SELECT id,username,full_name,company,role,active,approved,vendor_id,designation,created_at
                       FROM users ORDER BY id""", fetch=True)
        df = pd.DataFrame(users)
        df["vendor"] = df.vendor_id.map(lambda v: all_vendors.get(v, "") if pd.notna(v) else "")
        st.dataframe(df.drop(columns=["vendor_id"]), hide_index=True)
        lookup = {u["id"]: u for u in users}
        with st.container(border=True):
            uid = st.selectbox("Manage user", list(lookup),
                               format_func=lambda i: f"{lookup[i]['username']} ({lookup[i]['role']})")
            c1, c2 = st.columns(2)
            if uid != st.session_state.user["id"]:
                label = "Deactivate" if lookup[uid]["active"] else "Activate"
                if c1.button(label):
                    run("UPDATE users SET active=? WHERE id=?", (0 if lookup[uid]["active"] else 1, uid))
                    st.rerun()
            new_pw = c2.text_input("New password", type="password", key="reset_pw")
            if c2.button("Reset password"):
                if len(new_pw) < 8:
                    st.error("Min 8 characters.")
                else:
                    h, s = hash_pw(new_pw)
                    run("UPDATE users SET pw_hash=?, salt=? WHERE id=?", (h, s, uid))
                    st.success("Password reset.")


# --------------------------------------------------------------------------
# Vendor pages
# --------------------------------------------------------------------------
def page_vendor_submit():
    header("📤", "Submit candidates", "Pick an open role and upload a resume")
    user = st.session_state.user
    jobs = run("SELECT * FROM jobs WHERE status='Open' ORDER BY id DESC", fetch=True)
    if not jobs:
        st.info("There are no open jobs right now.")
        return
    lookup = {j["id"]: j for j in jobs}
    jid = st.selectbox("Open job", list(lookup),
                       format_func=lambda i: f"#{i} · {lookup[i]['title']} - {lookup[i]['location'] or ''}")
    j = lookup[jid]
    with st.container(border=True):
        st.markdown(f"#### {j['title']}")
        st.caption(f"{j['employment_type']} · {j['experience'] or 'Experience not set'} · "
                   f"{j['openings']} opening(s) · {j['location'] or 'Location not set'}")
        st.write(f"**Skills:** {j['required_skills'] or '-'}")
        with st.expander("Full job description"):
            st.write(j["description"])

    with st.form("submit_candidate", clear_on_submit=True):
        c1, c2 = st.columns(2)
        name = c1.text_input("Candidate name *")
        email = c2.text_input("Candidate email *")
        phone = c1.text_input("Phone")
        f = st.file_uploader("Resume (PDF, DOCX or TXT) *", type=["pdf", "docx", "txt"])
        if st.form_submit_button("Submit candidate", type="primary"):
            if not name.strip() or not email.strip() or f is None:
                st.error("Name, email and resume are required.")
            elif f.size > MAX_UPLOAD_MB * 1024 * 1024:
                st.error(f"File is larger than {MAX_UPLOAD_MB} MB.")
            else:
                data = f.getvalue()
                text = extract_text(f.name, data)
                try:
                    run("""INSERT INTO candidates(job_id,vendor_id,name,email,phone,resume_name,resume_blob,
                           resume_text,created_at) VALUES(?,?,?,?,?,?,?,?,?)""",
                        (jid, user["id"], name.strip(), email.strip().lower(), phone, f.name, data, text, now()))
                    st.success("Candidate submitted.")
                    if not text.strip():
                        st.warning("No text could be read from this file (scanned PDF?). "
                                   "AI ranking will not work - upload a text-based resume if possible.")
                except sqlite3.IntegrityError:
                    st.error("This candidate (same email) was already submitted for this job.")


def page_vendor_mine():
    header("📁", "My submissions", "Track the status of every candidate you've sent")
    rows = fetch_candidates(vendor_id=st.session_state.user["id"])
    if not rows:
        st.info("You haven't submitted any candidates yet.")
        return
    df = pd.DataFrame(rows)[["job_title", "name", "email", "status", "decision_reason", "created_at", "decided_at"]]
    total = len(df)
    c = st.columns(4)
    c[0].metric("Submitted", total)
    c[1].metric("Pending", int(df.status.isin(PENDING).sum()))
    c[2].metric("Accepted", int((df.status == "Accepted").sum()))
    c[3].metric("Rejected", int((df.status == "Rejected").sum()))
    df["status"] = df.status.map(lambda s: f"{BADGE[s]} {s}")
    df.columns = ["Job", "Candidate", "Email", "Status", "Manager feedback", "Submitted", "Decided"]
    st.dataframe(df, hide_index=True)


# --------------------------------------------------------------------------
# Employees: onboarding, timesheets, leave / WFH, approvals
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
    """{iso date: 'Leave' | 'WFH'} for approved requests that touch this month (weekdays only)."""
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
            (emp_id, ym, "Submitted" if submit else "Draft", json.dumps(entries), total,
             now() if submit else None, now()))
    elif submit:
        run("""UPDATE timesheets SET entries=?, total_hours=?, status='Submitted', submitted_at=?,
               manager_note=NULL, decided_by=NULL, decided_at=NULL WHERE id=?""",
            (json.dumps(entries), total, now(), cur[0]["id"]))
    else:  # draft save keeps the current status (Draft, or Rejected while the employee fixes it)
        run("UPDATE timesheets SET entries=?, total_hours=? WHERE id=?", (json.dumps(entries), total, cur[0]["id"]))


# ---- onboarding (manager / admin) ----------------------------------------
@st.dialog("Onboard as employee")
def onboard_dialog(c):
    st.write(f"Create a login for **{c['name']}**, supplied by **{c['vendor']}**.")
    default = re.sub(r"[^a-z0-9.]", "", c["name"].lower().replace(" ", "."))
    username = st.text_input("Username", value=default)
    pw = st.text_input("Temporary password (min 8 chars)", type="password")
    st.caption("Share these credentials with the employee; they can change the password after signing in.")
    if st.button("Create employee login", type="primary"):
        if not username.strip() or len(pw) < 8:
            st.error("Username and a password of 8+ characters are required.")
        else:
            try:
                job = run("SELECT department, employment_type FROM jobs WHERE id=?", (c["job_id"],), fetch=True)[0]
                create_user(username, pw, "employee", c["name"], c["vendor"], vendor_id=c["vendor_id"],
                            candidate_id=c["id"], designation=c["job_title"],
                            department=job["department"] or "", fte=fte_for(job["employment_type"]))
                flash(f"🪪 Employee login created for {c['name']}")
                st.rerun()
            except sqlite3.IntegrityError:
                st.error("That username already exists.")


# ---- employee pages --------------------------------------------------------
def page_emp_timesheet():
    header("🗓️", "My timesheet", "Fill in your hours for the month and submit for approval")
    user = st.session_state.user
    ym = st.selectbox("Month", month_options(), format_func=month_label)
    found = run("SELECT * FROM timesheets WHERE employee_id=? AND month=?", (user["id"], ym), fetch=True)
    ts = found[0] if found else None
    status = ts["status"] if ts else "Not started"
    st.markdown(f"**Status:** {TS_BADGE[status]} {status}")
    if status == "Rejected" and ts["manager_note"]:
        st.warning(f"Your manager sent this back: {ts['manager_note']}")
    if status == "Approved":
        st.success(f"Approved on {ts['decided_at']}. This timesheet is now visible to your vendor.")
    elif status == "Submitted":
        st.info("Submitted - waiting for your manager's approval.")
    locked = status in ("Submitted", "Approved")

    df = pd.DataFrame(json.loads(ts["entries"])) if ts else default_grid(user["id"], ym)
    if not ts:
        st.caption("Pre-filled with 8h on weekdays; approved leave / WFH days are marked for you. Adjust as needed.")
    edited = st.data_editor(
        df, key=f"ts_{ym}_{status}", hide_index=True, num_rows="fixed",
        disabled=True if locked else ["Date", "Day"],
        column_config={
            "Type": st.column_config.SelectboxColumn("Type", options=DAY_TYPES, required=True),
            "Hours": st.column_config.NumberColumn("Hours", min_value=0, max_value=24, step=0.5, format="%.1f"),
            "Notes": st.column_config.TextColumn("Notes", width="large"),
        },
    )
    s = ts_summary(json.loads(edited.fillna({"Hours": 0, "Notes": ""}).to_json(orient="records")))
    m = st.columns(4)
    m[0].metric("Total hours", f"{s['hours']:.1f}")
    m[1].metric("Office days", s["office"])
    m[2].metric("WFH days", s["wfh"])
    m[3].metric("Leave days", s["leave"])

    if not locked:
        c1, c2, _ = st.columns([1, 1.5, 3])
        if c1.button("💾 Save draft"):
            save_timesheet(user["id"], ym, edited, submit=False)
            flash("Draft saved")
            st.rerun()
        if c2.button("📨 Submit for approval", type="primary"):
            hrs = edited["Hours"].fillna(0)
            bad = edited[edited["Type"].isin(["Leave", "Holiday", "Off"]) & (hrs > 0)]
            if s["hours"] <= 0:
                st.error("Enter your hours before submitting.")
            elif not bad.empty:
                st.error("Hours entered on Leave / Holiday / Off days: " + ", ".join(bad["Date"]) +
                         ". Change the Type or set hours to 0.")
            else:
                save_timesheet(user["id"], ym, edited, submit=True)
                flash("📨 Timesheet submitted for approval")
                st.rerun()


def page_emp_requests():
    header("🏠", "Leave & WFH", "Request time off or a work-from-home period")
    user = st.session_state.user
    mine = run("SELECT * FROM requests WHERE employee_id=? ORDER BY id DESC", (user["id"],), fetch=True)
    yr, ym = str(date.today().year), date.today().strftime("%Y-%m")
    leave_days = sum(r["days"] or 0 for r in mine
                     if r["kind"] == "Leave" and r["status"] == "Approved" and r["start_date"].startswith(yr))
    wfh_days = sum(r["days"] or 0 for r in mine
                   if r["kind"] == "WFH" and r["status"] == "Approved" and r["start_date"].startswith(ym))
    m = st.columns(3)
    m[0].metric("Approved leave days (this year)", leave_days)
    m[1].metric("Approved WFH days (this month)", wfh_days)
    m[2].metric("Pending requests", sum(r["status"] == "Pending" for r in mine))

    tab_new, tab_hist = st.tabs(["➕ New request", "My requests"])
    with tab_new:
        with st.form("new_req", clear_on_submit=True):
            kind = st.radio("Request type", ["Leave", "WFH"], horizontal=True,
                            format_func=lambda k: "Leave" if k == "Leave" else "Work from home")
            leave_type = st.selectbox("Leave type (leave requests only)", LEAVE_TYPES)
            c1, c2 = st.columns(2)
            start = c1.date_input("From", value=date.today())
            end = c2.date_input("To", value=date.today())
            reason = st.text_area("Reason")
            if st.form_submit_button("Submit request", type="primary"):
                if end < start:
                    st.error("The end date is before the start date.")
                elif count_workdays(start, end) == 0:
                    st.error("The selected dates are all weekend days.")
                elif not reason.strip():
                    st.error("Please add a short reason.")
                elif run("""SELECT 1 FROM requests WHERE employee_id=? AND status IN ('Pending','Approved')
                            AND start_date<=? AND end_date>=?""",
                         (user["id"], end.isoformat(), start.isoformat()), fetch=True):
                    st.error("You already have a pending or approved request overlapping these dates.")
                else:
                    run("""INSERT INTO requests(employee_id,kind,leave_type,start_date,end_date,days,reason,created_at)
                           VALUES(?,?,?,?,?,?,?,?)""",
                        (user["id"], kind, leave_type if kind == "Leave" else None, start.isoformat(),
                         end.isoformat(), count_workdays(start, end), reason.strip(), now()))
                    flash("📨 Request sent to your manager")
                    st.rerun()

    with tab_hist:
        if not mine:
            st.info("No requests yet.")
        for r in [x for x in mine if x["status"] == "Pending"]:
            with st.container(border=True):
                a, b = st.columns([5, 1])
                label = "Work from home" if r["kind"] == "WFH" else f"{r['leave_type']} leave"
                a.markdown(f"🟡 **{label}** · {r['start_date']} → {r['end_date']} · {r['days']} working day(s)  \n{r['reason']}")
                if b.button("Cancel", key=f"cn{r['id']}"):
                    run("UPDATE requests SET status='Cancelled' WHERE id=? AND employee_id=?", (r["id"], user["id"]))
                    flash("Request cancelled")
                    st.rerun()
        done = [r for r in mine if r["status"] != "Pending"]
        if done:
            st.subheader("History")
            hist = pd.DataFrame([{
                "Type": "WFH" if r["kind"] == "WFH" else f"{r['leave_type']} leave",
                "From": r["start_date"], "To": r["end_date"], "Days": r["days"],
                "Status": f"{RQ_BADGE[r['status']]} {r['status']}", "Manager note": r["manager_note"] or "",
            } for r in done])
            st.dataframe(hist, hide_index=True)


# ---- manager / admin approvals --------------------------------------------
TS_SQL = """SELECT t.*, COALESCE(NULLIF(e.full_name,''), e.username) AS employee,
            COALESCE(NULLIF(v.company,''), NULLIF(v.full_name,''), v.username, '-') AS vendor
            FROM timesheets t JOIN users e ON e.id=t.employee_id LEFT JOIN users v ON v.id=e.vendor_id"""
RQ_SQL = """SELECT r.*, COALESCE(NULLIF(e.full_name,''), e.username) AS employee,
            COALESCE(NULLIF(v.company,''), NULLIF(v.full_name,''), v.username, '-') AS vendor
            FROM requests r JOIN users e ON e.id=r.employee_id LEFT JOIN users v ON v.id=e.vendor_id"""


def decide_item(table, item_id, status, note, label):
    # table is always a hard-coded literal from this module, never user input
    run(f"UPDATE {table} SET status=?, manager_note=?, decided_by=?, decided_at=? WHERE id=?",
        (status, note, st.session_state.user["id"], now(), item_id))
    flash(f"{label} {status.lower()}")
    st.rerun()


@st.dialog("Reject")
def reject_item_dialog(table, item_id, label):
    st.write(f"Rejecting **{label}**. The employee will see your note.")
    note = st.text_area("Reason *")
    if st.button("Confirm rejection", type="primary"):
        if not note.strip():
            st.error("A reason is required.")
        else:
            decide_item(table, item_id, "Rejected", note.strip(), label)


def page_approvals():
    header("✅", "Approvals", "Review timesheets and leave / WFH requests")
    pend_ts = run(TS_SQL + " WHERE t.status='Submitted' ORDER BY t.submitted_at", fetch=True)
    pend_rq = run(RQ_SQL + " WHERE r.status='Pending' ORDER BY r.created_at", fetch=True)
    tab_ts, tab_rq, tab_hist = st.tabs([f"🗓️ Timesheets ({len(pend_ts)})",
                                        f"🏠 Leave & WFH ({len(pend_rq)})", "📜 History"])

    with tab_ts:
        if not pend_ts:
            st.caption("No timesheets waiting for approval.")
        for t in pend_ts:
            entries, who = json.loads(t["entries"]), t["employee"]
            s = ts_summary(entries)
            with st.container(border=True):
                a, b = st.columns([3, 2])
                a.markdown(f"**{who}** · {month_label(t['month'])}  \nVendor: {t['vendor']} · submitted {t['submitted_at']}")
                b.markdown(f"**{s['hours']:.1f} h**  \n{s['office']} office · {s['wfh']} WFH · {s['leave']} leave")
                with st.expander("Daily breakdown"):
                    st.dataframe(pd.DataFrame(entries), hide_index=True)
                x, y, _ = st.columns([1, 1, 4])
                label = f"{who}'s {month_label(t['month'])} timesheet"
                if x.button("Approve", key=f"tsa{t['id']}", type="primary"):
                    decide_item("timesheets", t["id"], "Approved", "", label)
                if y.button("Reject", key=f"tsr{t['id']}"):
                    reject_item_dialog("timesheets", t["id"], label)

    with tab_rq:
        if not pend_rq:
            st.caption("No requests waiting for approval.")
        for r in pend_rq:
            kind = "Work from home" if r["kind"] == "WFH" else f"{r['leave_type']} leave"
            with st.container(border=True):
                st.markdown(f"**{r['employee']}** · {kind}  \nVendor: {r['vendor']} · "
                            f"{r['start_date']} → {r['end_date']} · **{r['days']} working day(s)**")
                st.caption(f"Reason: {r['reason']}")
                x, y, _ = st.columns([1, 1, 4])
                label = f"{r['employee']}'s {kind} request"
                if x.button("Approve", key=f"rqa{r['id']}", type="primary"):
                    decide_item("requests", r["id"], "Approved", "", label)
                if y.button("Reject", key=f"rqr{r['id']}"):
                    reject_item_dialog("requests", r["id"], label)

    with tab_hist:
        st.subheader("Recent timesheet decisions")
        done_ts = run(TS_SQL + " WHERE t.status IN ('Approved','Rejected') ORDER BY t.decided_at DESC LIMIT 30", fetch=True)
        if not done_ts:
            st.caption("Nothing yet.")
        for t in done_ts:
            with st.container(border=True):
                a, b = st.columns([5, 1])
                a.markdown(f"{TS_BADGE[t['status']]} **{t['employee']}** · {month_label(t['month'])} · "
                           f"{t['total_hours']:.1f} h · {t['status']} {t['decided_at']}"
                           + (f"  \n📝 {t['manager_note']}" if t["manager_note"] else ""))
                if t["status"] == "Approved" and b.button("↩ Revoke", key=f"rv{t['id']}",
                                                         help="Pull back to 'Submitted'; the vendor stops seeing it"):
                    run("UPDATE timesheets SET status='Submitted', decided_by=NULL, decided_at=NULL WHERE id=?", (t["id"],))
                    flash("Approval revoked - timesheet is pending again")
                    st.rerun()
        st.subheader("Recent leave / WFH decisions")
        done_rq = run(RQ_SQL + " WHERE r.status IN ('Approved','Rejected') ORDER BY r.decided_at DESC LIMIT 30", fetch=True)
        if done_rq:
            st.dataframe(pd.DataFrame([{
                "Employee": r["employee"], "Vendor": r["vendor"],
                "Type": "WFH" if r["kind"] == "WFH" else f"{r['leave_type']} leave",
                "From": r["start_date"], "To": r["end_date"], "Days": r["days"],
                "Status": f"{RQ_BADGE[r['status']]} {r['status']}", "Note": r["manager_note"] or "",
            } for r in done_rq]), hide_index=True)
        else:
            st.caption("Nothing yet.")


# ---- vendor view of approved timesheets -----------------------------------
def page_vendor_timesheets():
    header("🧾", "Team timesheets", "Approved monthly timesheets for the people you placed")
    uid = st.session_state.user["id"]
    emps = run("SELECT id, COALESCE(NULLIF(full_name,''), username) AS name, designation "
               "FROM users WHERE role='employee' AND vendor_id=? AND approved=1", (uid,), fetch=True)
    if not emps:
        st.info("No employees are linked to your company yet. Employees appear here once they sign up "
                "with you as their vendor (and an admin approves them) or a manager onboards them.")
        return
    rows = run(TS_SQL + " WHERE e.vendor_id=? AND t.status='Approved' ORDER BY t.month DESC, employee",
               (uid,), fetch=True)
    st.caption("Only timesheets approved by the hiring manager are shared with you.")

    c1, c2 = st.columns(2)
    months = ["All months"] + sorted({r["month"] for r in rows}, reverse=True)
    names = ["All employees"] + sorted({e["name"] for e in emps})
    f_month = c1.selectbox("Month", months, format_func=lambda x: x if x == "All months" else month_label(x))
    f_emp = c2.selectbox("Employee", names)
    rows = [r for r in rows if (f_month == "All months" or r["month"] == f_month)
            and (f_emp == "All employees" or r["employee"] == f_emp)]

    m = st.columns(3)
    m[0].metric("Employees", len(emps))
    m[1].metric("Approved timesheets", len(rows))
    m[2].metric("Approved hours", f"{sum(r['total_hours'] or 0 for r in rows):.1f}")
    if not rows:
        st.info("No approved timesheets match the filters yet.")
        return

    summary, flat = [], []
    for r in rows:
        entries = json.loads(r["entries"])
        s = ts_summary(entries)
        summary.append({"Employee": r["employee"], "Month": month_label(r["month"]), "Hours": round(s["hours"], 1),
                        "Office days": s["office"], "WFH days": s["wfh"], "Leave days": s["leave"],
                        "Approved on": r["decided_at"]})
        flat += [{"Employee": r["employee"], "Month": r["month"], **e} for e in entries]
    st.dataframe(pd.DataFrame(summary), hide_index=True)
    st.download_button("⬇ Download daily detail (CSV)", pd.DataFrame(flat).to_csv(index=False),
                       file_name="approved_timesheets.csv", mime="text/csv")
    for r in rows:
        with st.expander(f"{r['employee']} · {month_label(r['month'])} · {r['total_hours']:.1f} h"):
            st.dataframe(pd.DataFrame(json.loads(r["entries"])), hide_index=True)


# --------------------------------------------------------------------------
# Hiring statistics dashboard + employee lifecycle (join / resign / exit)
# --------------------------------------------------------------------------
def fte_for(employment_type):
    """Full-time equivalent used for FTE view when a job / employee has no explicit value."""
    return 0.5 if employment_type in ("Part-time", "Internship") else 1.0


def link_button(label, key):
    try:  # 'tertiary' (link-style) buttons need a recent Streamlit; fall back gracefully
        return st.button(label, key=key, type="tertiary")
    except Exception:
        return st.button(label, key=key)


@st.dialog("Details", width="large")
def details_dialog(title, df, note=""):
    st.subheader(title)
    if note:
        st.caption(note)
    if df.empty:
        st.info("Nothing to show for the selected filters.")
        return
    st.dataframe(df, hide_index=True)
    st.download_button("⬇ Download CSV", df.to_csv(index=False),
                       file_name=title.lower().replace(" ", "_") + ".csv", mime="text/csv")


def hiring_stats(year, dept, fte_view):
    """Build the six KPI cards. Returns (cards, active_employees_df)."""
    today = date.today().isoformat()
    ref = today if year == "All" else min(today, f"{year}-12-31")   # headcount is 'as of' this date

    def in_year(series):
        return pd.Series(True, index=series.index) if year == "All" else series.fillna("").str[:4] == str(year)

    # ---- employees ---------------------------------------------------------
    ecols = ["id", "name", "designation", "department", "fte", "join_date", "resigned_on",
             "exit_date", "exit_reason", "vendor"]
    emps = pd.DataFrame(run("""
        SELECT u.id, COALESCE(NULLIF(u.full_name,''), u.username) AS name, u.designation,
               COALESCE(NULLIF(u.department,''),'Unassigned') AS department, COALESCE(u.fte,1.0) AS fte,
               u.join_date, u.resigned_on, u.exit_date, u.exit_reason,
               COALESCE(NULLIF(v.company,''), NULLIF(v.full_name,''), v.username, '-') AS vendor
        FROM users u LEFT JOIN users v ON v.id=u.vendor_id
        WHERE u.role='employee' AND u.approved=1""", fetch=True), columns=ecols)
    for c in ("join_date", "resigned_on", "exit_date", "exit_reason"):
        emps[c] = emps[c].fillna("")
    emps["w"] = emps["fte"].astype(float) if fte_view else 1.0
    if dept != "All":
        emps = emps[emps.department == dept]

    active = emps[(emps.join_date <= ref) & ((emps.exit_date == "") | (emps.exit_date > ref))].copy()
    active["status"] = ["Serving notice" if (ro and ed > today) else "Active"
                        for ro, ed in zip(active.resigned_on, active.exit_date)]
    notice = emps[(emps.resigned_on != "") & (emps.exit_date > today) & in_year(emps.resigned_on)]
    left = emps[(emps.exit_date != "") & (emps.exit_date <= today) & in_year(emps.exit_date)]

    # ---- candidates (selected / offered) -----------------------------------
    ccols = ["id", "name", "status", "decided_at", "offered_at", "ai_score", "job_title",
             "department", "employment_type", "vendor", "joined"]
    cands = pd.DataFrame(run("""
        SELECT c.id, c.name, c.status, c.decided_at, c.offered_at, c.ai_score, j.title AS job_title,
               COALESCE(NULLIF(j.department,''),'Unassigned') AS department, j.employment_type,
               COALESCE(NULLIF(u.company,''), NULLIF(u.full_name,''), u.username) AS vendor,
               (SELECT COUNT(*) FROM users e WHERE e.candidate_id=c.id) AS joined
        FROM candidates c JOIN jobs j ON j.id=c.job_id JOIN users u ON u.id=c.vendor_id""", fetch=True), columns=ccols)
    cands["decided_at"] = cands.decided_at.fillna("")
    cands["offered_at"] = cands.offered_at.fillna("")
    cands["w"] = cands.employment_type.map(fte_for) if fte_view else 1.0
    if dept != "All":
        cands = cands[cands.department == dept]
    pool = cands[(cands.status == "Accepted") & (cands.joined == 0)]
    selected = pool[(pool.offered_at == "") & in_year(pool.decided_at)]
    offered = pool[(pool.offered_at != "") & in_year(pool.offered_at)]
    submitted = float(cands.w.sum())

    # ---- open positions (always the current picture) -----------------------
    jcols = ["id", "title", "department", "employment_type", "openings", "filled"]
    jobs = pd.DataFrame(run("""
        SELECT j.id, j.title, COALESCE(NULLIF(j.department,''),'Unassigned') AS department,
               j.employment_type, j.openings,
               (SELECT COUNT(*) FROM candidates c WHERE c.job_id=j.id AND c.status='Accepted') AS filled
        FROM jobs j WHERE j.status='Open'""", fetch=True), columns=jcols)
    if dept != "All":
        jobs = jobs[jobs.department == dept]
    jobs["open_n"] = (jobs.openings.astype(float) - jobs.filled.astype(float)).clip(lower=0)
    jobs = jobs[jobs.open_n > 0].copy()
    jobs["w"] = jobs.employment_type.map(fte_for) if fte_view else 1.0

    # ---- numbers -------------------------------------------------------------
    hc = float(active.w.sum())
    op = float((jobs.open_n * jobs.w).sum())
    rs = float(notice.w.sum())
    at = float(left.w.sum())
    sl = float(selected.w.sum())
    of = float(offered.w.sum())
    pct = lambda a, b: (a / b * 100) if b else 0.0

    d_hc = active[["name", "vendor", "department", "designation", "fte", "join_date", "status"]].rename(columns={
        "name": "Employee", "vendor": "Vendor", "department": "Department", "designation": "Title",
        "fte": "FTE", "join_date": "Joined", "status": "Status"})
    d_op = jobs[["title", "department", "employment_type", "openings", "filled", "open_n"]].rename(columns={
        "title": "Job", "department": "Department", "employment_type": "Type", "openings": "Openings",
        "filled": "Filled (accepted)", "open_n": "Still open"})
    d_op["Still open"] = d_op["Still open"].astype(int)
    d_rs = notice[["name", "vendor", "department", "resigned_on", "exit_date", "exit_reason"]].rename(columns={
        "name": "Employee", "vendor": "Vendor", "department": "Department", "resigned_on": "Resigned on",
        "exit_date": "Last working day", "exit_reason": "Reason"})
    d_at = left[["name", "vendor", "department", "join_date", "exit_date", "exit_reason"]].rename(columns={
        "name": "Employee", "vendor": "Vendor", "department": "Department", "join_date": "Joined",
        "exit_date": "Left on", "exit_reason": "Reason"})
    d_sl = selected[["name", "job_title", "department", "vendor", "decided_at", "ai_score"]].rename(columns={
        "name": "Candidate", "job_title": "Job", "department": "Department", "vendor": "Vendor",
        "decided_at": "Selected on", "ai_score": "AI score"})
    d_of = offered[["name", "job_title", "department", "vendor", "offered_at", "ai_score"]].rename(columns={
        "name": "Candidate", "job_title": "Job", "department": "Department", "vendor": "Vendor",
        "offered_at": "Offer released", "ai_score": "AI score"})

    cards = [
        dict(key="hc", title="Headcount", icon="🧑‍💼", value=hc, pct=pct(hc, hc + op),
             basis="of approved positions filled", detail=d_hc,
             note=f"Employees on the team as of {ref}, including anyone serving notice."),
        dict(key="op", title="Open Positions", icon="💼", value=op, pct=pct(op, hc + op),
             basis="of approved positions still open", detail=d_op,
             note="Openings on open jobs minus candidates already accepted. Always the current picture."),
        dict(key="rs", title="Resigned", icon="🚪", value=rs, pct=pct(rs, hc),
             basis="of headcount serving notice", detail=d_rs,
             note="Resignation recorded, last working day still ahead."),
        dict(key="at", title="Attrition", icon="🏃", value=at, pct=pct(at, hc + at),
             basis="of everyone who worked here", detail=d_at,
             note="Employees whose last working day has passed."),
        dict(key="sl", title="Selected", icon="🙋", value=sl, pct=pct(sl, submitted),
             basis="of candidates submitted", detail=d_sl,
             note="Accepted by the manager, offer not released yet."),
        dict(key="of", title="Offered", icon="📝", value=of, pct=pct(of, submitted),
             basis="of candidates submitted", detail=d_of,
             note="Offer released, candidate has not joined yet."),
    ]
    return cards, active


def page_hiring_stats():
    header("📈", "Hiring statistics", "Headcount, open positions, attrition and the offer pipeline")

    years = {date.today().year}
    for r in run("""SELECT substr(join_date,1,4) AS y FROM users WHERE join_date IS NOT NULL
                    UNION SELECT substr(exit_date,1,4) FROM users WHERE exit_date IS NOT NULL
                    UNION SELECT substr(created_at,1,4) FROM candidates
                    UNION SELECT substr(offered_at,1,4) FROM candidates WHERE offered_at IS NOT NULL""", fetch=True):
        try:
            years.add(int(r["y"]))
        except (TypeError, ValueError):
            pass
    depts = sorted({r["d"] for r in run(
        """SELECT COALESCE(NULLIF(department,''),'Unassigned') AS d FROM jobs
           UNION SELECT COALESCE(NULLIF(department,''),'Unassigned') FROM users WHERE role='employee'""", fetch=True)})

    f1, f2, f3, f4 = st.columns([2, 2, 1.4, 1.6])
    year = f1.selectbox("Year", ["All"] + [str(y) for y in sorted(years, reverse=True)])
    dept = f2.selectbox("Department / COE", ["All"] + depts)
    fte_view = f3.toggle("FTE view", help="Off = head count (people). On = full-time equivalents, "
                                         "where a part-timer or intern counts as 0.5.")
    pct_view = f4.toggle("Show percentages", help="Each card shows its share of a sensible base - "
                                                 "the base is printed under the number.")

    cards, active = hiring_stats(year, dept, fte_view)
    for row in (cards[:3], cards[3:]):
        cols = st.columns(3)
        for col, k in zip(cols, row):
            with col, st.container(border=True):
                ic, tx = st.columns([1, 2])
                ic.markdown(f"<div class='kpi-icon'>{k['icon']}</div>", unsafe_allow_html=True)
                if pct_view:
                    val, sub = f"{k['pct']:.1f}%", k["basis"]
                else:
                    val, sub = (f"{k['value']:.1f}" if fte_view else f"{int(round(k['value']))}"), "FTE" if fte_view else "people"
                tx.markdown(f"<div class='kpi-title'>{k['title']}</div><div class='kpi-value'>{val}</div>"
                            f"<div class='kpi-sub'>{sub}</div>", unsafe_allow_html=True)
                if link_button("More Details ›", key=f"md_{k['key']}"):
                    details_dialog(k["title"], k["detail"], k["note"])

    st.caption(f"Headcount is as of {'today' if year == 'All' else 'the end of ' + year}. "
               "Open positions are always current. Resigned = notice period running; Attrition = already left.")

    if not active.empty:
        c1, c2 = st.columns(2)
        unit = "FTE" if fte_view else "Headcount"
        by_dept = active.groupby("department", as_index=False).w.sum()
        fig = px.bar(by_dept, x="w", y="department", orientation="h", labels={"w": unit, "department": ""},
                     title=f"{unit} by department", color_discrete_sequence=["#4F46E5"])
        c1.plotly_chart(style_fig(fig, 320))
        by_v = active.groupby("vendor", as_index=False).w.sum()
        fig = px.bar(by_v, x="w", y="vendor", orientation="h", labels={"w": unit, "vendor": ""},
                     title=f"{unit} by vendor", color_discrete_sequence=["#10B981"])
        c2.plotly_chart(style_fig(fig, 320))


# ---- employees page (manager / admin) ------------------------------------
def page_employees():
    header("🧑‍💻", "Employees", "Department, FTE, joining date and resignations")
    emps = run("""SELECT u.*, COALESCE(NULLIF(v.company,''), NULLIF(v.full_name,''), v.username, '-') AS vendor_name
                  FROM users u LEFT JOIN users v ON v.id=u.vendor_id
                  WHERE u.role='employee' AND u.approved=1 ORDER BY u.id""", fetch=True)
    if not emps:
        st.info("No employees yet. Onboard an accepted candidate from Candidate review, "
                "or approve an employee sign-up in Users.")
        return
    today = date.today().isoformat()

    def state(e):
        if e["exit_date"] and e["exit_date"] <= today:
            return "⚪ Left"
        return "🟠 Serving notice" if e["resigned_on"] else "🟢 Active"

    st.dataframe(pd.DataFrame([{
        "Employee": e["full_name"] or e["username"], "Vendor": e["vendor_name"], "Title": e["designation"],
        "Department": e["department"] or "Unassigned", "FTE": e["fte"], "Joined": e["join_date"],
        "Status": state(e), "Last working day": e["exit_date"],
    } for e in emps]), hide_index=True)

    lookup = {e["id"]: e for e in emps}
    eid = st.selectbox("Select employee", list(lookup),
                       format_func=lambda i: f"{lookup[i]['full_name'] or lookup[i]['username']} ({lookup[i]['vendor_name']})")
    e = lookup[eid]

    with st.container(border=True):
        st.markdown("#### Details")
        c1, c2, c3 = st.columns(3)
        dept = c1.text_input("Department / COE", value=e["department"] or "", key=f"dp{eid}")
        fte = c2.number_input("FTE", 0.1, 1.0, float(e["fte"] or 1.0), 0.1, key=f"ft{eid}")
        jd = c3.date_input("Join date", value=date.fromisoformat(e["join_date"]) if e["join_date"] else date.today(),
                           key=f"jd{eid}")
        if st.button("Save details", key=f"sd{eid}"):
            run("UPDATE users SET department=?, fte=?, join_date=? WHERE id=?", (dept.strip(), fte, jd.isoformat(), eid))
            flash("Employee details saved")
            st.rerun()

    with st.container(border=True):
        st.markdown("#### Resignation / exit")
        if e["resigned_on"]:
            st.info(f"Resigned on {e['resigned_on']} · last working day {e['exit_date']}"
                    + (f" · {e['exit_reason']}" if e["exit_reason"] else ""))
        r1, r2 = st.columns(2)
        resigned = r1.date_input("Resignation date", value=date.fromisoformat(e["resigned_on"]) if e["resigned_on"] else date.today(),
                                 key=f"rd{eid}")
        last_day = r2.date_input("Last working day", value=date.fromisoformat(e["exit_date"]) if e["exit_date"] else date.today() + timedelta(days=30),
                                 key=f"ld{eid}")
        reason = st.text_input("Reason (optional)", value=e["exit_reason"] or "", key=f"rr{eid}")
        b1, b2, _ = st.columns([1.4, 1.4, 3])
        if b1.button("Record resignation", type="primary", key=f"rr_b{eid}"):
            if last_day < resigned:
                st.error("The last working day can't be before the resignation date.")
            else:
                run("UPDATE users SET resigned_on=?, exit_date=?, exit_reason=? WHERE id=?",
                    (resigned.isoformat(), last_day.isoformat(), reason.strip(), eid))
                flash("Resignation recorded - their login stops working after the last working day")
                st.rerun()
        if e["resigned_on"] and b2.button("Withdraw resignation", key=f"wd{eid}"):
            run("UPDATE users SET resigned_on=NULL, exit_date=NULL, exit_reason=NULL WHERE id=?", (eid,))
            flash("Resignation withdrawn")
            st.rerun()


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
PAGES = {
    "admin": [("Hiring stats", "📈", page_hiring_stats), ("Vendor performance", "📊", page_dashboard),
              ("Jobs", "📋", page_jobs), ("Candidate review", "🗂️", page_review),
              ("Approvals", "✅", page_approvals), ("Employees", "🧑‍💻", page_employees),
              ("Users", "👥", page_users)],
    "manager": [("Hiring stats", "📈", page_hiring_stats), ("Vendor performance", "📊", page_dashboard),
                ("Jobs", "📋", page_jobs), ("Candidate review", "🗂️", page_review),
                ("Approvals", "✅", page_approvals), ("Employees", "🧑‍💻", page_employees)],
    "vendor": [("Submit candidates", "📤", page_vendor_submit), ("My submissions", "📁", page_vendor_mine),
               ("Team timesheets", "🧾", page_vendor_timesheets)],
    "employee": [("My timesheet", "🗓️", page_emp_timesheet), ("Leave & WFH", "🏠", page_emp_requests)],
}


def main():
    init_db()
    if "user" not in st.session_state:
        login_view()
        return
    user = st.session_state.user
    msg = st.session_state.pop("flash", None)
    if msg:
        st.toast(msg)
      if LOGO.exists():
        st.logo(str(LOGO), icon_image=str(ICON) if ICON.exists() else None)
    sidebar_account(user)
    if user["role"] == "admin":
        n = run("SELECT COUNT(*) AS n FROM users WHERE approved=0", fetch=True)[0]["n"]
        if n:
            st.sidebar.info(f"🕓 {n} sign-up(s) awaiting approval")
    pages = [st.Page(fn, title=title, icon=icon) for title, icon, fn in PAGES[user["role"]]]
    st.navigation(pages).run()


main()
