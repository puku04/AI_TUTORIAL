import os
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import json
from datetime import datetime, timedelta
from functools import wraps

# Import functions from your existing app.py
from app import call_groq_api, process_image, transcribe_audio

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tutor.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize SQLAlchemy
db = SQLAlchemy(app)

# Initialize LoginManager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Database Models
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'student' or 'educator'
    education_level = db.Column(db.String(50))  # 'high_school', 'college', etc.
    grade_or_year = db.Column(db.String(20))  # '9th', '10th', 'freshman', etc.
    major = db.Column(db.String(100))  # For college students
    points = db.Column(db.Integer, default=0)
    streak_days = db.Column(db.Integer, default=0)
    last_activity = db.Column(db.DateTime)
    
    courses = db.relationship('Enrollment', back_populates='user')
    achievements = db.relationship('UserAchievement', back_populates='user')

class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    education_level = db.Column(db.String(50))
    subject = db.Column(db.String(50))
    difficulty = db.Column(db.String(20))  # 'beginner', 'intermediate', 'advanced'
    
    topics = db.relationship('Topic', back_populates='course')
    enrollments = db.relationship('Enrollment', back_populates='course')

class Topic(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'))
    youtube_links = db.Column(db.Text)  # Store as JSON string
    
    course = db.relationship('Course', back_populates='topics')
    learning_sessions = db.relationship('LearningSession', back_populates='topic')

class Enrollment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'))
    enrollment_date = db.Column(db.DateTime, default=datetime.utcnow)
    completed = db.Column(db.Boolean, default=False)
    
    user = db.relationship('User', back_populates='courses')
    course = db.relationship('Course', back_populates='enrollments')

class LearningSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    topic_id = db.Column(db.Integer, db.ForeignKey('topic.id'))
    start_time = db.Column(db.DateTime, default=datetime.utcnow)
    end_time = db.Column(db.DateTime)
    duration = db.Column(db.Integer)  # in seconds
    
    topic = db.relationship('Topic', back_populates='learning_sessions')

class Achievement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    badge_image = db.Column(db.String(200))
    points = db.Column(db.Integer, default=0)
    requirement = db.Column(db.String(100))  # e.g., 'streak_5', 'complete_course_1'
    
    users = db.relationship('UserAchievement', back_populates='achievement')

class UserAchievement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    achievement_id = db.Column(db.Integer, db.ForeignKey('achievement.id'))
    date_earned = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', back_populates='achievements')
    achievement = db.relationship('Achievement', back_populates='users')

class Challenge(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    start_date = db.Column(db.DateTime, default=datetime.utcnow)
    end_date = db.Column(db.DateTime)
    points = db.Column(db.Integer, default=0)
    requirement = db.Column(db.String(100))  # e.g., 'study_time_180' (minutes)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Role-based access control decorator
def role_required(role):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or current_user.role != role:
                return redirect(url_for('unauthorized'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# Routes
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('landing.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            
            # Update streak if necessary
            if user.last_activity:
                last_date = user.last_activity.date()
                today = datetime.utcnow().date()
                
                if today - last_date == timedelta(days=1):
                    user.streak_days += 1
                elif today - last_date > timedelta(days=1):
                    user.streak_days = 1
            else:
                user.streak_days = 1
                
            user.last_activity = datetime.utcnow()
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                print(f"Error: {e}")
            
            return redirect(url_for('dashboard'))
        return render_template('login.html', error='Invalid username or password')
        
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        role = request.form.get('role')
        education_level = request.form.get('education_level')
        grade_or_year = request.form.get('grade_or_year')
        major = request.form.get('major', '')
        
        if User.query.filter_by(username=username).first():
            return render_template('register.html', error='Username already exists')
        if User.query.filter_by(email=email).first():
            return render_template('register.html', error='Email already exists')
        
        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            role=role,
            education_level=education_level,
            grade_or_year=grade_or_year,
            major=major,
            last_activity=datetime.utcnow()
        )
        db.session.add(user)
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Error: {e}")
        
        # Award registration achievement
        registration_achievement = Achievement.query.filter_by(name='First Steps').first()
        if registration_achievement:
            user_achievement = UserAchievement(
                user_id=user.id,
                achievement_id=registration_achievement.id
            )
            user.points += registration_achievement.points
            db.session.add(user_achievement)
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                print(f"Error: {e}")
        
        login_user(user)
        return redirect(url_for('dashboard'))
        
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    # Get recommended courses based on user's education level
    recommended_courses = Course.query.filter_by(education_level=current_user.education_level).limit(5).all()
    
    # Get user's enrolled courses
    enrolled_courses = [enrollment.course for enrollment in current_user.courses]
    
    # Get active challenges
    active_challenges = Challenge.query.filter(Challenge.end_date > datetime.utcnow()).all()
    
    # Get user's achievements
    user_achievements = [ua.achievement for ua in current_user.achievements]
    
    # Calculate study time today
    today = datetime.utcnow().date()
    today_sessions = LearningSession.query.filter(
        LearningSession.user_id == current_user.id,
        LearningSession.start_time >= today
    ).all()
    
    study_time_today = sum(session.duration for session in today_sessions if session.duration) or 0
    study_time_today_minutes = study_time_today // 60
    
    return render_template(
        'dashboard.html',
        recommended_courses=recommended_courses,
        enrolled_courses=enrolled_courses,
        active_challenges=active_challenges,
        user_achievements=user_achievements,
        study_time_today=study_time_today_minutes,
        goal_time=30  # 30-minute daily goal
    )

@app.route('/course/<int:course_id>')
@login_required
def course_detail(course_id):
    course = Course.query.get_or_404(course_id)
    topics = Topic.query.filter_by(course_id=course_id).all()
    
    # Check if user is enrolled
    enrollment = Enrollment.query.filter_by(user_id=current_user.id, course_id=course_id).first()
    
    return render_template(
        'course_detail.html',
        course=course,
        topics=topics,
        is_enrolled=enrollment is not None
    )

@app.route('/enroll/<int:course_id>')
@login_required
def enroll_course(course_id):
    # Check if already enrolled
    enrollment = Enrollment.query.filter_by(user_id=current_user.id, course_id=course_id).first()
    if enrollment:
        return redirect(url_for('course_detail', course_id=course_id))
    
    # Create new enrollment
    enrollment = Enrollment(user_id=current_user.id, course_id=course_id)
    db.session.add(enrollment)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Error: {e}")
    
    # Award points
    current_user.points += 10
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Error: {e}")
    
    return redirect(url_for('course_detail', course_id=course_id))

@app.route('/topic/<int:topic_id>')
@login_required
def topic_detail(topic_id):
    topic = Topic.query.get_or_404(topic_id)
    
    # Parse YouTube links from JSON string
    youtube_links = []
    if topic.youtube_links:
        try:
            youtube_links = json.loads(topic.youtube_links)
        except json.JSONDecodeError:
            youtube_links = []
    
    # Start a learning session
    session = LearningSession(user_id=current_user.id, topic_id=topic_id)
    db.session.add(session)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Error: {e}")
    
    session_id = session.id
    
    return render_template(
        'topic_detail.html',
        topic=topic,
        youtube_links=youtube_links,
        session_id=session_id
    )

@app.route('/end_session/<int:session_id>')
@login_required
def end_session(session_id):
    session = LearningSession.query.get_or_404(session_id)
    
    # Ensure the session belongs to the current user
    if session.user_id != current_user.id:
        return redirect(url_for('dashboard'))
    
    # Calculate duration
    session.end_time = datetime.utcnow()
    duration = (session.end_time - session.start_time).total_seconds()
    session.duration = int(duration)
    
    # Award points based on duration (1 point per minute, max 30 for a 30-minute session)
    points_earned = min(int(duration / 60), 30)
    current_user.points += points_earned
    
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Error: {e}")
    
    # Check for achievements
    check_achievements(current_user.id)
    
    return redirect(url_for('dashboard'))

@app.route('/ask', methods=['POST'])
@login_required
def ask_question():
    data = request.get_json()
    question = data.get('question', '')
    
    if not question:
        return jsonify({"error": "No question provided"}), 400
    
    # Get user's education level and subject context
    context = f"The student is at {current_user.education_level} level"
    if current_user.education_level == 'college':
        context += f" majoring in {current_user.major}"
    else:
        context += f" in grade {current_user.grade_or_year}"
    
    # Enhance the prompt with user context
    enhanced_prompt = f"{context}. Question: {question}"
    
    # Call the AI service
    response = call_groq_api(enhanced_prompt)
    
    return jsonify({"answer": response})

@app.route('/suggest_topics', methods=['POST'])
@login_required
def suggest_topics():
    data = request.get_json()
    subject = data.get('subject', '')
    
    if not subject:
        return jsonify({"error": "No subject provided"}), 400
    
    # Create context for AI
    context = f"""
    Based on a {current_user.education_level} student 
    in {current_user.grade_or_year} studying {subject},
    suggest 3 key math topics they should learn, 
    with a brief description and 1 YouTube video link for each.
    Format as JSON with fields: topic_name, description, youtube_link
    """
    
    # Call AI service
    response = call_groq_api(context)
    
    # Try to parse JSON from the response
    try:
        topics_json = json.loads(response)
    except json.JSONDecodeError:
        return jsonify({"error": "Invalid JSON response from AI"}), 500
    
    return jsonify(topics_json)

# Helper functions
def check_achievements(user_id):
    user = User.query.get(user_id)
    
    # Check streak achievements
    if user.streak_days == 3:
        award_achievement(user_id, '3-Day Streak')
    elif user.streak_days == 7:
        award_achievement(user_id, '7-Day Streak')
    elif user.streak_days == 30:
        award_achievement(user_id, '30-Day Streak')
    
    # Check study time achievements
    total_study_time = sum(session.duration for session in 
                        LearningSession.query.filter_by(user_id=user_id).all() 
                        if session.duration) / 60  # Convert to minutes
    
    if total_study_time >= 60:
        award_achievement(user_id, '1 Hour of Learning')
    elif total_study_time >= 300:
        award_achievement(user_id, '5 Hours of Learning')
    elif total_study_time >= 1000:
        award_achievement(user_id, 'Learning Master')

def award_achievement(user_id, achievement_name):
    user = User.query.get(user_id)
    achievement = Achievement.query.filter_by(name=achievement_name).first()
    
    if not achievement:
        return
    
    # Check if user already has this achievement
    existing = UserAchievement.query.filter_by(
        user_id=user_id, 
        achievement_id=achievement.id
    ).first()
    
    if not existing:
        user_achievement = UserAchievement(
            user_id=user_id,
            achievement_id=achievement.id
        )
        db.session.add(user_achievement)
        
        # Award points
        user.points += achievement.points
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Error: {e}")

# Initialize database with some sample data
def create_sample_data():
    # Create achievements
    achievements = [
        Achievement(name='First Steps', description='Register an account', points=10, badge_image='badge_first_steps.png'),
        Achievement(name='3-Day Streak', description='Login for 3 consecutive days', points=15, badge_image='badge_streak_3.png'),
        Achievement(name='7-Day Streak', description='Login for 7 consecutive days', points=30, badge_image='badge_streak_7.png'),
        Achievement(name='30-Day Streak', description='Login for 30 consecutive days', points=100, badge_image='badge_streak_30.png'),
        Achievement(name='1 Hour of Learning', description='Study for a total of 1 hour', points=20, badge_image='badge_1h.png'),
        Achievement(name='5 Hours of Learning', description='Study for a total of 5 hours', points=50, badge_image='badge_5h.png'),
        Achievement(name='Learning Master', description='Study for a total of 10+ hours', points=150, badge_image='badge_master.png'),
    ]
    
    # Create sample courses for high school
    high_school_courses = [
        Course(name='Algebra Fundamentals', description='Basic algebraic concepts and equations', education_level='high_school', subject='Math', difficulty='beginner'),
        Course(name='Geometry Basics', description='Introduction to geometric shapes and theorems', education_level='high_school', subject='Math', difficulty='beginner'),
        Course(name='Trigonometry', description='Study of triangles and trigonometric functions', education_level='high_school', subject='Math', difficulty='intermediate'),
        Course(name='Pre-Calculus', description='Preparation for calculus concepts', education_level='high_school', subject='Math', difficulty='advanced'),
    ]
    
    # Create sample courses for college
    college_courses = [
        Course(name='Calculus I', description='Limits, derivatives, and basic integration', education_level='college', subject='Math', difficulty='beginner'),
        Course(name='Linear Algebra', description='Vector spaces, matrices, and linear transformations', education_level='college', subject='Math', difficulty='intermediate'),
        Course(name='Differential Equations', description='Solving and applications of differential equations', education_level='college', subject='Math', difficulty='intermediate'),
        Course(name='Advanced Statistics', description='Statistical inference and data analysis', education_level='college', subject='Math', difficulty='advanced'),
    ]
    
    # Add to database
    for achievement in achievements:
        db.session.add(achievement)
    
    for course in high_school_courses + college_courses:
        db.session.add(course)
    
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Error: {e}")
    
    # Add topics to courses
    algebra_topics = [
        Topic(
            name='Solving Linear Equations', 
            description='Learn how to solve equations in the form ax + b = c', 
            course_id=1,
            youtube_links=json.dumps([
                "https://www.youtube.com/watch?v=wAHJiM3nZD4",
                "https://www.youtube.com/watch?v=3YzMh-b-CJU"
            ])
        ),
        Topic(
            name='Quadratic Equations', 
            description='Solving quadratic equations using factoring and the quadratic formula', 
            course_id=1,
            youtube_links=json.dumps([
                "https://www.youtube.com/watch?v=EBbtoFMJvFc",
                "https://www.youtube.com/watch?v=i7idZfS8t8w"
            ])
        ),
    ]
    
    geometry_topics = [
        Topic(
            name='Triangles and Their Properties', 
            description='Understanding different types of triangles and their properties', 
            course_id=2,
            youtube_links=json.dumps([
                "https://www.youtube.com/watch?v=JvBbRNRc-Wk",
                "https://www.youtube.com/watch?v=7Jw0YF_UvRo"
            ])
        ),
        Topic(
            name='Circle Theorems', 
            description='Understanding theorems related to circles', 
            course_id=2,
            youtube_links=json.dumps([
                "https://www.youtube.com/watch?v=Pv8H8-VH8r8",
                "https://www.youtube.com/watch?v=O30CNvgCJqs"
            ])
        ),
    ]
    
    # Add sample topics to database
    for topic in algebra_topics + geometry_topics:
        db.session.add(topic)
    
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"Error: {e}")

@app.route('/initialize_db')
def initialize_db():
    db.create_all()
    create_sample_data()
    return jsonify({"message": "Database initialized with sample data"})

@app.route('/unauthorized')
def unauthorized():
    return render_template('unauthorized.html')

@app.route('/educator/dashboard')
@login_required
@role_required('educator')
def educator_dashboard():
    # Get courses created by this educator
    return render_template('educator_dashboard.html')

if __name__ == '__main__':
    app.run(debug=True, port=5002)