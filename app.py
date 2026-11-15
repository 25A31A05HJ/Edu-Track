"""📚 Assignment Tracker - 100% Python (Streamlit + SQLite). No Java needed.

Run:      streamlit run app.py
Teacher:  open the base link, enter the PIN.
Student:  open the link the teacher shares:  https://<your-app>.streamlit.app/?class=CSE-A
"""
import hmac
import os
from urllib.parse import quote

import pandas as pd
import streamlit as st

import storage
from storage import BackendError

ITEMS = storage.ITEMS
KIND_LABEL = {"A": "📝 Assignment", "T": "🧪 Class Test"}


def get_teacher_pin():
    """PIN from Streamlit secrets (cloud), then environment variable, then the default."""
    try:
        return str(st.secrets["TEACHER_PIN"])
    except Exception:
        return os.environ.get("TEACHER_PIN", "teacher123")


st.set_page_config(page_title="Assignment Tracker", page_icon="📚", layout="wide")

# ---------- look & feel: soft, calm study colours ----------
st.markdown(
    """
    <style>
    .stApp {
        background: linear-gradient(135deg, #e8f1fb 0%, #f3ecfb 50%, #fdf3e7 100%);
    }
    h1, h2, h3 { color: #2b3a67; }
    .hero {
        background: linear-gradient(90deg, #3a5ba0, #6c63b5);
        color: white; padding: 22px 28px; border-radius: 18px;
        margin-bottom: 18px; box-shadow: 0 4px 14px rgba(58,91,160,.25);
    }
    .hero h1 { color: white; margin: 0; font-size: 2rem; }
    .hero p { margin: 4px 0 0 0; opacity: .92; }
    .count-card {
        background: white; border-left: 6px solid #4caf8e; border-radius: 12px;
        padding: 12px 18px; margin: 8px 0 14px 0;
        box-shadow: 0 2px 8px rgba(0,0,0,.06); color: #2b3a67; font-size: 1.1rem;
    }
    div[data-testid="stForm"], div[data-testid="stExpander"] {
        background: rgba(255,255,255,.75); border-radius: 14px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def hero(title, subtitle):
    st.markdown(f'<div class="hero"><h1>{title}</h1><p>{subtitle}</p></div>', unsafe_allow_html=True)


def tick(flag):
    return "✅" if flag == "1" else "⬜"


def flash(key):
    """Show (once) a message saved before a rerun."""
    msg = st.session_state.pop(key, None)
    if msg:
        st.success(msg)


def detect_base_url():
    """The address the app is running at (so the student link is right without typing)."""
    try:
        headers = st.context.headers
        host = headers.get("Host") or headers.get("host")
        if host:
            local = host.startswith(("localhost", "127.0.0.1", "0.0.0.0"))
            proto = headers.get("X-Forwarded-Proto") or ("http" if local else "https")
            return f"{proto.split(',')[0].strip()}://{host}"
    except Exception:
        pass
    return "http://localhost:8501"


# =====================================================================
# STUDENT PAGE  (opened through the link  ?class=<n>)
# =====================================================================
def student_page(class_name):
    hero("🎓 Submit your work", f"🏫 Class: <b>{class_name}</b> &nbsp;|&nbsp; Upload a photo of your completed notebook ✏️")

    if st.session_state.pop("balloons", False):
        st.balloons()
    flash("student_flash")

    names = storage.students(class_name)
    subjects = storage.subjects(class_name)
    if not names or not subjects:
        st.warning("📭 Your teacher has not finished setting up this class yet. Please check back soon.")
        return

    c1, c2 = st.columns(2)
    student = c1.selectbox("🧑‍🎓 Your name", names)
    subject = c2.selectbox("📖 Subject", subjects)

    c3, c4 = st.columns(2)
    kind = c3.radio("What are you submitting?", ["A", "T"], format_func=KIND_LABEL.get, horizontal=True)

    # show which ones this student already finished
    done = {r[0]: r for r in storage.matrix(class_name, subject, kind)}.get(student)
    flags = done[1:1 + ITEMS] if done else ["0"] * ITEMS
    number = c4.selectbox(
        "🔢 Number",
        list(range(1, ITEMS + 1)),
        format_func=lambda n: f"{'Assignment' if kind == 'A' else 'Test'} {n}  {tick(flags[n - 1])}",
    )
    st.caption("✅ = already submitted. Submitting again replaces your earlier photo.")

    n = st.session_state.setdefault("upload_round", 0)  # changing the key clears the pickers after submit
    tab_up, tab_cam = st.tabs(["📁 Upload photo", "📷 Take photo"])
    with tab_up:
        photo = st.file_uploader("Choose the photo of your completed work",
                                 type=["png", "jpg", "jpeg", "webp"], key=f"upload_{n}")
    with tab_cam:
        shot = st.camera_input("Take a clear photo of your page", key=f"camera_{n}")

    chosen = photo or shot
    if chosen is not None:
        st.image(chosen, caption="👀 Preview", width=320)

    if st.button("🚀 Submit as proof", type="primary", disabled=chosen is None):
        try:
            storage.submit(class_name, subject, kind, number, student,
                           getattr(chosen, "name", "camera.jpg"), chosen.getvalue())
            st.session_state["student_flash"] = (
                f"🎉 Submitted! {student} - {subject} - {KIND_LABEL[kind]} {number} ✅")
            st.session_state["balloons"] = True
            st.session_state["upload_round"] = n + 1
            st.rerun()
        except BackendError as e:
            st.error(f"😕 Could not submit: {e}")


# =====================================================================
# TEACHER PAGE
# =====================================================================
def teacher_login():
    hero("🧑‍🏫 Teacher Dashboard", "See who has submitted their assignments and class tests 📊")
    pin = st.text_input("🔒 Teacher PIN", type="password")
    if pin and hmac.compare_digest(pin.encode(), get_teacher_pin().encode()):
        st.session_state["teacher"] = True
        st.rerun()
    elif pin:
        st.error("Wrong PIN")


def setup_tab():
    flash("setup_flash")
    st.subheader("🏫 Create / update a class")
    existing = storage.classes()
    NEW = "➕ New class"
    if "setup_next" in st.session_state:  # set before the picker is drawn (allowed)
        st.session_state["setup_choice"] = st.session_state.pop("setup_next")
    choice = st.selectbox("Class", [NEW] + existing, key="setup_choice")
    is_new = choice == NEW

    with st.form(f"class_form_{choice}"):
        if is_new:
            class_name = st.text_input("Class name (e.g. CSE-A)")
        else:
            class_name = choice
            st.markdown(f"**Class name:** {choice}")
        roster = st.text_area(
            "🧑‍🎓 Student names (one per line - this fixes the class list)",
            height=200,
            value="" if is_new else "\n".join(storage.students(choice)),
        )
        if st.form_submit_button("💾 Save class", type="primary"):
            names = [n.strip() for n in roster.splitlines() if n.strip()]
            if not class_name.strip() or not names:
                st.error("Please give a class name and at least one student.")
            else:
                storage.set_students(class_name, names)
                st.session_state["setup_flash"] = f"Saved {len(set(names))} students in {class_name.strip()} ✅"
                st.session_state["setup_next"] = class_name.strip()
                st.rerun()

    st.subheader("📚 Add a subject")
    existing = storage.classes()
    if not existing:
        st.info("Create a class first.")
        return
    with st.form("subject_form", clear_on_submit=True):
        cls = st.selectbox("Class", existing)
        subject = st.text_input("Subject name (e.g. Data Structures)")
        if st.form_submit_button("➕ Add subject") and subject.strip():
            storage.add_subject(cls, subject)
            st.success(f"Added {subject.strip()} to {cls} 📖")
    for c in existing:
        st.write(f"**{c}** subjects: " + (", ".join(storage.subjects(c)) or "_none yet_"))


def matrix_table(rows, kind):
    cols = [f"{kind}{n}" for n in range(1, ITEMS + 1)]
    total = len(rows)
    body = [[r[0]] + [tick(f) for f in r[1:1 + ITEMS]] + [f"{r[-1]} / {ITEMS}"] for r in rows]
    # last row: how many students submitted each item, out of the whole class
    per_item = [sum(r[n] == "1" for r in rows) for n in range(1, ITEMS + 1)]
    body.append(["📊 Submitted"] + [f"{c} / {total}" for c in per_item] + [""])
    return pd.DataFrame(body, columns=["Student"] + cols + ["Total"])


def reports_tab():
    classes = storage.classes()
    if not classes:
        st.info("📭 No class yet. Create one in the first tab.")
        return
    c1, c2 = st.columns(2)
    cls = c1.selectbox("🏫 Class", classes, key="rep_class")
    subjects = storage.subjects(cls)
    if not subjects:
        st.info("Add a subject for this class first.")
        return
    subject = c2.selectbox("📖 Subject", subjects, key="rep_subject")

    for kind in ("A", "T"):
        st.subheader(f"{KIND_LABEL[kind]}s - {subject}")
        st.dataframe(matrix_table(storage.matrix(cls, subject, kind), kind), hide_index=True)

    st.subheader("🔍 Check one item and see the proof")
    d1, d2 = st.columns(2)
    kind = d1.radio("Type", ["A", "T"], format_func=KIND_LABEL.get, horizontal=True, key="one_kind")
    number = d2.selectbox("Number", list(range(1, ITEMS + 1)), key="one_num")
    rows, done, total = storage.single_report(cls, subject, kind, number)
    st.markdown(
        f'<div class="count-card">🎯 <b>{done}</b> out of <b>{total}</b> students have submitted '
        f'{KIND_LABEL[kind]} {number}</div>',
        unsafe_allow_html=True,
    )
    for name, ok, proof, when in rows:
        if ok == "1":
            with st.expander(f"✅ {name}  -  {when.replace('T', ' ')}"):
                st.image(proof, width=360)
        else:
            st.write(f"⬜ {name}")


def link_tab():
    st.subheader("🔗 Student link")
    classes = storage.classes()
    if not classes:
        st.info("Create a class first.")
        return
    cls = st.selectbox("Class", classes, key="link_class")
    base = st.text_input("Your app address", value=detect_base_url(),
                         help="Filled in automatically. If it looks wrong, paste your app's address here.")
    link = f"{base.rstrip('/')}/?class={quote(cls)}"
    st.success("Share this link with your students 👇")
    st.code(link, language=None)


def backup_tab():
    st.subheader("💾 Backup & restore")
    st.warning(
        "Free hosting (like Streamlit Community Cloud) can reset the app's storage when it restarts "
        "or after a long idle time. **Download a backup after each class setup and regularly during the "
        "term** - you can restore it in one click if the data disappears."
    )
    st.markdown("**1. Download a backup**")
    if st.button("📦 Prepare backup"):
        st.session_state["backup_bytes"] = storage.make_backup()
    if st.session_state.get("backup_bytes"):
        st.download_button("⬇️ Download backup (.zip)", st.session_state["backup_bytes"],
                           file_name="assignment-tracker-backup.zip", mime="application/zip")

    st.markdown("**2. Restore from a backup**")
    up = st.file_uploader("Choose a backup .zip", type=["zip"], key="restore_file")
    sure = st.checkbox("I understand this replaces everything currently in the app")
    if st.button("♻️ Restore", disabled=not (up and sure)):
        try:
            storage.restore_backup(up.getvalue())
            st.session_state.pop("backup_bytes", None)
            st.success("Restored ✅ - classes, subjects and photos are back.")
        except BackendError as e:
            st.error(str(e))


def teacher_page():
    top1, top2 = st.columns([6, 1])
    with top1:
        hero("🧑‍🏫 Teacher Dashboard", "Track assignments ✏️ and class tests 🧪 for every student")
    with top2:
        if st.button("🚪 Logout"):
            st.session_state["teacher"] = False
            st.rerun()
    t1, t2, t3, t4 = st.tabs(["🏫 Class setup", "📊 Reports", "🔗 Student link", "💾 Backup"])
    with t1:
        setup_tab()
    with t2:
        reports_tab()
    with t3:
        link_tab()
    with t4:
        backup_tab()


# ---------- routing ----------
try:
    class_param = st.query_params.get("class")
    if class_param:
        student_page(class_param)
    elif st.session_state.get("teacher"):
        teacher_page()
    else:
        teacher_login()
except BackendError as err:
    st.error(f"⚠️ Backend problem: {err}")
