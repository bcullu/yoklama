from flask import jsonify, render_template, Blueprint, request, redirect, url_for, session, current_app, flash, abort
from flask_login import login_user, logout_user, login_required, current_user
from .services import generate_session_qr, get_or_create_user, get_google_auth_flow, process_google_callback 
# Removed User from models import here as it's used via db.User now. Models are imported in __init__
from .models import ClassSession, Question, StudentResponse, User # Import necessary DB models
from app import db # Import the SQLAlchemy db instance
from werkzeug.exceptions import BadRequest
from datetime import datetime
import uuid # For generating session_code

main_bp = Blueprint('main', __name__)

# All global in-memory dictionaries like active_sessions, session_students, 
# student_responses, active_question_for_session, quiz_questions are REMOVED.
# Data will be fetched from the database.

@main_bp.route('/')
def index():
    return render_template('index.html')

# --- Teacher Routes ---
# URL will change to use integer IDs for ClassSession once created
@main_bp.route('/teacher/start_session', methods=['GET'])
@login_required # Teacher needs to be logged in
def teacher_start_session(): 
    """
    Starts a new session, generates a QR code for students to join,
    and displays it to the teacher.
    """
    session_code_uuid = str(uuid.uuid4())
    base_url = request.host_url.rstrip('/')
    # The QR code URL should point to the student login page with the session_code
    qr_code_path, _ = generate_session_qr(f"{base_url}{url_for('main.student_login')}?session_code={session_code_uuid}")

    new_class_session = ClassSession(
        session_code=session_code_uuid,
        qr_code_url=qr_code_path, # Store the path to the QR image
        presenter_id=current_user.id,
        is_active=True,
        # active_question_id and active_question_status are nullable, default to None/Null
    )
    db.session.add(new_class_session)
    try:
        db.session.commit()
        current_app.logger.info(f"New ClassSession created with ID: {new_class_session.id} and code: {new_class_session.session_code} by presenter {current_user.email}")
        # Redirect to the session management page using the new database ID
        return redirect(url_for('main.manage_session', class_session_id=new_class_session.id))
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating new ClassSession: {e}")
        flash("Could not start a new session. Please try again.", "error")
        return redirect(url_for('main.index')) # Or a teacher dashboard

# --- Student Routes ---
@main_bp.route('/student/login', methods=['GET'])
def student_login():
    session_code_param = request.args.get('session_code') # Changed from session_id to session_code
    if not session_code_param:
        flash("Session code is required.", "error")
        return render_template('student_login.html', error="Session code is required.")

    # Find active session by code
    target_session = ClassSession.query.filter_by(session_code=session_code_param, is_active=True).first()
    
    if not target_session:
        current_app.logger.warning(f"Attempt to join non-existent or inactive session with code: {session_code_param}")
        flash("Invalid or expired session code.", "error")
        return render_template('student_login.html', error="Invalid or expired session code.")
        
    # Store database ClassSession.id in Flask session for the student
    session['current_class_session_id'] = target_session.id 
    session['current_session_code'] = target_session.session_code # Keep for display if needed
    current_app.logger.info(f"Student attempting to join session with code: {session_code_param} (DB ID: {target_session.id}). Stored in session.")
    return render_template('student_login.html', session_code=session_code_param) # Pass code for display

@main_bp.route('/student/google_login')
def student_google_login():
    # Use current_class_session_id from Flask session
    if 'current_class_session_id' not in session:
        flash("Session information missing. Please try joining the session again via QR code or link.", "error")
        return redirect(url_for('main.index')) 

    # Check if the session from Flask session is still active in DB
    class_session_db_id = session['current_class_session_id']
    target_session = ClassSession.query.get(class_session_db_id)
    if not target_session or not target_session.is_active:
        flash("The session you were trying to join is no longer active.", "error")
        # Clear potentially stale session vars
        session.pop('current_class_session_id', None)
        session.pop('current_session_code', None)
        return redirect(url_for('main.student_login')) # General login, no params

    redirect_uri = url_for('main.student_google_callback', _external=True)
    current_app.logger.debug(f"Redirect URI for Google Auth: {redirect_uri}")
    auth_url, state = get_google_auth_flow(redirect_uri) # This service is still a placeholder
    session['oauth_state'] = state 
    current_app.logger.info(f"Redirecting to Google for auth. DB ClassSession ID: {class_session_db_id}, State: {state}")
    return redirect(auth_url)

@main_bp.route('/student/callback/google')
def student_google_callback():
    if 'current_class_session_id' not in session:
        flash("Your session may have expired. Please try logging in again.", "error")
        return redirect(url_for('main.index')) # Or student_login without session_code
    
    class_session_db_id = session['current_class_session_id']
    # Basic state validation could be added here if get_google_auth_flow was not a mock
    # ...

    redirect_uri = url_for('main.student_google_callback', _external=True)
    try:
        # process_google_callback is still a placeholder returning mock data
        user_info = process_google_callback(request.url, redirect_uri) 
    except Exception as e:
        current_app.logger.error(f"Error in process_google_callback: {e}")
        flash("Failed to process Google authentication. Please try again.", "error")
        return redirect(url_for('main.student_login', session_code=session.get('current_session_code')))

    if not user_info or not user_info.get('email') or not user_info.get('google_id'):
        flash("Could not retrieve complete user information from Google (missing email or Google ID). Please try again.", "error")
        return redirect(url_for('main.student_login', session_code=session.get('current_session_code')))

    # Use the new get_or_create_user with google_id
    user = get_or_create_user(
        email=user_info['email'], 
        name=user_info.get('name', 'Student'), 
        google_id=user_info['google_id']
    )

    if not user:
        flash("Could not create or retrieve your user profile. Please contact support.", "error")
        return redirect(url_for('main.student_login', session_code=session.get('current_session_code')))
        
    login_user(user, remember=True) # Remember the user across browser sessions
    current_app.logger.info(f"User {user.email} (DB ID: {user.id}) logged in for ClassSession DB ID {class_session_db_id}.")

    # Add student to the ClassSession's student list if not already there
    target_session = ClassSession.query.get(class_session_db_id)
    if target_session and target_session.is_active:
        # Check if user is already associated with this session
        is_already_joined = db.session.query(session_student_association).filter_by(
            user_id=user.id, 
            class_session_id=target_session.id
        ).first() is not None

        if not is_already_joined:
            target_session.students_in_session.append(user)
            try:
                db.session.commit()
                current_app.logger.info(f"User {user.email} added to session {target_session.session_code}.")
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Error adding user {user.email} to session {target_session.session_code}: {e}")
                flash("Error joining the session. Please try again.", "error")
                return redirect(url_for('main.student_login', session_code=session.get('current_session_code')))
        else:
            current_app.logger.info(f"User {user.email} already in session {target_session.session_code}.")
    elif not target_session:
        flash("The session you were trying to join could not be found.", "error")
        return redirect(url_for('main.student_login'))
    elif not target_session.is_active:
        flash("The session you are trying to join is no longer active.", "error")
        return redirect(url_for('main.student_login', session_code=session.get('current_session_code')))


    return redirect(url_for('main.student_dashboard'))

@main_bp.route('/student/dashboard')
@login_required
def student_dashboard():
    # current_class_session_id should be in session
    if 'current_class_session_id' not in session:
        flash("No active session found for you. Please join a session using a QR code or link.", "warning")
        return redirect(url_for('main.index')) 
    
    class_session_db_id = session['current_class_session_id']
    target_session = ClassSession.query.get(class_session_db_id)

    if not target_session or not target_session.is_active:
        flash("Your current session is no longer active or valid. Please join a new one.", "warning")
        session.pop('current_class_session_id', None)
        session.pop('current_session_code', None)
        return redirect(url_for('main.index'))
    
    # current_user is available via Flask-Login
    return render_template('student_dashboard.html', 
                           name=current_user.name, 
                           current_session_code=target_session.session_code) # Pass session_code for display

@main_bp.route('/student/logout')
@login_required
def student_logout():
    # Optionally, remove student from session_students if needed, but logout handles auth state
    current_app.logger.info(f"User {current_user.email} logging out from session {session.get('session_id')}")
    logout_user()
    flash("You have been logged out.", "info")
    # session.pop('session_id', None) # Clear specific session key
    # session.pop('oauth_state', None) # Clear oauth state
    return redirect(url_for('main.index')) # Redirect to a general landing or login page


@main_bp.route('/student/submit_answer', methods=['POST'])
@login_required
def student_submit_answer():
    class_session_db_id = session.get('current_class_session_id')
    if not class_session_db_id:
        return jsonify({'status': 'error', 'message': 'Session context not found. Please rejoin session.'}), 400

    target_session = ClassSession.query.get(class_session_db_id)
    if not target_session or not target_session.is_active:
        return jsonify({'status': 'error', 'message': 'Classroom session is no longer active.'}), 403

    if not request.is_json:
        return jsonify({'status': 'error', 'message': 'Invalid request: Content-Type must be application/json.'}), 415

    try:
        data = request.get_json()
    except BadRequest:
        return jsonify({'status': 'error', 'message': 'Invalid JSON payload.'}), 400

    # Student submits question_ref_id (e.g. 'q1') or question_db_id.
    # The JS gets question_ref_id as 'id' and question_db_id as 'db_id'. Let's assume JS sends 'db_id'.
    question_db_id_from_student = data.get('question_db_id') 
    chosen_answer = data.get('chosen_answer')

    if not all([question_db_id_from_student, chosen_answer]):
        missing_fields = [f for f,v in [('question_db_id',question_db_id_from_student), ('chosen_answer',chosen_answer)] if not v]
        return jsonify({'status': 'error', 'message': f'Missing data: {", ".join(missing_fields)} required.'}), 400
    
    # Validate against current active question in the session
    if target_session.active_question_db_id != question_db_id_from_student or \
       target_session.active_question_status != 'open':
        current_app.logger.warning(
            f"Rejected answer from user {current_user.id} for ClassSession {target_session.id}. "
            f"Student submitted for Q_DB_ID:{question_db_id_from_student}, session active Q_DB_ID:{target_session.active_question_db_id} (status:{target_session.active_question_status})"
        )
        return jsonify({'status': 'error', 'message': 'Question is not currently open for answers or ID mismatch.'}), 403

    # Create and save the StudentResponse
    try:
        existing_response = StudentResponse.query.filter_by(
            student_id=current_user.id,
            class_session_id=target_session.id,
            question_id=question_db_id_from_student
        ).first()

        if existing_response:
            # Depending on policy, either update or reject. For now, reject re-submission.
            return jsonify({'status': 'error', 'message': 'You have already answered this question.'}), 409 # 409 Conflict
            # If updating:
            # existing_response.chosen_answer = chosen_answer
            # existing_response.submitted_at = datetime.utcnow()
            # message = f'Answer updated to "{chosen_answer}".'
        else:
            new_response = StudentResponse(
                student_id=current_user.id,
                class_session_id=target_session.id,
                question_id=question_db_id_from_student, # This must be Question.id (PK)
                chosen_answer=chosen_answer
            )
            db.session.add(new_response)
            message = f'Answer "{chosen_answer}" received.'
        
        db.session.commit()
        question_ref_id_display = Question.query.get(question_db_id_from_student).question_ref_id
        current_app.logger.info(
            f"Answer by user {current_user.id} for Q_REF_ID '{question_ref_id_display}' (DB_ID: {question_db_id_from_student}) "
            f"in ClassSession {target_session.id}: {chosen_answer}"
        )
        return jsonify({'status': 'success', 'message': message}), 200

    except Exception as e: # Catches IntegrityError from UniqueConstraint or other DB errors
        db.session.rollback()
        current_app.logger.error(f"Error submitting answer for user {current_user.id}, Q_DB_ID {question_db_id_from_student}, session {target_session.id}: {e}")
        # Check if it's a unique constraint violation
        if "UNIQUE constraint failed" in str(e) or "Duplicate entry" in str(e): # Adapt based on DB engine
             return jsonify({'status': 'error', 'message': 'You have already answered this question for this session.'}), 409
        return jsonify({'status': 'error', 'message': 'Could not save your answer due to a server error.'}), 500


# --- Teacher Question Management Routes ---
@main_bp.route('/teacher/set_active_question', methods=['POST'])
@login_required 
def set_active_question():
    class_session_db_id = request.form.get('class_session_id', type=int)
    # This should be question_db_id from the form, referring to Question.id
    question_db_id_to_activate = request.form.get('question_db_id', type=int) 

    target_session = ClassSession.query.get(class_session_db_id)
    if not target_session:
        flash("Session not found.", "error")
        return redirect(url_for('main.index')) 

    if target_session.presenter_id != current_user.id: # Authorization check
        flash("You are not authorized to modify this session.", "error")
        # Consider redirecting to 'main.manage_session' if it's just an access issue to *this* session
        return redirect(url_for('main.index'))


    question_to_activate = Question.query.get(question_db_id_to_activate)
    if not question_to_activate:
        flash("Invalid question ID selected.", "error")
        return redirect(url_for('main.manage_session', class_session_id=class_session_db_id))

    # If a different question is currently 'open', prevent activating a new one based on current UI recommendation
    if target_session.active_question_db_id and \
       target_session.active_question_status == 'open' and \
       target_session.active_question_db_id != question_to_activate.id:
        active_q = Question.query.get(target_session.active_question_db_id)
        flash(f"Question '{active_q.question_ref_id if active_q else 'Unknown'}' is currently open. Please close it before activating a new one.", "warning")
        return redirect(url_for('main.manage_session', class_session_id=class_session_db_id))

    target_session.active_question_db_id = question_to_activate.id
    target_session.active_question_status = 'open'
    try:
        db.session.commit()
        flash(f"Question '{question_to_activate.question_ref_id}' is now active for session {target_session.session_code}.", "success")
        current_app.logger.info(f"Teacher {current_user.email} set active question for ClassSession ID {target_session.id} to Question DB ID {question_to_activate.id} with status 'open'")
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error setting active question for session {target_session.id}: {e}")
        flash("Error setting active question. Please try again.", "error")
    
    return redirect(url_for('main.manage_session', class_session_id=class_session_db_id))


@main_bp.route('/teacher/session/<int:class_session_id>') 
@login_required 
def manage_session(class_session_id):
    target_session = ClassSession.query.get_or_404(class_session_id)

    if target_session.presenter_id != current_user.id: 
        flash("You are not authorized to manage this session.", "error")
        return redirect(url_for('main.index')) 

    qr_code_url = target_session.qr_code_url 
    
    current_active_question_from_db = None
    if target_session.active_question_db_id:
        current_active_question_from_db = Question.query.get(target_session.active_question_db_id)
    
    # Use question_ref_id for display consistency if it exists, else fallback to db id
    display_active_question_id = current_active_question_from_db.question_ref_id if current_active_question_from_db else None
    
    current_question_status = target_session.active_question_status if target_session.active_question_status else 'none'
    
    num_joined_students = target_session.students_in_session.count()

    num_responses_for_current_question = 0
    if current_active_question_from_db: # Ensure we have a question object
        num_responses_for_current_question = StudentResponse.query.filter_by(
            class_session_id=target_session.id,
            question_id=current_active_question_from_db.id 
        ).count()
    
    all_questions_from_db = Question.query.order_by(Question.id).all() # Consistent ordering
                
    return render_template('teacher_session_management.html',
                           class_session=target_session, 
                           qr_code_url=qr_code_url,
                           quiz_questions_db=all_questions_from_db, 
                           current_active_question_ref_id_display=display_active_question_id, # For display
                           current_active_question_db_id=target_session.active_question_db_id, # For forms
                           current_question_status=current_question_status,
                           num_joined_students=num_joined_students,
                           num_responses_for_current_question=num_responses_for_current_question)


@main_bp.route('/teacher/close_question', methods=['POST'])
@login_required
def teacher_close_question():
    class_session_db_id = request.form.get('class_session_id', type=int)
    question_db_id_to_close = request.form.get('question_db_id', type=int) 

    target_session = ClassSession.query.get(class_session_db_id)
    if not target_session:
        flash("Session not found.", "error")
        return redirect(url_for('main.index'))
    
    if target_session.presenter_id != current_user.id: 
        flash("You are not authorized to modify this session.", "error")
        return redirect(url_for('main.manage_session', class_session_id=class_session_db_id))

    # Ensure the question being closed is actually the one active in the session
    if not target_session.active_question_db_id or \
       target_session.active_question_db_id != question_db_id_to_close:
        # Fetch ref_id for better message if possible
        active_q_obj = Question.query.get(target_session.active_question_db_id) if target_session.active_question_db_id else None
        to_close_q_obj = Question.query.get(question_db_id_to_close)
        flash(f"Mismatch: Question to close ('{to_close_q_obj.question_ref_id if to_close_q_obj else question_db_id_to_close}') "
              f"is not the one currently active ('{active_q_obj.question_ref_id if active_q_obj else 'None'}').", "error")
        return redirect(url_for('main.manage_session', class_session_id=class_session_db_id))
    
    if target_session.active_question_status != 'open':
        q_to_close_obj = Question.query.get(question_db_id_to_close)
        flash(f"Question '{q_to_close_obj.question_ref_id if q_to_close_obj else question_db_id_to_close}' is already not 'open' (current status: {target_session.active_question_status}).", "warning")
        return redirect(url_for('main.manage_session', class_session_id=class_session_db_id))

    target_session.active_question_status = 'closed'
    try:
        db.session.commit()
        closed_question = Question.query.get(question_db_id_to_close) # Fetch again for ref_id
        flash(f"Question '{closed_question.question_ref_id if closed_question else question_db_id_to_close}' has been closed for answers.", "info")
        current_app.logger.info(f"Teacher {current_user.email} closed question (DB ID: {question_db_id_to_close}) for ClassSession ID {class_session_db_id}")
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error closing question {question_db_id_to_close} for session {class_session_db_id}: {e}")
        flash("Error closing question. Please try again.", "error")
        
    return redirect(url_for('main.manage_session', class_session_id=class_session_db_id))

# --- Student Question Fetching ---
@main_bp.route('/student/get_current_question')
@login_required
def get_current_question():
    class_session_db_id = session.get('current_class_session_id')
    if not class_session_db_id:
        return jsonify({'status': 'error', 'message': 'Session context not found. Please rejoin session.'}), 400

    target_session = ClassSession.query.get(class_session_db_id)
    if not target_session or not target_session.is_active:
        session.pop('current_class_session_id', None)
        session.pop('current_session_code', None)
        return jsonify({'status': 'error', 'message': 'Classroom session is no longer active. Please rejoin.'}), 403

    if target_session.active_question_db_id and target_session.active_question_status:
        question_from_db = Question.query.get(target_session.active_question_db_id)
        if question_from_db:
            question_info_for_student = {
                'id': question_from_db.question_ref_id, # Use ref_id for student-facing identification
                'db_id': question_from_db.id, # Keep db_id if needed for submission logic directly
                'text': question_from_db.text,
                'options': question_from_db.get_options_dict(), # Use method to get options
                'status': target_session.active_question_status 
            }
            return jsonify({'status': 'new_question', 'question': question_info_for_student})
        else:
            current_app.logger.error(f"Data inconsistency: Active question DB ID {target_session.active_question_db_id} for ClassSession {target_session.id} not found in Question table.")
            return jsonify({'status': 'error', 'message': 'Active question data is inconsistent. Please notify teacher.'}), 500
    else:
        return jsonify({'status': 'no_active_question', 'message': 'No question is currently active.'})


# --- Teacher Results Route ---
@main_bp.route('/teacher/session/<int:class_session_id>/results') 
@login_required
def teacher_session_results(class_session_id):
    target_session = ClassSession.query.get_or_404(class_session_id)

    if target_session.presenter_id != current_user.id:
        flash("You are not authorized to view results for this session.", "error")
        return redirect(url_for('main.index'))

    # Fetch all students who were part of this session
    # students_in_this_session = target_session.students_in_session.all() # This is a list of User objects
    
    # Fetch all responses for this session
    all_responses_for_session = StudentResponse.query.filter_by(class_session_id=target_session.id).all()
    
    # Fetch all questions (to get correct answers and text)
    all_questions = Question.query.order_by(Question.id).all()

    scores = {}
    # Initialize scores for all students who joined the session
    for student_user in target_session.students_in_session: # Iterate over User objects
        scores[student_user.id] = {
            'name': student_user.name,
            'email': student_user.email,
            'score': 0,
            'answers': {} # q_id -> {'chosen': 'A', 'correct': 'C', 'is_correct': False, 'question_text': ...}
        }

    # Process responses
    for response in all_responses_for_session:
        student_id = response.student_id
        question_id = response.question_id # This is Question.id (PK)
        
        # Find the question details (correct answer, text)
        question_details = next((q for q in all_questions if q.id == question_id), None)
        if not question_details:
            current_app.logger.warning(f"Response found for Q_DB_ID {question_id} but question not in all_questions list. Skipping.")
            continue

        correct_answer = question_details.correct_answer
        is_correct = (response.chosen_answer == correct_answer)
        
        if student_id in scores: # Should always be true if student joined session properly
            if is_correct:
                scores[student_id]['score'] += 1
            
            scores[student_id]['answers'][question_id] = { # Use Question DB ID as key
                'chosen': response.chosen_answer,
                'correct': correct_answer,
                'is_correct': is_correct,
                'question_text': question_details.text,
                'question_ref_id': question_details.question_ref_id # For display
            }
        else:
             current_app.logger.warning(f"Response found from student ID {student_id} who is not in the session's student list (scores dict). Response ID: {response.id}")


    # Fill in answers for questions students didn't respond to
    for student_id in scores:
        for question in all_questions:
            if question.id not in scores[student_id]['answers']:
                 scores[student_id]['answers'][question.id] = {
                    'chosen': None, # Or 'N/A'
                    'correct': question.correct_answer,
                    'is_correct': False,
                    'question_text': question.text,
                    'question_ref_id': question.question_ref_id
                }


    sorted_scores_list = sorted(scores.values(), key=lambda x: x['score'], reverse=True)
    top_3_students = sorted_scores_list[:3]
    total_participants = target_session.students_in_session.count()


    return render_template('teacher_session_results.html',
                           class_session=target_session, # Pass the session object
                           sorted_scores=sorted_scores_list,
                           top_3_students=top_3_students,
                           total_participants=total_participants,
                           quiz_questions_map={q.id: q for q in all_questions}) # Pass a map for easy lookup by id

@main_bp.route('/teacher/end_session', methods=['POST'])
@login_required
def teacher_end_session():
    class_session_db_id = request.form.get('class_session_id', type=int)
    target_session = ClassSession.query.get(class_session_db_id)

    if not target_session:
        flash("Session not found or already ended.", "error")
        return redirect(url_for('main.index')) 

    if target_session.presenter_id != current_user.id:
        flash("You are not authorized to end this session.", "error")
        return redirect(url_for('main.manage_session', class_session_id=class_session_db_id))
        
    target_session.is_active = False
    if target_session.active_question_status == 'open': # If a question is open, close it.
        target_session.active_question_status = 'closed'
        current_app.logger.info(f"Question DB ID {target_session.active_question_db_id} for session {target_session.id} was auto-closed due to session end.")
    # No need to clear target_session.active_question_db_id if we want to know the last active question.
    
    try:
        db.session.commit()
        flash(f"Session {target_session.session_code} has been ended. Results are now final.", "info")
        current_app.logger.info(f"Teacher {current_user.email} ended ClassSession ID {target_session.id}.")
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error ending session {target_session.id}: {e}")
        flash("Error ending session. Please try again.", "error")
        return redirect(url_for('main.manage_session', class_session_id=class_session_db_id))
    
    return redirect(url_for('main.teacher_session_results', class_session_id=class_session_db_id))
