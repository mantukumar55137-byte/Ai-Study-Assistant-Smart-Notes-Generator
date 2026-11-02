import os, json, requests
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
import fitz
from docx import Document as DocxDocument

load_dotenv()
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "change-this-development-key")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///study_assistant.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
app.config["UPLOAD_FOLDER"] = os.path.join(app.root_path, "uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
ALLOWED_EXTENSIONS = {"pdf", "docx", "txt"}

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class StudyDocument(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    original_name = db.Column(db.String(255), nullable=False)
    stored_name = db.Column(db.String(255), nullable=False)
    extracted_text = db.Column(db.Text, default="")
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

class Note(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    document_id = db.Column(db.Integer, db.ForeignKey("study_document.id"))
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Quiz(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    questions_json = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_text(path, ext):
    if ext == "pdf":
        doc = fitz.open(path)
        return "\n".join(page.get_text() for page in doc)
    if ext == "docx":
        doc = DocxDocument(path)
        return "\n".join(p.text for p in doc.paragraphs)
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()

def ai_generate(prompt):
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()
    if not api_key or api_key.lower() in {"your_gemini_api_key_here", "your_api_key_here", "replace_me", "placeholder"}:
        raise RuntimeError("Gemini API key is not configured. Add GEMINI_API_KEY to your .env file, then restart the app.")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
    payload = {
        "systemInstruction": {
            "parts": [{"text": "You are a careful academic study assistant. Use the supplied source material. If it does not contain the answer, say so."}]
        },
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": 1200,
            "temperature": 0.4,
            "thinkingConfig": {"thinkingLevel": "MINIMAL"}
        }
    }
    response = requests.post(url, headers=headers, json=payload, timeout=90)
    if response.status_code == 401:
        raise RuntimeError("Google rejected the Gemini API key (HTTP 401). Check GEMINI_API_KEY in .env and restart the app.")
    if response.status_code == 403:
        raise RuntimeError("Gemini denied the request (HTTP 403). Check that the Gemini API is enabled for the Google AI Studio project associated with this key.")
    if response.status_code == 429:
        raise RuntimeError("Gemini rate limit or free-tier quota reached. Check your Google AI Studio usage and limits, then try again later.")
    if response.status_code >= 400:
        detail = response.text[:500].strip()
        raise RuntimeError(f"Gemini API returned HTTP {response.status_code}: {detail or 'No error details returned.'}")
    data = response.json()
    candidates = data.get("candidates", [])
    if not candidates:
        reason = data.get("promptFeedback", {}).get("blockReason", "No response candidate was returned.")
        raise RuntimeError(f"Gemini could not generate a response: {reason}")
    text = "".join(part.get("text", "") for part in candidates[0].get("content", {}).get("parts", []))
    if not text.strip():
        raise RuntimeError("Gemini returned an empty response. Try again or use a shorter document.")
    return text.strip()

@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    return render_template("landing.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not name or not email or len(password) < 8:
            flash("Enter your name, a valid email and a password of at least 8 characters.", "error")
        elif User.query.filter_by(email=email).first():
            flash("An account with that email already exists.", "error")
        else:
            user = User(name=name, email=email, password_hash=generate_password_hash(password))
            db.session.add(user); db.session.commit()
            login_user(user)
            return redirect(url_for("dashboard"))
    return render_template("auth.html", mode="Register")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(email=request.form.get("email", "").strip().lower()).first()
        if user and check_password_hash(user.password_hash, request.form.get("password", "")):
            login_user(user)
            return redirect(url_for("dashboard"))
        flash("Incorrect email or password.", "error")
    return render_template("auth.html", mode="Login")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))

@app.route("/dashboard")
@login_required
def dashboard():
    docs = StudyDocument.query.filter_by(user_id=current_user.id).order_by(StudyDocument.uploaded_at.desc()).all()
    notes = Note.query.filter_by(user_id=current_user.id).order_by(Note.created_at.desc()).limit(5).all()
    quizzes = Quiz.query.filter_by(user_id=current_user.id).count()
    return render_template("dashboard.html", docs=docs, notes=notes, quiz_count=quizzes)

@app.route("/documents", methods=["GET", "POST"])
@login_required
def documents():
    if request.method == "POST":
        f = request.files.get("document")
        if not f or not f.filename:
            flash("Choose a file first.", "error")
        elif not allowed_file(f.filename):
            flash("Only PDF, DOCX and TXT files are supported.", "error")
        else:
            original = secure_filename(f.filename)
            stored = f"{current_user.id}_{int(datetime.utcnow().timestamp())}_{original}"
            path = os.path.join(app.config["UPLOAD_FOLDER"], stored)
            f.save(path)
            try:
                content = extract_text(path, original.rsplit(".", 1)[1].lower())
                if not content.strip():
                    raise ValueError("No readable text was found in this document.")
                item = StudyDocument(user_id=current_user.id, original_name=original, stored_name=stored, extracted_text=content[:100000])
                db.session.add(item); db.session.commit()
                flash("Document uploaded and text extracted successfully.", "success")
            except Exception as e:
                if os.path.exists(path): os.remove(path)
                flash(f"Could not process document: {e}", "error")
        return redirect(url_for("documents"))
    docs = StudyDocument.query.filter_by(user_id=current_user.id).order_by(StudyDocument.uploaded_at.desc()).all()
    return render_template("documents.html", docs=docs)

@app.route("/documents/delete/<int:doc_id>", methods=["POST"])
@login_required
def delete_document(doc_id):
    doc = StudyDocument.query.filter_by(id=doc_id, user_id=current_user.id).first_or_404()
    path = os.path.join(app.config["UPLOAD_FOLDER"], doc.stored_name)
    if os.path.exists(path): os.remove(path)
    Note.query.filter_by(document_id=doc.id, user_id=current_user.id).delete()
    db.session.delete(doc); db.session.commit()
    flash("Document deleted.", "success")
    return redirect(url_for("documents"))

@app.route("/notes", methods=["GET", "POST"])
@login_required
def notes():
    docs = StudyDocument.query.filter_by(user_id=current_user.id).all()
    if request.method == "POST":
        doc = StudyDocument.query.filter_by(id=request.form.get("document_id", type=int), user_id=current_user.id).first()
        if not doc:
            flash("Select one of your uploaded documents.", "error")
            return redirect(url_for("notes"))
        style = request.form.get("style", "Exam-oriented notes")
        language = request.form.get("language", "English")
        prompt = f"Create {style} in {language}. Use clear headings, subheadings, definitions and bullet points. Do not invent facts. Source material:\n\n{doc.extracted_text[:14000]}"
        try:
            content = ai_generate(prompt)
            note = Note(user_id=current_user.id, document_id=doc.id, title=f"{style}: {doc.original_name}", content=content)
            db.session.add(note); db.session.commit()
            return redirect(url_for("view_note", note_id=note.id))
        except Exception as e:
            flash(str(e), "error")
    return render_template("notes.html", docs=docs)

@app.route("/notes/<int:note_id>")
@login_required
def view_note(note_id):
    note = Note.query.filter_by(id=note_id, user_id=current_user.id).first_or_404()
    return render_template("view_note.html", note=note)

@app.route("/chat", methods=["GET", "POST"])
@login_required
def chat():
    docs = StudyDocument.query.filter_by(user_id=current_user.id).all()
    answer = None
    if request.method == "POST":
        doc = StudyDocument.query.filter_by(id=request.form.get("document_id", type=int), user_id=current_user.id).first()
        question = request.form.get("question", "").strip()
        if not doc or not question:
            flash("Choose a document and enter a question.", "error")
        else:
            try:
                answer = ai_generate(f"Answer the student's question using only the source below. If the answer is not present, clearly say that.\\nSOURCE:\\n{doc.extracted_text[:12000]}\\nQUESTION: {question}")
            except Exception as e:
                flash(str(e), "error")
    return render_template("chat.html", docs=docs, answer=answer)

@app.route("/quiz", methods=["GET", "POST"])
@login_required
def quiz():
    docs = StudyDocument.query.filter_by(user_id=current_user.id).all()
    quiz_data = None
    if request.method == "POST":
        doc = StudyDocument.query.filter_by(id=request.form.get("document_id", type=int), user_id=current_user.id).first()
        count = max(3, min(15, request.form.get("count", 5, type=int)))
        if not doc:
            flash("Choose one of your documents.", "error")
        else:
            try:
                raw = ai_generate(f"""Create exactly {count} multiple-choice questions from this source. Return ONLY valid JSON array. Each object must have keys: question, options (array of exactly 4 strings), answer (exactly one option string), explanation. Source:\n{doc.extracted_text[:12000]}""")
                raw = raw.replace("```json", "").replace("```", "").strip()
                quiz_data = json.loads(raw)
                if not isinstance(quiz_data, list) or not quiz_data:
                    raise ValueError("AI did not return a valid question list.")
                saved = Quiz(user_id=current_user.id, title=f"Quiz: {doc.original_name}", questions_json=json.dumps(quiz_data))
                db.session.add(saved); db.session.commit()
            except Exception as e:
                flash(f"Quiz generation failed: {e}", "error")
    return render_template("quiz.html", docs=docs, quiz_data=quiz_data)

@app.route("/api/grade", methods=["POST"])
@login_required
def grade():
    payload = request.get_json(force=True)
    questions = payload.get("questions", [])
    answers = payload.get("answers", {})
    score = sum(1 for i, q in enumerate(questions) if answers.get(str(i)) == q.get("answer"))
    return jsonify({"score": score, "total": len(questions), "percentage": round(score / len(questions) * 100, 1) if questions else 0})

@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        current_user.name = request.form.get("name", current_user.name).strip()
        new_password = request.form.get("new_password", "")
        if new_password:
            if len(new_password) < 8:
                flash("New password must contain at least 8 characters.", "error")
                return redirect(url_for("profile"))
            current_user.password_hash = generate_password_hash(new_password)
        db.session.commit()
        flash("Profile updated.", "success")
    return render_template("profile.html")

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=os.getenv("FLASK_DEBUG", "false").lower() == "true")
