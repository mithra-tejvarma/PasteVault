# PasteVault

A lightweight, clean, and distraction-free text and code sharing web application built with Python, Flask, and SQLite. PasteVault allows users to quickly publish snippets, logs, or notes and share them via compact, unique URLs with optional expiration and one-click clipboard copying.

This project was built to demonstrate core full-stack web engineering principles—HTTP routing, relational database persistence, server-side validation, clean Jinja2 templating, and essential web security—without unnecessary framework bloat.

---

## Features

- **Text & Code Pastes**: Share plain text, source code, configuration files, or notes.
- **Images & File Attachments**: Attach images (PNG, JPG, GIF, WebP) or files (PDF, code, zip) up to 10 MB. Images are rendered inline with preview and download links.
- **Creator-Only Delete Protection**: Deletion is protected with an unguessable cryptographic token stored in the creator's signed session cookie. Public visitors cannot delete the paste (the delete button is omitted, and unauthorized requests return HTTP 403 Forbidden).
- **Unique Shareable URLs**: Clean 6-character short identifiers (e.g. `/p/Ab12X`).
- **Optional Expiration**: Choose between *Never*, *10 minutes*, *1 hour*, *1 day*, or *7 days*. Expired pastes automatically become unavailable, and attached files are unlinked from disk.
- **View Counter**: Tracks how many times each paste has been viewed.
- **One-Click Clipboard Copying**: Instant buttons to copy the raw paste content or the shareable URL using the browser Clipboard API.
- **Server-Side Validation**: Robust validation preventing empty inputs, oversized files (>10 MB), or oversized payloads (>100 characters for titles, >50,000 characters for content).
- **XSS & Path Traversal Protection**: User content is HTML-escaped by default, and uploaded filenames are sanitized via `secure_filename`.
- **SQLite Persistence & Filesystem Storage**: Relational metadata storage via SQLAlchemy ORM, and streaming file storage on disk.
- **No Account Required**: Instant access without logins, passwords, or authentication overhead.

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Backend** | Python 3, Flask |
| **Database** | SQLite, SQLAlchemy (Flask-SQLAlchemy) |
| **Frontend** | HTML5, CSS3, Vanilla JavaScript |
| **Templating** | Jinja2 |

---

## How It Works

```text
User Submits Form in Browser
        │
        ▼ (HTTP POST /create)
Flask Route (`create_paste`)
        │
        ▼
Server-Side Validation (Title length, non-empty, content <= 50k chars, valid expiry)
        │
        ▼
Generate Collision-Free 6-Char Short ID (`secrets.choice`)
        │
        ▼
SQLAlchemy ORM Model (`Paste`)
        │
        ▼
SQLite Database (`instance/pastevault.db`)
        │
        ▼
HTTP 302 Redirect to `/p/<short_id>`
        │
        ▼
Viewer Accesses Paste (Escaped HTML + CSS `white-space: pre-wrap`)
```

---

## Installation & Running Locally

### 1. Prerequisites
- Python 3.10+ installed on your machine.

### 2. Clone the repository
```bash
git clone https://github.com/your-username/PasteVault.git
cd PasteVault
```

### 3. Create and activate a virtual environment

**On Windows (PowerShell / Command Prompt):**
```bash
python -m venv venv
venv\Scripts\activate
```

**On macOS / Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 4. Install dependencies
```bash
pip install -r requirements.txt
```

### 5. Run the application
```bash
python app.py
```

### 6. Open in your browser
Navigate to:
```text
http://127.0.0.1:5000
```

---

## Project Structure

```text
PasteVault/
│
├── app.py              # Main Flask application, routes, validation, and error handlers
├── models.py           # SQLAlchemy database model (Paste table) and datetime helpers
├── requirements.txt    # Minimal project dependencies (Flask, Flask-SQLAlchemy)
├── test_app.py         # Automated test suite covering the 10 core verification scenarios
├── README.md           # Project documentation and setup guide
├── INTERVIEW_NOTES.md  # 15 technical interview questions & clear, concise answers
├── .gitignore          # Git exclusion rules for venv, cache, and database files
│
├── instance/
│   └── pastevault.db   # Local SQLite database file (created automatically on startup)
│
├── templates/
│   ├── base.html       # Base layout with header, navigation, and flash alert container
│   ├── index.html      # Landing page with hero CTA, how-it-works, and feature highlights
│   ├── create.html     # Paste creation form with validation messages and live counters
│   ├── paste.html      # View paste page with escaped content, copy buttons, and delete action
│   ├── expired.html    # Dedicated view displayed when a paste has exceeded its lifetime
│   └── error.html      # Friendly error page for 404 (Not Found) and 500 (Server Error)
│
└── static/
    ├── css/
    │   └── style.css   # Clean, restrained developer-tool CSS styling
    └── js/
        └── script.js   # Clipboard API integration, live character counters, tab indentation
```

---

## Running the Automated Tests

The project includes unit and integration tests covering paste creation, expiry, view counter increments, deletion, invalid input handling, and 404 responses.

Run tests using:
```bash
python test_app.py
```

---

## Future Improvements

While PasteVault is intentionally kept simple and lightweight as an educational portfolio project, the following features would be natural next steps for a production service:

- **Syntax Highlighting**: Client-side code highlighting (e.g. via Prism.js or highlight.js) based on detected language.
- **User Accounts & Authentication**: Allow registered users to manage an archive of their own pastes.
- **Client-Side End-to-End Encryption**: Encrypt paste text in the browser with AES-GCM before sending it to the server so that even the database administrator cannot read it.
- **Rate Limiting**: Protect creation endpoints from spam using Flask-Limiter.
- **PostgreSQL Support**: Migrate from SQLite to PostgreSQL for multi-node deployments with concurrent writes.
- **Background Expiry Worker**: Periodically purge expired records via Celery or a lightweight cron job rather than lazy deletion upon request.
- **Cloud Deployment**: Containerization with Docker and deployment to AWS ECS, Fly.io, or Render.
