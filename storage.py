"""Storage + report logic (pure Python, SQLite). Replaces Store.java and ReportService.java.

Everything lives in the `data/` folder next to this file:
    data/assignments.db   classes, subjects, submissions
    data/uploads/...      proof photos
"""
import io
import os
import re
import shutil
import sqlite3
import time
import zipfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DATA_DIR", ROOT / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"
DB_FILE = DATA_DIR / "assignments.db"
ITEMS = 5  # 5 assignments and 5 class tests per subject
ALLOWED_EXT = (".png", ".jpg", ".jpeg", ".webp")


class BackendError(Exception):
    pass


SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_name TEXT NOT NULL,
    student TEXT NOT NULL,
    UNIQUE (class_name, student)
);
CREATE TABLE IF NOT EXISTS subjects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    class_name TEXT NOT NULL,
    subject TEXT NOT NULL,
    UNIQUE (class_name, subject)
);
CREATE TABLE IF NOT EXISTS submissions (
    class_name TEXT NOT NULL,
    subject TEXT NOT NULL,
    kind TEXT NOT NULL,
    number INTEGER NOT NULL,
    student TEXT NOT NULL,
    proof TEXT NOT NULL,
    submitted_at TEXT NOT NULL,
    PRIMARY KEY (class_name, subject, kind, number, student)
);
"""


def clean(text):
    """Same idea as Store.clean(): no tabs/newlines, trimmed."""
    return re.sub(r"[\t\r\n]+", " ", str(text or "")).strip()


def _safe(text):
    return re.sub(r"[^A-Za-z0-9_-]+", "_", str(text)).strip("_") or "x"


@contextmanager
def _db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_FILE, timeout=30)  # waits if two students submit together
    try:
        con.executescript(SCHEMA)
        yield con
        con.commit()
    finally:
        con.close()


# ---------------------------------------------------------------- classes, students, subjects
def set_students(class_name, names):
    cls = clean(class_name)
    if not cls:
        raise BackendError("Class name is empty")
    unique = list(dict.fromkeys(clean(n) for n in names if clean(n)))
    if not unique:
        raise BackendError("Please give at least one student")
    with _db() as con:
        con.execute("DELETE FROM students WHERE class_name = ?", (cls,))
        con.executemany("INSERT INTO students (class_name, student) VALUES (?, ?)", [(cls, s) for s in unique])
        # students who were removed from the list lose their submissions too
        marks = ",".join("?" * len(unique))
        removed = con.execute(
            f"SELECT proof FROM submissions WHERE class_name = ? AND student NOT IN ({marks})", (cls, *unique)
        ).fetchall()
        con.execute(f"DELETE FROM submissions WHERE class_name = ? AND student NOT IN ({marks})", (cls, *unique))
    for (proof,) in removed:
        _remove_proof(proof)


def add_subject(class_name, subject):
    cls, sub = clean(class_name), clean(subject)
    if not cls or not sub:
        return
    with _db() as con:
        con.execute("INSERT OR IGNORE INTO subjects (class_name, subject) VALUES (?, ?)", (cls, sub))


def classes():
    with _db() as con:
        rows = con.execute("SELECT class_name FROM students GROUP BY class_name ORDER BY MIN(id)").fetchall()
    return [r[0] for r in rows]


def students(class_name):
    with _db() as con:
        rows = con.execute(
            "SELECT student FROM students WHERE class_name = ? ORDER BY id", (clean(class_name),)
        ).fetchall()
    return [r[0] for r in rows]


def subjects(class_name):
    with _db() as con:
        rows = con.execute(
            "SELECT subject FROM subjects WHERE class_name = ? ORDER BY id", (clean(class_name),)
        ).fetchall()
    return [r[0] for r in rows]


# ---------------------------------------------------------------- reports (ReportService)
def matrix(class_name, subject, kind):
    """Rows: [name, f1..f5 ('1'/'0'), count]. One row per student in the class."""
    cls, sub = clean(class_name), clean(subject)
    with _db() as con:
        done = {
            (s, n)
            for s, n in con.execute(
                "SELECT student, number FROM submissions WHERE class_name=? AND subject=? AND kind=?",
                (cls, sub, kind),
            )
        }
    rows = []
    for name in students(cls):
        flags = ["1" if (name, n) in done else "0" for n in range(1, ITEMS + 1)]
        rows.append([name] + flags + [str(flags.count("1"))])
    return rows


def single_report(class_name, subject, kind, number):
    """Returns (rows, done, total). Row: [name, '1'/'0', proofPath, time]."""
    cls, sub = clean(class_name), clean(subject)
    with _db() as con:
        found = {
            s: (p, t)
            for s, p, t in con.execute(
                "SELECT student, proof, submitted_at FROM submissions "
                "WHERE class_name=? AND subject=? AND kind=? AND number=?",
                (cls, sub, kind, int(number)),
            )
        }
    rows = []
    for name in students(cls):
        if name in found:
            rows.append([name, "1", str(DATA_DIR / found[name][0]), found[name][1]])
        else:
            rows.append([name, "0", "", ""])
    done = sum(r[1] == "1" for r in rows)
    return rows, done, len(rows)


# ---------------------------------------------------------------- student submission
def _prepare_photo(file_bytes, ext):
    """Shrink big phone photos (keeps the app fast and the backup small)."""
    try:
        from PIL import Image, ImageOps

        img = Image.open(io.BytesIO(file_bytes))
        img = ImageOps.exif_transpose(img)
        img.thumbnail((1600, 1600))
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        out = io.BytesIO()
        img.save(out, "JPEG", quality=82)
        return out.getvalue(), ".jpg"
    except Exception:
        return file_bytes, ext  # Pillow missing or odd file: keep the original bytes


def _remove_proof(rel):
    try:
        (DATA_DIR / rel).unlink(missing_ok=True)
    except OSError:
        pass


def submit(class_name, subject, kind, number, student, filename, file_bytes):
    """Save the proof photo and record the submission. Submitting again replaces the old one."""
    cls, sub, stu = clean(class_name), clean(subject), clean(student)
    kind = str(kind).upper()
    if kind not in ("A", "T"):
        raise BackendError("Type must be A (assignment) or T (test)")
    number = int(number)
    if not 1 <= number <= ITEMS:
        raise BackendError(f"Number must be 1-{ITEMS}")
    if stu not in students(cls):
        raise BackendError(f"Student not in class list: {stu}")
    if sub not in subjects(cls):
        raise BackendError(f"Unknown subject: {sub}")
    if not file_bytes:
        raise BackendError("Please attach a photo")

    ext = Path(filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        ext = ".jpg"
    file_bytes, ext = _prepare_photo(file_bytes, ext)

    folder = UPLOAD_DIR / _safe(cls) / _safe(sub)
    folder.mkdir(parents=True, exist_ok=True)
    proof = folder / f"{kind}{number}_{_safe(stu)}_{int(time.time())}{ext}"
    proof.write_bytes(file_bytes)
    rel = proof.relative_to(DATA_DIR).as_posix()

    try:
        with _db() as con:
            old = con.execute(
                "SELECT proof FROM submissions WHERE class_name=? AND subject=? AND kind=? AND number=? AND student=?",
                (cls, sub, kind, number, stu),
            ).fetchone()
            con.execute(
                "INSERT OR REPLACE INTO submissions VALUES (?,?,?,?,?,?,?)",
                (cls, sub, kind, number, stu, rel, datetime.now().replace(microsecond=0).isoformat()),
            )
    except Exception:
        proof.unlink(missing_ok=True)
        raise
    if old and old[0] != rel:
        _remove_proof(old[0])


# ---------------------------------------------------------------- backup / restore
def make_backup():
    """Zip of the database and all photos (download it before the app restarts)."""
    with _db():
        pass  # make sure the files exist
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(DB_FILE, "assignments.db")
        for f in UPLOAD_DIR.rglob("*"):
            if f.is_file():
                z.write(f, "uploads/" + f.relative_to(UPLOAD_DIR).as_posix())
    return buf.getvalue()


def restore_backup(zip_bytes):
    """Replace all current data with a backup made by make_backup()."""
    try:
        z = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile:
        raise BackendError("That is not a valid backup zip")
    names = z.namelist()
    if "assignments.db" not in names:
        raise BackendError("This zip is not an Assignment Tracker backup")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    base = DATA_DIR.resolve()
    if UPLOAD_DIR.exists():
        shutil.rmtree(UPLOAD_DIR)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    for name in names:
        if name.endswith("/") or not (name == "assignments.db" or name.startswith("uploads/")):
            continue
        target = (DATA_DIR / name).resolve()
        if base not in target.parents:  # block ../ tricks
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(z.read(name))
    with _db() as con:  # confirm the restored database opens
        con.execute("SELECT COUNT(*) FROM students").fetchone()
