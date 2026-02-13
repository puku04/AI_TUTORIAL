import os
import logging
import tempfile
import json
import requests
import speech_recognition as sr
import cv2
import numpy as np
from flask import Flask, request, render_template, jsonify, g
from PIL import Image
import pytesseract
from dotenv import load_dotenv
from extensions import db  # Assuming this is where SQLAlchemy is set up
from sympy import sympify
from routes import main  # Import the Blueprint
from gamification import gamification
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_cors import CORS
from flask_migrate import Migrate
from models import UserAchievement, UserChallenge
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# Load environment variables
load_dotenv()

# Logging setup
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configure Tesseract path
pytesseract.pytesseract.tesseract_cmd = r'D:\Users\ghosh\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'

# Create Flask app
app = Flask(__name__)

# Enable CORS for the Flask app
CORS(app)

# Set the secret key for session management
app.secret_key = 'super-secret-dev-key'

app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///example.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize extensions
db.init_app(app)
migrate = Migrate(app, db)

# Speech recognition
recognizer = sr.Recognizer()
recognizer.energy_threshold = 300
recognizer.dynamic_energy_threshold = True

# Register gamification routes
from gamification import register_gamification_routes
register_gamification_routes(app, register_badges=False)

# Register Blueprints
app.register_blueprint(main)

# Flask-Login setup
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'index'

class User(UserMixin):
    def __init__(self, id, email, role):
        self.id = id
        self.email = email
        self.role = role

@login_manager.user_loader
def load_user(user_id):
    if user_id == "1":
        return User(id="1", email="test@example.com", role="student")
    return None

@app.before_request
def before_request():
    g.current_user = current_user if current_user.is_authenticated else {'name': 'Guest', 'points': 0, 'role': 'guest'}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/initialize_db')
def initialize_db():
    with app.app_context():
        db.create_all()
    return "Database initialized successfully!"

@app.route('/check_tables')
def check_tables():
    with app.app_context():
        result = db.session.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in result]
        return jsonify(tables)

@app.route('/ask', methods=['POST'])
def ask():
    data = request.get_json()
    if not data or "question" not in data:
        return jsonify({"error": "No question provided"}), 400

    question = data["question"]
    response = call_groq_api(question)
    return jsonify({"answer": response})

@app.route('/process-image', methods=['POST'])
def process_image():
    if 'image' not in request.files:
        return jsonify({"error": "No image uploaded"}), 400

    file = request.files['image']
    if not file.filename.lower().endswith(('.jpg', '.jpeg', '.png')):
        return jsonify({"error": "Invalid file type"}), 400

    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as temp:
        temp_name = temp.name
        file.save(temp_name)

    try:
        image = cv2.imread(temp_name, cv2.IMREAD_GRAYSCALE)
        processed = cv2.GaussianBlur(image, (5, 5), 0)
        _, processed = cv2.threshold(processed, 128, 255, cv2.THRESH_BINARY)
        processed_path = temp_name.replace('.jpg', '_processed.jpg')
        cv2.imwrite(processed_path, processed)
        text = pytesseract.image_to_string(Image.open(processed_path), lang='eng')
        text = text.replace("sinx", "sin(x)").replace("xe^x", "x e^x")
        if not text.strip():
            return jsonify({"error": "No clear text found"}), 400
        prompt = f"The following text was extracted from an image: '{text}'. Help me understand this."
        response = call_groq_api(prompt)
        return jsonify({"extracted_text": text, "answer": response})
    finally:
        if os.path.exists(temp_name): os.remove(temp_name)
        if os.path.exists(processed_path): os.remove(processed_path)

@app.route('/transcribe-audio', methods=['POST'])
def transcribe_audio():
    if 'audio' not in request.files:
        return jsonify({"error": "No audio file uploaded"}), 400

    file = request.files['audio']
    if not file.filename.lower().endswith('.wav'):
        return jsonify({"error": "Invalid file type"}), 400

    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp:
        temp_name = temp.name
        file.save(temp_name)

    try:
        with sr.AudioFile(temp_name) as source:
            audio_data = recognizer.record(source)
            transcribed_text = recognizer.recognize_google(audio_data)
            response = call_groq_api(transcribed_text)
            return jsonify({"transcription": transcribed_text, "answer": response})
    except Exception as e:
        logger.error("Transcription error: %s", str(e), exc_info=True)
        return jsonify({"error": str(e)}), 500
    finally:
        if os.path.exists(temp_name): os.remove(temp_name)

@app.route('/routes')
def list_routes():
    routes = []
    for rule in app.url_map.iter_rules():
        routes.append({
            "endpoint": rule.endpoint,
            "methods": list(rule.methods),
            "url": str(rule)
        })
    return jsonify(routes)

@app.route('/dashboard')
def dashboard():
    topics = [
        {"title": "Algebra Basics"},
        {"title": "Geometry Intro"},
        {"title": "Calculus Fundamentals"},
    ]
    return render_template('dashboard.html', topics=topics)

@app.route('/courses')
def courses():
    courses = [
        {"id": 1, "name": "Math Basics", "description": "Learn the basics of mathematics.", "subject": "Math"},
        {"id": 2, "name": "Physics Fundamentals", "description": "Understand the fundamentals of physics.", "subject": "Physics"}
    ]
    return render_template('courses.html', courses=courses)

@app.route('/course/<int:course_id>')
def course_detail(course_id):
    course = {"id": course_id, "name": f"Course {course_id}", "description": "This is a sample course.", "subject": "Math", "education_level": "high_school", "difficulty": "beginner"}
    topics = [
        {"id": 1, "name": "Algebra", "description": "Learn about algebraic equations."},
        {"id": 2, "name": "Geometry", "description": "Understand the basics of geometry."}
    ]
    is_enrolled = True
    return render_template('course_detail.html', course=course, topics=topics, is_enrolled=is_enrolled)

@app.route('/topic/<int:topic_id>')
def topic_detail(topic_id):
    topic = {"id": topic_id, "name": f"Topic {topic_id}", "description": f"This is a sample description for topic {topic_id}."}
    return render_template("topic_detail.html", topic=topic)

@app.route('/login')
def login():
    user = User(id="1", email="test@example.com", role="student")
    login_user(user)
    return "Logged in as test@example.com"

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return "Logged out"

@app.route("/dashboard-data", methods=["GET"])
@login_required
def dashboard_data():
    if not current_user.is_authenticated:
        return jsonify({"error": "Unauthorized"}), 401

    user_id = current_user.id
    achievements = UserAchievement.query.filter_by(user_id=user_id).all()
    challenges = UserChallenge.query.filter_by(user_id=user_id).all()

    return jsonify({
        "email": current_user.email,
        "points": current_user.points,
        "streak": current_user.current_streak,
        "achievements": [{"name": a.name, "description": a.description} for a in achievements],
        "challenges": [{"name": c.name, "points": c.points} for c in challenges]
    })

def call_groq_api(prompt):
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return "Missing GROQ_API_KEY in .env"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    system_msg = (
        "You are an educational AI tutor. "
        "For math and factual queries, give only the final answer, e.g., 'Answer: 4'. "
        "Avoid detailed breakdown unless the question requires explanation."
    )

    data = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2,
        "max_tokens": 200,
        "top_p": 0.8
    }

    try:
        res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, data=json.dumps(data), timeout=30)
        if res.status_code != 200:
            return "AI service unavailable. Try again."
        return res.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Error calling AI: {e}"

if __name__ == '__main__':
    app.run(debug=True)
    # app.run(host='0.0.0.0', port=5002)