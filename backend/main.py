from fastapi import (
    FastAPI,
    UploadFile,
    File,
    Request,
    BackgroundTasks,
    Form,
    Depends,
    HTTPException,
    status
)
from fastapi.responses import (
    RedirectResponse,
    HTMLResponse,
    JSONResponse,
    StreamingResponse
)
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from typing import List
import os
import uuid
import time
import json
import csv
import io
from gemini_engine import run_full_pipeline
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# -------------------------------------------------
# APP SETUP
# -------------------------------------------------
app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SECRET_KEY", "super-secret-key-change-me"), max_age=None)
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# -------------------------------------------------
# STORAGE
# -------------------------------------------------
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Serve uploaded images
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# -------------------------------------------------
# IN-MEMORY STATE (session-based)
# -------------------------------------------------
PROCESS_STATUS = {}   # session_id → PROCESSING | DONE | ERROR
RESULT_STORE = {}     # session_id → result dict

# -------------------------------------------------
# BACKGROUND PROCESSOR
# -------------------------------------------------
def process_images(session_id: str, session_path: str):
    """
    Process images with Gemini Vision API for real scoring.
    """
    try:
        print(f"\n[{session_id}] Starting analysis...")
        
        # Get image paths
        image_files = [f for f in os.listdir(session_path) 
                      if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))]
        
        if not image_files:
            raise ValueError("No images found in session folder")
        
        image_paths = [os.path.join(session_path, f) for f in image_files]
        print(f"[{session_id}] Found {len(image_paths)} images: {image_files}")
        
        # Run Gemini analysis
        print(f"[{session_id}] Running Gemini Vision analysis...")
        result = run_full_pipeline(image_paths)
        
        analysis = result.get("analysis", {})
        scoring = result.get("scoring", {})
        
        # Determine risk level based on normalized score
        norm_score = scoring.get("normalized_score", 50)
        if norm_score >= 70:
            risk_level = "Low Risk"
        elif norm_score >= 50:
            risk_level = "Medium Risk"
        else:
            risk_level = "High Risk"
        
        # Store results
        RESULT_STORE[session_id] = {
            "overall_score": scoring.get("final_score", 75),
            "normalized_score": norm_score,
            "risk_level": risk_level,
            "exterior_score": scoring.get("exterior_score", 0),
            "interior_score": scoring.get("interior_score", 0),
            "adjusted_exterior_score": scoring.get("adjusted_exterior_score", 0),
            "category_scores": scoring.get("category_scores", {}),
            "analysis": analysis,
            "images": [f"/uploads/{session_id}/{img}" for img in image_files]
        }
        
        PROCESS_STATUS[session_id] = "DONE"
        print(f"[{session_id}] Analysis complete!")
        
    except Exception as e:
        print(f"[{session_id}] Error: {str(e)}")
        PROCESS_STATUS[session_id] = "ERROR"
        RESULT_STORE[session_id] = {
            "error": str(e)
        }

# -------------------------------------------------
# AUTHENTICATION
# -------------------------------------------------

class NotAuthenticated(Exception):
    pass

@app.exception_handler(NotAuthenticated)
async def not_authenticated_handler(request: Request, exc: NotAuthenticated):
    return RedirectResponse(url="/login")

def get_current_user(request: Request):
    user = request.session.get("user")
    if not user:
        raise NotAuthenticated()
    return user

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    # Simple hardcoded credentials for demonstration
    # In production, use a database and hash passwords
    users = ["jeyasri", "jadagesh", "beno", "satish", "george", "dhanush", ]
    if username in users and password == "password123":
        request.session["user"] = username
        return RedirectResponse(url="/", status_code=303)
    
    return templates.TemplateResponse(
        "login.html", 
        {"request": request, "error": "Invalid username or password"}
    )

@app.api_route("/logout", methods=["GET", "POST"])
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)

# -------------------------------------------------
# ROUTES
# -------------------------------------------------

# Landing / Upload page
@app.get("/", response_class=HTMLResponse)
def index(request: Request, user: str = Depends(get_current_user)):
    return templates.TemplateResponse(
        "index.html",
        {"request": request}
    )

# Upload handler
@app.post("/upload")
async def upload_images(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    pincode: str = Form(default=""),
    postoffice: str = Form(default=""),
    district: str = Form(default=""),
    state: str = Form(default=""),
    user: str = Depends(get_current_user)
):
    print("FILES RECEIVED:", len(files))
    session_id = str(uuid.uuid4())
    session_path = os.path.join(UPLOAD_DIR, session_id)
    os.makedirs(session_path, exist_ok=True)

    PROCESS_STATUS[session_id] = "PROCESSING"

    # Save uploaded files
    for file in files:
        file_path = os.path.join(session_path, file.filename)
        with open(file_path, "wb") as f:
            f.write(await file.read())

    # Store location info in session
    LOCATION_DATA = {}  # Will be used to store location per session
    if not hasattr(upload_images, "_locations"):
        upload_images._locations = {}
    upload_images._locations[session_id] = {
        "pincode": pincode,
        "postoffice": postoffice,
        "district": district,
        "state": state
    }

    # Run processing in background
    background_tasks.add_task(
        process_images,
        session_id,
        session_path
    )

    return RedirectResponse(
        url=f"/processing?session_id={session_id}",
        status_code=303
    )

# Processing screen
@app.get("/processing", response_class=HTMLResponse)
def processing(request: Request, session_id: str, user: str = Depends(get_current_user)):
    # Get location data if it exists
    location_data = {}
    if hasattr(upload_images, "_locations") and session_id in upload_images._locations:
        location_data = upload_images._locations[session_id]
    
    return templates.TemplateResponse(
        "processing.html",
        {
            "request": request,
            "session_id": session_id,
            "pincode": location_data.get("pincode", ""),
            "postoffice": location_data.get("postoffice", ""),
            "district": location_data.get("district", ""),
            "state": location_data.get("state", "")
        }
    )

# Status polling endpoint
@app.get("/status")
def status(session_id: str, user: str = Depends(get_current_user)):
    return JSONResponse({
        "status": PROCESS_STATUS.get(session_id, "UNKNOWN")
    })

# Result dashboard
@app.get("/result", response_class=HTMLResponse)
def result(request: Request, session_id: str, user: str = Depends(get_current_user)):
    data = RESULT_STORE.get(session_id)
    
    # Get location data if it exists
    location_data = {}
    if hasattr(upload_images, "_locations") and session_id in upload_images._locations:
        location_data = upload_images._locations[session_id]

    # Handle invalid or failed sessions safely
    if not data or "error" in data:
        return templates.TemplateResponse(
            "result.html",
            {
                "request": request,
                "score": "N/A",
                "risk": "Processing Failed",
                "exterior": 0,
                "interior": 0,
                "images": [],
                "normalized_score": 0,
                "category_scores": {},
                "analysis": {},
                "postoffice": location_data.get("postoffice", ""),
                "district": location_data.get("district", ""),
                "state": location_data.get("state", "")
            }
        )

    return templates.TemplateResponse(
        "result.html",
        {
            "request": request,
            "score": data.get("overall_score", 0),
            "normalized_score": data.get("normalized_score", 0),
            "risk": data.get("risk_level", "Unknown"),
            "exterior": data.get("exterior_score", 0),
            "interior": data.get("interior_score", 0),
            "adjusted_exterior": data.get("adjusted_exterior_score", 0),
            "category_scores": data.get("category_scores", {}),
            "analysis": data.get("analysis", {}),
            "images": data.get("images", []),
            "postoffice": location_data.get("postoffice", ""),
            "district": location_data.get("district", ""),
            "state": location_data.get("state", "")
        }
    )


# JSON API endpoint for real-time dashboard updates
@app.get("/result-json")
def result_json(session_id: str, user: str = Depends(get_current_user)):
    """Return the current result data as JSON for client-side polling"""
    data = RESULT_STORE.get(session_id)
    
    # If data doesn't exist or has error, return a safe default
    if not data or "error" in data:
        return JSONResponse({
            "overall_score": 0,
            "normalized_score": 0,
            "risk_level": "Processing Failed",
            "exterior_score": 0,
            "interior_score": 0,
            "adjusted_exterior_score": 0,
            "category_scores": {},
            "analysis": {},
            "images": [],
            "status": "ERROR" if not data else "READY"
        })
    
    # Return the full result data for dashboard updates
    return JSONResponse({
        "overall_score": data.get("overall_score", 0),
        "normalized_score": data.get("normalized_score", 0),
        "risk_level": data.get("risk_level", "Unknown"),
        "exterior_score": data.get("exterior_score", 0),
        "interior_score": data.get("interior_score", 0),
        "adjusted_exterior_score": data.get("adjusted_exterior_score", 0),
        "category_scores": data.get("category_scores", {}),
        "analysis": data.get("analysis", {}),
        "images": data.get("images", []),
        "status": "READY"
    })


# Debug helper: create a sample result and redirect to it (development only)
@app.get("/debug/fill_result")
def debug_fill_result(user: str = Depends(get_current_user)):
    session_id = str(uuid.uuid4())
    PROCESS_STATUS[session_id] = "DONE"
    RESULT_STORE[session_id] = {
        "overall_score": 112,
        "normalized_score": 74,
        "risk_level": "Low Risk",
        "exterior_score": 72,
        "interior_score": 40,
        "adjusted_exterior_score": 70,
        "category_scores": {"roof": 30, "siding": 25, "landscape": 20},
        "analysis": {"roof": ["minor wear"], "interior": ["good flooring"]},
        "images": []
    }
    return RedirectResponse(url=f"/result?session_id={session_id}", status_code=303)


# -------------------------------------------------
# EXPORT AND SHARE ENDPOINTS
# -------------------------------------------------

@app.post("/export-pdf")
async def export_pdf(request: Request, user: str = Depends(get_current_user)):
    """Generate and export PDF report"""
    try:
        data = await request.json()
        
        # Try to import reportlab for PDF generation
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
            from reportlab.lib.units import inch
            from reportlab.lib import colors
        except ImportError:
            # Fallback: Return a simple text document if reportlab is not installed
            return StreamingResponse(
                iter([f"""
Property Risk Assessment Report
{'='*50}

Overall Risk Score: {data.get('score', 'N/A')} / 150
Normalized Score: {data.get('normalized_score', 'N/A')}%
Risk Level: {data.get('risk', 'N/A')}

BREAKDOWN:
- Exterior Condition: {data.get('exterior', 'N/A')} pts
- Interior Systems: {data.get('interior', 'N/A')} pts

PROPERTY DETAILS:
- Post Office: {data.get('postoffice', 'N/A')}
- District: {data.get('district', 'N/A')}
- State: {data.get('state', 'N/A')}

Generated on: {time.strftime('%Y-%m-%d %H:%M:%S')}
"""]),
                media_type="text/plain",
                headers={"Content-Disposition": "attachment; filename=property-assessment.txt"}
            )
        
        # Create PDF using reportlab
        pdf_buffer = io.BytesIO()
        doc = SimpleDocTemplate(pdf_buffer, pagesize=letter, topMargin=0.5*inch)
        story = []
        
        # Styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#667fea'),
            spaceAfter=12,
            alignment=1
        )
        
        # Add content
        story.append(Paragraph("Property Risk Assessment Report", title_style))
        story.append(Spacer(1, 0.3*inch))
        
        # Key metrics
        data_table = [
            ['Metric', 'Value'],
            ['Overall Risk Score', f"{data.get('score', 'N/A')} / 150"],
            ['Normalized Score', f"{data.get('normalized_score', 'N/A')}%"],
            ['Risk Level', data.get('risk', 'N/A')],
            ['Exterior Condition', f"{data.get('exterior', 'N/A')} pts"],
            ['Interior Systems', f"{data.get('interior', 'N/A')} pts"],
        ]
        
        table = Table(data_table, colWidths=[2.5*inch, 2.5*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#667fea')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 14),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        story.append(table)
        story.append(Spacer(1, 0.3*inch))
        
        # Property details
        story.append(Paragraph("<b>Property Details</b>", styles['Heading2']))
        details_text = f"""
        Post Office: {data.get('postoffice', 'N/A')}<br/>
        District: {data.get('district', 'N/A')}<br/>
        State: {data.get('state', 'N/A')}<br/>
        Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}
        """
        story.append(Paragraph(details_text, styles['BodyText']))
        
        # Build PDF
        doc.build(story)
        pdf_buffer.seek(0)
        
        return StreamingResponse(
            iter([pdf_buffer.getvalue()]),
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=property-assessment.pdf"}
        )
    except Exception as e:
        print(f"PDF Export Error: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/export-csv")
async def export_csv(request: Request, user: str = Depends(get_current_user)):
    """Generate and export CSV report"""
    try:
        data = await request.json()
        
        # Create CSV in memory
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write headers and data
        writer.writerow(['Property Risk Assessment Report'])
        writer.writerow([])
        writer.writerow(['Metric', 'Value'])
        writer.writerow(['Overall Risk Score', f"{data.get('score', 'N/A')} / 150"])
        writer.writerow(['Normalized Score', f"{data.get('normalized_score', 'N/A')}%"])
        writer.writerow(['Risk Level', data.get('risk', 'N/A')])
        writer.writerow(['Exterior Condition', f"{data.get('exterior', 'N/A')} pts"])
        writer.writerow(['Interior Systems', f"{data.get('interior', 'N/A')} pts"])
        writer.writerow([])
        writer.writerow(['Property Details'])
        writer.writerow(['Post Office', data.get('postoffice', 'N/A')])
        writer.writerow(['District', data.get('district', 'N/A')])
        writer.writerow(['State', data.get('state', 'N/A')])
        writer.writerow(['Generated', time.strftime('%Y-%m-%d %H:%M:%S')])
        
        # Return as streaming response
        csv_data = output.getvalue()
        return StreamingResponse(
            iter([csv_data]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=property-assessment.csv"}
        )
    except Exception as e:
        print(f"CSV Export Error: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/generate-share-link")
async def generate_share_link(request: Request, user: str = Depends(get_current_user)):
    """Generate a unique share link for the report"""
    try:
        data = await request.json()
        
        # Generate a unique share ID
        share_id = str(uuid.uuid4())
        
        # Store the share data
        SHARE_STORE = {}
        if not hasattr(app, 'share_store'):
            app.share_store = {}
        
        app.share_store[share_id] = {
            'data': data,
            'created_at': time.time(),
            'expires_at': time.time() + (7 * 24 * 60 * 60)  # 7 days
        }
        
        # Generate the share link
        share_link = f"{request.url.scheme}://{request.url.netloc}/shared-report/{share_id}"
        
        return JSONResponse({
            "share_link": share_link,
            "share_id": share_id
        })
    except Exception as e:
        print(f"Share Link Error: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/shared-report/{share_id}")
async def view_shared_report(share_id: str, request: Request):
    """View a shared report"""
    try:
        if not hasattr(app, 'share_store'):
            app.share_store = {}
        
        if share_id not in app.share_store:
            return HTMLResponse("<h1>Report Not Found</h1><p>This shared report does not exist or has expired.</p>", status_code=404)
        
        share_data = app.share_store[share_id]
        
        # Check if expired
        if time.time() > share_data['expires_at']:
            del app.share_store[share_id]
            return HTMLResponse("<h1>Report Expired</h1><p>This shared report has expired (7 days).</p>", status_code=404)
        
        data = share_data['data']
        
        return templates.TemplateResponse(
            "result.html",
            {
                "request": request,
                "score": data.get("score", "N/A"),
                "normalized_score": data.get("normalized_score", 0),
                "risk": data.get("risk", "Unknown"),
                "exterior": data.get("exterior", 0),
                "interior": data.get("interior", 0),
                "category_scores": {},
                "analysis": {},
                "postoffice": data.get("postoffice", ""),
                "district": data.get("district", ""),
                "state": data.get("state", ""),
                "is_shared_view": True
            }
        )
    except Exception as e:
        print(f"View Shared Report Error: {str(e)}")
        return HTMLResponse(f"<h1>Error</h1><p>{str(e)}</p>", status_code=500)
