from . import db # Import db from the current package's __init__.py
from flask_login import UserMixin
from datetime import datetime
from sqlalchemy import UniqueConstraint

# Association Table for Many-to-Many relationship between ClassSession and User (students)
session_student_association = db.Table('session_student_association',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('class_session_id', db.Integer, db.ForeignKey('class_session.id'), primary_key=True)
)

class User(UserMixin, db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    google_id = db.Column(db.String(200), unique=True, nullable=False) # Google's unique user ID
    email = db.Column(db.String(120), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    
    # Relationship to StudentResponse (one-to-many: one user can have many responses)
    responses = db.relationship('StudentResponse', backref='student', lazy=True)
    
    # Sessions this user has presented (if storing teachers as users)
    # presented_sessions = db.relationship('ClassSession', backref='presenter', lazy='dynamic', foreign_keys='ClassSession.presenter_id')
    
    # Sessions this user has joined as a student (many-to-many)
    # This relationship is defined in ClassSession model via session_student_association

    def __repr__(self):
        return f'<User {self.email} (ID: {self.id})>'

class ClassSession(db.Model):
    __tablename__ = 'class_session'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    session_code = db.Column(db.String(36), unique=True, nullable=False) # For UUID
    qr_code_url = db.Column(db.String(255), nullable=True)
    # Assuming teacher is also a User. If not, this might be a simple string or different FK.
    presenter_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False) 
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    active_question_db_id = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=True) # Stores Question.id
    active_question_status = db.Column(db.String(50), nullable=True) # 'open', 'closed'

    # Relationship to User (students in session) - Many-to-Many
    students_in_session = db.relationship('User', secondary=session_student_association,
                                          backref=db.backref('joined_sessions', lazy='dynamic'),
                                          lazy='dynamic') # 'dynamic' allows further querying

    # Relationship to StudentResponse (one-to-many: one session can have many responses)
    responses = db.relationship('StudentResponse', backref='class_session', lazy='dynamic')
    
    # Relationship to the User who is the presenter
    presenter = db.relationship('User', backref=db.backref('presented_sessions', lazy='dynamic'), foreign_keys=[presenter_id])


    def __repr__(self):
        return f'<ClassSession {self.session_code} (ID: {self.id}) Active: {self.is_active}>'

class Question(db.Model):
    __tablename__ = 'question'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    question_ref_id = db.Column(db.String(50), unique=True, nullable=False) # e.g., 'q1', 'q2'
    text = db.Column(db.Text, nullable=False)
    option_a = db.Column(db.String(255), nullable=True)
    option_b = db.Column(db.String(255), nullable=True)
    option_c = db.Column(db.String(255), nullable=True)
    option_d = db.Column(db.String(255), nullable=True)
    correct_answer = db.Column(db.String(1), nullable=False) # 'A', 'B', 'C', 'D'

    # Relationship to StudentResponse (one-to-many: one question can have many responses across sessions)
    # responses = db.relationship('StudentResponse', backref='question_responded', lazy='dynamic')
    
    # Active question for sessions (one-to-many: one question can be active in many sessions, though usually one at a time)
    # This is handled by ClassSession.active_question_db_id

    def __repr__(self):
        return f'<Question {self.question_ref_id} (ID: {self.id})>'

    def get_options_dict(self):
        options = {}
        if self.option_a: options['A'] = self.option_a
        if self.option_b: options['B'] = self.option_b
        if self.option_c: options['C'] = self.option_c
        if self.option_d: options['D'] = self.option_d
        return options

class StudentResponse(db.Model):
    __tablename__ = 'student_response'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    class_session_id = db.Column(db.Integer, db.ForeignKey('class_session.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=False) # This is Question.id (PK)
    chosen_answer = db.Column(db.String(1), nullable=False) # 'A', 'B', 'C', 'D'
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships (backrefs are defined in User, ClassSession, Question)
    # student = db.relationship('User', backref='student_responses') # defined in User
    # class_session = db.relationship('ClassSession', backref='session_responses') # defined in ClassSession
    question_responded_to = db.relationship('Question', backref=db.backref('student_answers', lazy='dynamic'))


    # Unique constraint: a student can only answer a specific question once in a session
    __table_args__ = (UniqueConstraint('student_id', 'class_session_id', 'question_id', name='_student_session_question_uc'),)

    def __repr__(self):
        return f'<StudentResponse UserID:{self.student_id} SessionID:{self.class_session_id} QID:{self.question_id} Ans:{self.chosen_answer}>'

# Data for seeding questions (can be moved to a dedicated seed script or config)
# This is here just for reference during refactoring, will be moved for seeding.
initial_quiz_questions_data = [
    {'question_ref_id': 'q1', 'text': 'What is the capital of France?', 'options': {'A': 'Berlin', 'B': 'Madrid', 'C': 'Paris', 'D': 'Rome'}, 'correct_answer': 'C'},
    {'question_ref_id': 'q2', 'text': 'What is 2 * 5?', 'options': {'A': '7', 'B': '10', 'C': '12', 'D': '8'}, 'correct_answer': 'B'},
    {'question_ref_id': 'q3', 'text': 'Which planet is known as the Red Planet?', 'options': {'A': 'Earth', 'B': 'Mars', 'C': 'Jupiter', 'D': 'Venus'}, 'correct_answer': 'B'},
    {'question_ref_id': 'q4', 'text': 'What is the largest ocean on Earth?', 'options': {'A': 'Atlantic', 'B': 'Indian', 'C': 'Arctic', 'D': 'Pacific'}, 'correct_answer': 'D'}
]

def seed_questions():
    from app import db # Local import to ensure app context
    if Question.query.first() is None: # Check if questions already exist
        for q_data in initial_quiz_questions_data:
            question = Question(
                question_ref_id=q_data['question_ref_id'],
                text=q_data['text'],
                option_a=q_data['options'].get('A'),
                option_b=q_data['options'].get('B'),
                option_c=q_data['options'].get('C'),
                option_d=q_data['options'].get('D'),
                correct_answer=q_data['correct_answer']
            )
            db.session.add(question)
        db.session.commit()
        print("Questions seeded successfully.")
    else:
        print("Questions already exist, skipping seed.")
