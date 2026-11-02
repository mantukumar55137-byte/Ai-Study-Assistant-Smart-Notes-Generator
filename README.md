# AI Study Assistant & Smart Notes Generator

A Flask + SQLite educational web application. It uses the Google Gemini API for AI generation.

## 1. Requirements
- Windows 10/11
- Python 3.11 or newer
- VS Code (recommended)
- Internet connection for hosted AI features

## 2. Open and keep the folder
1. Download and extract `AI_Study_Assistant.zip`.
2. Move the extracted `AI_Study_Assistant` folder to a permanent location, for example `D:\MCA_Projects\AI_Study_Assistant`.
3. Do not run the project from inside the ZIP file.
4. Open VS Code → File → Open Folder → select `AI_Study_Assistant`.

## 3. Install and run (PowerShell terminal)
```powershell
py -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
python app.py
```
Open the address printed in the terminal, usually http://127.0.0.1:5000

If PowerShell blocks activation:
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
```

## 4. Configure AI
1. Open [Google AI Studio](https://aistudio.google.com/app/apikey), sign in, and create a Gemini API key.
2. Open `.env` in VS Code.
3. Replace `your_gemini_api_key_here` with your key. Keep it private; never paste it into HTML/JavaScript or share it publicly.
4. Save `.env` and restart `python app.py`.

The default model is `gemini-3.5-flash-lite`, selected for low latency and cost. You can choose another Gemini API model by changing `GEMINI_MODEL` in `.env`. Google controls model availability, rate limits, pricing and free-tier quotas, which may change. Review Google's data-use terms before sending sensitive documents; free-tier data may be used to improve Google products.

## 5. Main features in this starter
- Register, login and logout
- Private document uploads (PDF, DOCX, TXT)
- Text extraction
- AI notes generation
- Document-grounded question answering
- AI MCQ quiz generation and grading
- Saved notes
- Profile name and password update
- SQLite persistence

## 6. Stop and restart
- Stop server: press `Ctrl + C` in the terminal.
- Restart: reopen terminal, activate `venv`, then run `python app.py`.
- Your database is created under `instance/study_assistant.db`. Uploaded documents are in `uploads/`.

## 7. Important project notes
This is a functional starter intended for local development and learning. Before public deployment, add production-grade CSRF protection, password reset via verified email, secure cookies/HTTPS, request throttling, malware scanning, stronger document storage controls, and comprehensive automated tests. Do not use Flask's debug server in production.
