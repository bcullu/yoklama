import qrcode
import uuid
import os
# User model is now from DB, users_db and next_user_id are removed
from .models import User 
from app import db # Import db instance
from flask import current_app, url_for

# Business logic (e.g., QR generation, auth) will be defined here

def get_or_create_user(email, name, google_id):
    """
    Retrieves a user by Google ID or creates a new one if not found.
    Now uses the database.
    """
    user = User.query.filter_by(google_id=google_id).first()
    if user:
        # Optionally, update name or email if they have changed in Google profile
        if user.name != name or user.email != email:
            user.name = name
            user.email = email # Be cautious if email is primary identifier elsewhere
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                current_app.logger.error(f"Error updating user {google_id}: {e}")
        return user
    
    # Create new user if not found
    # Check if email is already in use by another google_id (optional, depends on policy)
    existing_user_by_email = User.query.filter_by(email=email).first()
    if existing_user_by_email:
        # This case needs careful handling.
        # Maybe link google_id to existing email, or reject, or prompt user.
        # For now, let's assume one google_id per email and vice-versa for simplicity in this step.
        # If a user tries to log in with a new Google account that has an email already in the system
        # associated with a different Google account, this will raise an integrity error if email is unique.
        # Or, if we allow it, it might create a new User row if google_id is the primary check.
        # Let's prioritize google_id as the unique identifier for login.
        # If email uniqueness is strict and different google_id has same email, it's an issue.
        # For now, we assume google_id is the source of truth for a user record.
        # If an email exists with a *different* google_id, this means trouble.
        # current_app.logger.warning(f"Email {email} already exists with a different Google ID.")
        # For now, we proceed to create new user based on new google_id.
        # If email must be unique, the User.query.filter_by(email=email).first() check is more critical.
        pass


    user = User(google_id=google_id, name=name, email=email)
    db.session.add(user)
    try:
        db.session.commit()
        current_app.logger.info(f"New user created: {user}")
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating user {google_id} / {email}: {e}")
        # Could re-raise or return None to indicate failure
        return None 
    return user

def get_google_auth_flow(redirect_uri):
    """
    Prepares the Google OAuth flow.
    Returns the authorization URL and state.
    (Placeholder implementation)
    """
    # In a real implementation, this would use:
    # from google_auth_oauthlib.flow import Flow
    # client_config = {
    #     "web": {
    #         "client_id": current_app.config['GOOGLE_CLIENT_ID'],
    #         "client_secret": current_app.config['GOOGLE_CLIENT_SECRET'],
    #         "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    #         "token_uri": "https://oauth2.googleapis.com/token",
    #         "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    #         "redirect_uris": [redirect_uri]
    #     }
    # }
    # flow = Flow.from_client_config(
    #     client_config,
    #     scopes=['openid', 'https://www.googleapis.com/auth/userinfo.email', 'https://www.googleapis.com/auth/userinfo.profile'],
    #     redirect_uri=redirect_uri
    # )
    # authorization_url, state = flow.authorization_url(access_type='offline', prompt='consent')
    # current_app.logger.debug(f"Generated authorization_url: {authorization_url}, state: {state}")
    # return authorization_url, state
    
    # Placeholder:
    current_app.logger.info(f"Mock Google Auth Flow: redirect_uri={redirect_uri}")
    # Simulate state being stored in session by the actual library
    # For testing, we can use a fixed state or skip state validation in the callback if not using a real flow.
    # from flask import session
    # session['oauth_state'] = 'mock_state_12345' # Example state
    return f"https://accounts.google.com/o/oauth2/auth?response_type=code&client_id=MOCK_CLIENT_ID&redirect_uri={redirect_uri}&scope=openid%20email%20profile&state=mock_state_12345", "mock_state_12345"

def process_google_callback(authorization_response_url, redirect_uri):
    """
    Processes the Google OAuth callback.
    Fetches user information.
    (Placeholder implementation)
    """
    # In a real implementation, this would involve:
    # 1. Validating state (from session vs. returned by Google)
    # 2. Using the `flow` object (possibly reconstructed or stored) to fetch the token:
    #    flow.fetch_token(authorization_response=authorization_response_url)
    # 3. Getting credentials from the flow:
    #    credentials = flow.credentials
    # 4. Verifying the ID token and getting user info:
    #    from google.oauth2 import id_token
    #    from google.auth.transport import requests as google_requests
    #    id_info = id_token.verify_oauth2_token(credentials.id_token, google_requests.Request(), current_app.config['GOOGLE_CLIENT_ID'])
    #    return {'name': id_info.get('name'), 'email': id_info.get('email'), 'google_id': id_info.get('sub')}
    
    # Placeholder:
    current_app.logger.info(f"Mock Google Callback Processing: authorization_response_url={authorization_response_url}, redirect_uri={redirect_uri}")
    # Simulate extracting info from the authorization_response_url or a fixed response
    return {'name': 'Mock Test User', 'email': 'mock.test.user@example.com', 'google_id': 'mock_google_id_123'}


def generate_session_qr(base_url="http://127.0.0.1:5000"):
    """
    Generates a unique session ID, creates a QR code for the student login URL,
    saves the QR code image, and returns the path to the image and the session ID.
    """
    session_id = uuid.uuid4()
    login_url = f"{base_url}/student/login?session_id={str(session_id)}"

    # Create QR code
    img = qrcode.make(login_url)

    # Ensure the directory for QR codes exists
    qr_code_dir = os.path.join("app", "static", "qr_codes")
    os.makedirs(qr_code_dir, exist_ok=True)

    # Save the QR code image
    image_filename = f"session_{str(session_id)}.png"
    image_path = os.path.join(qr_code_dir, image_filename)
    img.save(image_path)

    # Return the URL path to the image and the session ID
    qr_code_url_path = f"/static/qr_codes/{image_filename}"
    return qr_code_url_path, str(session_id)
