# 📚 Assignment Tracker (100% Python - Streamlit)

Teachers fix the class list. Students open a link, pick their name, subject and
assignment/test number (each subject has 5 assignments + 5 class tests), and upload
a photo as proof. The teacher sees a ✅ next to each student and "submitted / total".

No Java. Only Python + Streamlit, so it deploys straight from GitHub.

## Files
| File | Role |
|------|------|
| `app.py` | Streamlit app (teacher dashboard + student upload page) |
| `storage.py` | Storage + report logic (SQLite) - replaces the old Java files |
| `requirements.txt` | `streamlit`, `pandas` |
| `.streamlit/config.toml` | Light theme so the colours look right for everyone |

## Run on your computer
```
pip install -r requirements.txt
streamlit run app.py
```
Open http://localhost:8501 and enter the teacher PIN (default `teacher123`).

## Deploy on Streamlit Community Cloud (free)
1. Create a GitHub repo and upload **all files at the top level** (keep the `.streamlit` folder).
2. Go to https://share.streamlit.io → **Create app** → pick your repo, branch `main`,
   **Main file path:** `app.py` → **Deploy**.
3. Set your own PIN: in the app's **Settings → Secrets** add
   ```
   TEACHER_PIN = "your-pin"
   ```
4. Open the app, log in, create the class and subjects, then go to the **Student link** tab.
   The link is filled in with your live address - copy it and share it.

## Use
1. **Class setup**: pick *New class* (or an existing one), type student names one per line, save. Then add subjects.
2. **Student link**: copy `https://your-app.streamlit.app/?class=CSE-A` and send it to students.
3. **Reports**: ticks per student, `Submitted n / N` per item, and each proof photo.
4. **Backup**: download a backup `.zip` and restore it if the data is ever wiped.

## Important: free hosting can wipe saved data
Streamlit Community Cloud keeps files on a temporary disk. When the app restarts (or sleeps
for a long time and is rebuilt), classes and photos can disappear. That's why the **Backup**
tab exists: download a backup after setting up a class and every few days, and press
*Restore* if needed. For permanent storage you would need an external database.
