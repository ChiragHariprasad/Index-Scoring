# Lifestyle Lens - Property Assessment Dashboard

## Setup Instructions

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Environment Variables

Create a `.env` file in the root directory with your Google API key:

```
GEMINI_API_KEY=your_gemini_api_key_here
```

### 3. Run the Application

**Option 1: Using Python script (Recommended)**

```bash
cd backend
python run_server.py
```

**Option 2: Using uvicorn with full module path**

```bash
cd backend
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Option 3: Direct uvicorn call (Alternative)**

```bash
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
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
