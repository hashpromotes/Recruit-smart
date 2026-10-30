
"""===
Vendor Recruitment Hub - Streamlit app
======================================
Roles
  admin    : everything a manager can do + user management
  manager  : creates jobs, reviews candidates (shortlist / accept / reject),
             runs AI ranking, sees the vendor dashboard
  vendor   : sees open jobs, uploads candidate resumes, tracks own submissions

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
from datetime import datetime

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Recruitment Hub", page_icon="🧑‍💼", layout="wide")

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
  role TEXT NOT NULL CHECK(role IN ('admin','manager','vendor')),
  pw_hash TEXT NOT NULL, salt TEXT NOT NULL,
  active INTEGER DEFAULT 1, created_at TEXT
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
  ai_score REAL, ai_details TEXT, created_at TEXT,
  UNIQUE(job_id, email)
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


def create_user(username, password, role, full_name="", company=""):
    h, s = hash_pw(password)
    return run(
        "INSERT INTO users(username,full_name,company,role,pw_hash,salt,created_at) VALUES(?,?,?,?,?,?,?)",
        (username.strip(), full_name.strip(), company.strip(), role, h, s, now()),
    )


@st.cache_resource
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
    if not run("SELECT id FROM users LIMIT 1", fetch=True):
        create_user("admin", os.environ.get("ADMIN_PASSWORD", "Admin@123"), "admin", "Administrator")
    return True


CAND_COLS = """c.id, c.job_id, c.vendor_id, c.name, c.email, c.phone, c.resume_name,
  c.status, c.decision_reason, c.decided_at, c.ai_score, c.ai_details, c.created_at,
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
# Auth
# --------------------------------------------------------------------------
def login_view():
    st.title("🧑‍💼 Recruitment Hub")
    _, mid, _ = st.columns([1, 1, 1])
    with mid:
        with st.form("login"):
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            if st.form_submit_button("Sign in"):
                rows = run("SELECT * FROM users WHERE username=? AND active=1", (u.strip(),), fetch=True)
                if rows and verify_pw(p, rows[0]["pw_hash"], rows[0]["salt"]):
                    st.session_state.user = rows[0]
                    st.rerun()
                else:
                    st.error("Invalid credentials or inactive account.")


def sidebar_account(user):
    st.sidebar.markdown(f"**{user['full_name'] or user['username']}**  \n`{user['role']}`")
    with st.sidebar.expander("Change password"):
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
    if st.sidebar.button("Sign out"):
        st.session_state.clear()
        st.rerun()


# --------------------------------------------------------------------------
# Manager / admin pages
# --------------------------------------------------------------------------
def page_jobs():
    st.header("Job openings")
    user = st.session_state.user
    with st.expander("➕ Create a new job opportunity", expanded=False):
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
            if st.form_submit_button("Publish job"):
                if not title.strip() or not desc.strip():
                    st.error("Title and description are required.")
                else:
                    run("""INSERT INTO jobs(title,department,location,employment_type,experience,
                           required_skills,description,openings,created_by,created_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?)""",
                        (title.strip(), dept, loc, etype, exp, skills, desc, openings, user["id"], now()))
                    st.success("Job published - vendors can now submit candidates.")
                    st.rerun()

    jobs = run("""SELECT j.*, (SELECT COUNT(*) FROM candidates c WHERE c.job_id=j.id) AS submissions,
                  (SELECT COUNT(*) FROM candidates c WHERE c.job_id=j.id AND c.status='Accepted') AS accepted
                  FROM jobs j ORDER BY j.id DESC""", fetch=True)
    if not jobs:
        st.info("No jobs yet.")
        return
    for j in jobs:
        icon = "🟢" if j["status"] == "Open" else "⚪"
        with st.expander(f"{icon} #{j['id']} · {j['title']} · {j['submissions']} submissions · "
                         f"{j['accepted']}/{j['openings']} filled"):
            st.write(f"**Dept:** {j['department'] or '-'} | **Location:** {j['location'] or '-'} | "
                     f"**Type:** {j['employment_type']} | **Experience:** {j['experience'] or '-'}")
            st.write(f"**Skills:** {j['required_skills'] or '-'}")
            st.write(j["description"])
            new_status = "Closed" if j["status"] == "Open" else "Open"
            if st.button(f"{'Close' if new_status == 'Closed' else 'Reopen'} job", key=f"js{j['id']}"):
                run("UPDATE jobs SET status=? WHERE id=?", (new_status, j["id"]))
                st.rerun()


def decide(cid, status, reason=""):
    run("UPDATE candidates SET status=?, decision_reason=?, decided_by=?, decided_at=? WHERE id=?",
        (status, reason, st.session_state.user["id"], now(), cid))
    st.rerun()


def page_review():
    st.header("Candidate review")
    jobs = run("SELECT id,title,status FROM jobs ORDER BY id DESC", fetch=True)
    if not jobs:
        st.info("Create a job first.")
        return
    lookup = {j["id"]: j for j in jobs}
    job_id = st.selectbox("Job", list(lookup), format_func=lambda i: f"#{i} · {lookup[i]['title']} ({lookup[i]['status']})")
    job = run("SELECT * FROM jobs WHERE id=?", (job_id,), fetch=True)[0]

    # ---- AI ranking -------------------------------------------------------
    with st.expander("🤖 AI screening & ranking"):
        methods = st.multiselect("AI methods (if several, scores are averaged)", list(METHODS),
                                 default=["Keyword skills match", "TF-IDF similarity"])
        st.caption("Keyword + TF-IDF run locally and free. Claude / GPT need an API key and give written reasoning.")
        rescore = st.checkbox("Also re-score candidates that already have a score")
        if st.button("Run AI ranking", disabled=not methods):
            targets = [c for c in fetch_candidates(job_id=job_id) if rescore or c["ai_score"] is None]
            if not targets:
                st.info("Nothing to score.")
            else:
                bar, failed = st.progress(0.0), 0
                for i, c in enumerate(targets):
                    text = run("SELECT resume_text FROM candidates WHERE id=?", (c["id"],), fetch=True)[0]["resume_text"] or ""
                    score, details = ai_evaluate(job, text, methods)
                    if score is None:
                        failed += 1
                    else:
                        run("UPDATE candidates SET ai_score=?, ai_details=? WHERE id=?",
                            (score, json.dumps(details), c["id"]))
                    bar.progress((i + 1) / len(targets))
                st.success(f"Scored {len(targets) - failed} candidate(s).")
                if failed:
                    st.warning(f"{failed} failed - check API keys / installed packages.")

    cands = fetch_candidates(job_id=job_id)
    if not cands:
        st.info("No candidates submitted for this job yet.")
        return

    # ---- Bulk action --------------------------------------------------------
    with st.expander("⚡ Bulk reject low scorers"):
        thr = st.slider("Reject 'Submitted' candidates scoring below", 0, 100, 30)
        if st.button("Bulk reject"):
            n = 0
            for c in cands:
                if c["status"] == "Submitted" and c["ai_score"] is not None and c["ai_score"] < thr:
                    run("UPDATE candidates SET status='Rejected', decision_reason=?, decided_by=?, decided_at=? WHERE id=?",
                        (f"Below AI screening threshold ({thr})", st.session_state.user["id"], now(), c["id"]))
                    n += 1
            st.success(f"Rejected {n} candidate(s).")
            st.rerun()

    # ---- Candidate list -----------------------------------------------------
    flt = st.multiselect("Show statuses", STATUSES, default=PENDING + ["Accepted", "Rejected"])
    cands = sorted([c for c in cands if c["status"] in flt],
                   key=lambda c: (c["ai_score"] is None, -(c["ai_score"] or 0)))
    st.caption(f"{len(cands)} candidate(s), ranked by AI score")

    for rank, c in enumerate(cands, 1):
        score = f"{c['ai_score']:.0f}" if c["ai_score"] is not None else "-"
        with st.expander(f"{BADGE[c['status']]} #{rank} · {c['name']} · AI {score}/100 · {c['vendor']} · {c['status']}"):
            left, right = st.columns([2, 1])
            with left:
                st.write(f"📧 {c['email']}  📞 {c['phone'] or '-'}  🏢 Vendor: **{c['vendor']}**")
                if c["ai_details"]:
                    for d in json.loads(c["ai_details"]):
                        s = "n/a" if d["score"] is None else f"{d['score']:.0f}"
                        st.markdown(f"- **{d['method']}** ({s}): {d['note']}")
                else:
                    st.caption("Not scored yet.")
                row = run("SELECT resume_text, resume_blob FROM candidates WHERE id=?", (c["id"],), fetch=True)[0]
                st.text_area("Resume text", row["resume_text"] or "", height=160, disabled=True,
                             key=f"rt{c['id']}")
            with right:
                st.download_button("⬇ Download resume", row["resume_blob"], file_name=c["resume_name"],
                                   key=f"dl{c['id']}")
                reason = st.text_input("Decision note / reject reason", value=c["decision_reason"] or "",
                                       key=f"rs{c['id']}")
                b1, b2, b3 = st.columns(3)
                if b1.button("Shortlist", key=f"sl{c['id']}", disabled=c["status"] == "Shortlisted"):
                    decide(c["id"], "Shortlisted", reason)
                if b2.button("Accept", key=f"ac{c['id']}", disabled=c["status"] == "Accepted"):
                    decide(c["id"], "Accepted", reason)
                if b3.button("Reject", key=f"rj{c['id']}", disabled=c["status"] == "Rejected"):
                    if reason.strip():
                        decide(c["id"], "Rejected", reason)
                    else:
                        st.warning("Add a reason so the vendor gets feedback.")


def page_dashboard():
    st.header("Vendor performance dashboard")
    jobs = run("SELECT id,title FROM jobs ORDER BY id DESC", fetch=True)
    lookup = {0: "All jobs", **{j["id"]: f"#{j['id']} · {j['title']}" for j in jobs}}
    job_id = st.selectbox("Job filter", list(lookup), format_func=lambda i: lookup[i])
    df = pd.DataFrame(fetch_candidates(job_id=job_id or None))
    if df.empty:
        st.info("No candidate data yet.")
        return

    total = len(df)
    acc, rej = (df.status == "Accepted").sum(), (df.status == "Rejected").sum()
    pend = df.status.isin(PENDING).sum()
    m = st.columns(4)
    m[0].metric("Submitted", total)
    m[1].metric("Accepted", f"{acc}  ({acc / total:.0%})")
    m[2].metric("Rejected", f"{rej}  ({rej / total:.0%})")
    m[3].metric("Pending", pend)

    g = df.groupby("vendor")
    out = pd.DataFrame({
        "Submitted": g.size(),
        "Pending": g.status.apply(lambda s: s.isin(PENDING).sum()),
        "Accepted": g.status.apply(lambda s: (s == "Accepted").sum()),
        "Rejected": g.status.apply(lambda s: (s == "Rejected").sum()),
        "Avg AI score": g.ai_score.mean().round(1),
    })
    out["Accepted %"] = (out["Accepted"] / out["Submitted"] * 100).round(1)
    out["Rejected %"] = (out["Rejected"] / out["Submitted"] * 100).round(1)
    decided = (out["Accepted"] + out["Rejected"]).where(lambda x: x > 0)
    out["Acceptance % of decided"] = (out["Accepted"] / decided * 100).round(1)
    out = out.sort_values("Accepted %", ascending=False)

    st.subheader("By vendor")
    st.dataframe(out)
    st.caption("Accepted % / Rejected % are out of everything the vendor submitted; "
               "'Acceptance % of decided' ignores candidates still pending.")
    st.bar_chart(out[["Accepted %", "Rejected %"]])

    st.subheader("Submissions per job")
    st.dataframe(df.groupby("job_title").status.value_counts().unstack(fill_value=0))

    st.subheader("Submissions over time")
    df["day"] = pd.to_datetime(df.created_at).dt.date
    st.line_chart(df.groupby("day").size())


def page_users():
    st.header("User management")
    with st.form("new_user", clear_on_submit=True):
        c1, c2 = st.columns(2)
        username = c1.text_input("Username *")
        role = c2.selectbox("Role", ["manager", "vendor", "admin"])
        full = c1.text_input("Full name")
        company = c2.text_input("Vendor company (for vendors)")
        pw = st.text_input("Temporary password * (min 8 chars)", type="password")
        if st.form_submit_button("Create user"):
            if not username.strip() or len(pw) < 8:
                st.error("Username and a password of 8+ characters are required.")
            elif role == "vendor" and not (company.strip() or full.strip()):
                st.error("Vendors need a company or full name (shown on the dashboard).")
            else:
                try:
                    create_user(username, pw, role, full, company)
                    st.success(f"Created {role} '{username}'.")
                except sqlite3.IntegrityError:
                    st.error("That username already exists.")

    users = run("SELECT id,username,full_name,company,role,active,created_at FROM users ORDER BY id", fetch=True)
    st.dataframe(pd.DataFrame(users))
    lookup = {u["id"]: u for u in users}
    uid = st.selectbox("Manage user", list(lookup), format_func=lambda i: f"{lookup[i]['username']} ({lookup[i]['role']})")
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
    st.header("Submit candidates")
    user = st.session_state.user
    jobs = run("SELECT * FROM jobs WHERE status='Open' ORDER BY id DESC", fetch=True)
    if not jobs:
        st.info("There are no open jobs right now.")
        return
    lookup = {j["id"]: j for j in jobs}
    jid = st.selectbox("Open job", list(lookup), format_func=lambda i: f"#{i} · {lookup[i]['title']} - {lookup[i]['location'] or ''}")
    j = lookup[jid]
    with st.expander("Job details", expanded=True):
        st.write(f"**Experience:** {j['experience'] or '-'} | **Type:** {j['employment_type']} | **Openings:** {j['openings']}")
        st.write(f"**Skills:** {j['required_skills'] or '-'}")
        st.write(j["description"])

    with st.form("submit_candidate", clear_on_submit=True):
        c1, c2 = st.columns(2)
        name = c1.text_input("Candidate name *")
        email = c2.text_input("Candidate email *")
        phone = c1.text_input("Phone")
        f = st.file_uploader("Resume (PDF, DOCX or TXT) *", type=["pdf", "docx", "txt"])
        if st.form_submit_button("Submit candidate"):
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
    st.header("My submissions")
    rows = fetch_candidates(vendor_id=st.session_state.user["id"])
    if not rows:
        st.info("You haven't submitted any candidates yet.")
        return
    df = pd.DataFrame(rows)[["job_title", "name", "email", "status", "decision_reason", "created_at", "decided_at"]]
    df.columns = ["Job", "Candidate", "Email", "Status", "Manager feedback", "Submitted", "Decided"]
    st.dataframe(df)
    total = len(df)
    c = st.columns(3)
    c[0].metric("Submitted", total)
    c[1].metric("Accepted", (df.Status == "Accepted").sum())
    c[2].metric("Rejected", (df.Status == "Rejected").sum())


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------
PAGES = {
    "admin": {"Dashboard": page_dashboard, "Jobs": page_jobs, "Candidate review": page_review, "Users": page_users},
    "manager": {"Dashboard": page_dashboard, "Jobs": page_jobs, "Candidate review": page_review},
    "vendor": {"Submit candidates": page_vendor_submit, "My submissions": page_vendor_mine},
}


def main():
    init_db()
    if "user" not in st.session_state:
        login_view()
        return
    user = st.session_state.user
    sidebar_account(user)
    pages = PAGES[user["role"]]
    choice = st.sidebar.radio("Navigate", list(pages))
    pages[choice]()


main()