# Lifestyle Lens - Property Assessment Dashboard

## Setup Instructions

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Environment Variables

Create a `.env` file in the root directory with your Google API key and (optionally) SMTP settings for sending automated emails:

```
GEMINI_API_KEY=your_gemini_api_key_here
# Optional: SMTP settings for automailer
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=your_smtp_user
SMTP_PASS=your_smtp_password
SMTP_FROM=noreply@example.com
# Optional: admin notification address used by the app
ADMIN_EMAIL=admin@example.com
```

If you do not configure SMTP, the admin email sending feature will return a helpful error and you can use the `/admin/test-email` endpoint to validate configuration.
User management & login behavior:

- When adding a user from the Admin UI, the app auto-generates a temporary password (or you can provide one). The admin response includes the temporary password and the system will attempt to email credentials (or save to `backend/outbox` when SMTP is unavailable).
- Users can log in using their **email** (or full name) and the temporary password. They should then use the password-reset flow to set a permanent password.
Troubleshooting SMTP errors:

- If you see a runtime message like `SMTP not configured: SMTP_HOST is missing` or a 400/500 when sending emails, ensure `.env` contains the SMTP settings above and restart the server.
- For local testing without a real SMTP server, run a debug SMTP server:

```bash
python -m smtpd -c DebuggingServer -n localhost:1025
```

then set:

```
SMTP_HOST=localhost
SMTP_PORT=1025
```

- If `SMTP_HOST` is not set, the app will save outgoing emails to `backend/outbox` by default. To attempt sending to a local SMTP server instead, set `SMTP_DEBUG=1` (and optionally `SMTP_DEBUG_HOST` and `SMTP_DEBUG_PORT`) and run a local SMTP server (for example `python -m smtpd -n -c DebuggingServer localhost:1025` or use a Windows tool like `smtp4dev`). If sending is attempted but fails, the message will fall back to `backend/outbox` and the API will return `{"status": "saved", "message": "saved-to-outbox:/path/to/file.eml"}` so you can inspect the message.

- You can manage saved messages from the Admin UI: click **Outbox** on the Admin page to list files, view a message, or attempt to resend it once SMTP is configured (the UI triggers `/admin/outbox` and `/admin/outbox/resend`).
- The app also includes an **automatic outbox retry worker** that will periodically attempt to resend saved `.eml` files when SMTP is configured (or when `SMTP_DEBUG=1` is set to test a local SMTP). Configure the behavior with environment variables:
  - `SMTP_OUTBOX_AUTO_RETRY` (default `1`) — enable/disable auto resend
  - `SMTP_OUTBOX_RETRY_INTERVAL` (default `60`) — retry interval in seconds
  If a resend succeeds the `.eml` file is removed from `backend/outbox`. If it fails it remains for manual inspection.

- Check the server console logs for details such as: `SMTP login failed: ...`, `starttls failed: ...`, or `SMTP send failed: ...`. Share those messages if you need help diagnosing them.

### 3. Run the Application

**Option 1: Using Python script (Recommended)**

```bash
cd backend
python run_server.py
```

**Option 2: Using uvicorn with full module path**

```bash
cd backend
python -m uvicorn main:app --reload
```

**Option 3: Direct uvicorn call (Alternative)**

```bash
python -m uvicorn backend.main:app --reload 
```

The application will be available at `http://localhost:8000`

## Troubleshooting

### "Error loading ASGI app" Error

If you get the error "Could not import module 'main'", ensure:

1. You're in the `backend/` directory when running the server
2. All dependencies are installed: `pip install -r requirements.txt`
3. Your `.env` file exists in the root directory with `GEMINI_API_KEY` set
4. Use the `run_server.py` script or the full module path approach

### Testing the Server

```bash
# Verify all imports work
python startup_test.py

# Test the app directly
python -c "import main; print('App loaded successfully')"
```

## Project Structure

```
UI/
├── backend/
│   ├── main.py              # FastAPI application
│   ├── gemini_engine.py     # Gemini AI integration
│   └── uploads/             # Uploaded images
├── templates/
│   ├── index.html           # Search page
│   ├── processing.html      # Processing page
│   └── result.html          # Results dashboard
├── requirements.txt         # Python dependencies
└── README.md               # This file
```

## Features

- 🏠 Property Risk Assessment
- 📊 Real-time Analytics Dashboard
- 🎨 Beautiful UI with Tailwind CSS
- 🔄 Real-time data updates
- 📈 Comprehensive scoring breakdown
- 💫 Smooth animations and transitions
