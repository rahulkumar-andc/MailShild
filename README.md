# MailShield AI

MailShield AI is a Python Django-based backend service designed for ethical security researchers, students, and bug bounty hunters. It hooks directly into Gmail (via IMAP) and Instagram (via instagrapi) to scan incoming messages every 5 minutes and uses Anthropic's Claude 3.5 Sonnet to classify them securely. Important and potentially malicious messages are triaged and sent as push notifications via `ntfy.sh`.

## Features
- **Automated Fetching**: Runs headless via Celery + Redis, polling Gmail and Instagram Direct every 5 minutes.
- **AI Classification**: Routes all messages to Anthropic's API for intelligent reading. Categorizes them (e.g. COLLEGE, PHISHING, COLLAB, THREAT) and assigns a spam index (0-100).
- **Push Alerts**: Urgent and high-priority messages ping your devices via ntfy.sh immediately.
- **Database Safety & Indexing**: Uses SQLite/Postgres to handle deduplication logic, ensuring you are never double-alerted.
- **Visual Dashboard**: Local web UI matching modern security interfaces allowing you to quickly filter and inspect classified items.

## Setup Instructions

1. **Clone the repo and configure environment:**
   ```bash
   git clone https://github.com/rahulkumar-andc/MailShild.git
   cd MailShild
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Configure `.env`**:
   Copy the `.*env.example*` config or create your `.env`:
   ```bash
   cp .env.example .env
   ```
   Add your `ANTHROPIC_API_KEY`, Instagram credentials, and a Gmail App Password.

3. **Migrate the Database**:
   ```bash
   python manage.py makemigrations
   python manage.py migrate
   ```

4. **Start the Infrastructure**:
   You need Redis running locally. Then start:
   
   Run Django Server (Dashboard on `http://localhost:8000`):
   ```bash
   python manage.py runserver
   ```
   Run Celery Worker (In a new terminal):
   ```bash
   celery -A config worker -l info
   ```
   Run Celery Beat (In a new terminal):
   ```bash
   celery -A config beat -l info
   ```

## DRY_RUN Mode
In your `.env` there is a `DRY_RUN=True` flag enabled. This allows you to test the API fetching logic and view logs WITHOUT pushing mobile notifications via `ntfy`. Change this to `False` once you have validated the fetch logic.

## ntfy.sh Setup
ntfy is a free push-alert notification app. Define `NTFY_TOPIC=sometopic123` in `.env`, and subscribe to that same topic using the ntfy.sh mobile client (iOS/Android) or via the desktop app securely and anonymously.
