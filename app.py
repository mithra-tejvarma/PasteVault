import os
import secrets
import string
from datetime import timedelta
from flask import (
    Flask, render_template, request, redirect, url_for, flash,
    jsonify, session, send_from_directory
)
from werkzeug.utils import secure_filename
from models import db, Paste, utc_now

# Initialize Flask application
app = Flask(__name__)

# Basic configuration
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'pastevault-insecure-dev-secret-key-cse')
instance_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'instance')
os.makedirs(instance_path, exist_ok=True)

# Upload directory configuration & size limit (10 MB)
UPLOAD_FOLDER = os.path.join(instance_path, 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10 MB maximum upload size

app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(instance_path, 'pastevault.db')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Connect SQLAlchemy to Flask app
db.init_app(app)

# Expiration options lookup (key -> timedelta or None)
EXPIRY_MAP = {
    'never': None,
    '10m': timedelta(minutes=10),
    '1h': timedelta(hours=1),
    '1d': timedelta(days=1),
    '7d': timedelta(days=7),
}


def generate_short_id(length: int = 6) -> str:
    """
    Generates a secure random 6-character alphanumeric string.
    Checks the database to ensure no collision occurs before returning.
    """
    alphabet = string.ascii_letters + string.digits
    for _ in range(10):  # Retry up to 10 times in case of collision
        candidate = ''.join(secrets.choice(alphabet) for _ in range(length))
        if not Paste.query.filter_by(short_id=candidate).first():
            return candidate

    # Fallback with slightly longer length in astronomical collision event
    return ''.join(secrets.choice(alphabet) for _ in range(length + 2))


def is_authorized_creator(paste: Paste) -> bool:
    """
    Verifies if the current client is the authorized creator of the paste.
    Checks:
      1. Secret creator token stored in Flask's cryptographically signed session cookie.
      2. Optional explicit token passed via URL parameter or form value (?delete_token=...).
    Uses secrets.compare_digest to prevent timing attacks.
    """
    session_token = session.get(f'delete_token_{paste.short_id}')
    if session_token and secrets.compare_digest(session_token, paste.delete_token):
        return True

    param_token = request.values.get('delete_token') or request.headers.get('X-Delete-Token')
    if param_token and secrets.compare_digest(param_token, paste.delete_token):
        return True

    return False


def cleanup_paste_file(paste: Paste):
    """Safely deletes an attached file from disk when a paste is expired or deleted."""
    if paste.file_filename:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], paste.file_filename)
        if os.path.exists(file_path):
            import gc
            import time
            for attempt in range(3):
                try:
                    os.remove(file_path)
                    break
                except OSError as e:
                    gc.collect()
                    time.sleep(0.05)
                    if attempt == 2:
                        app.logger.warning(f"Could not remove file {file_path}: {e}")


@app.template_filter('time_remaining')
def time_remaining_filter(expires_at):
    """Jinja filter to display a friendly countdown until expiration."""
    if not expires_at:
        return "Never"
    now = utc_now()
    diff = expires_at - now
    if diff.total_seconds() <= 0:
        return "Expired"

    seconds = int(diff.total_seconds())
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60

    if days > 0:
        return f"{days}d {hours}h remaining"
    if hours > 0:
        return f"{hours}h {minutes}m remaining"
    if minutes > 0:
        return f"{minutes}m remaining"
    return f"{seconds}s remaining"


@app.route('/')
def index():
    """Home landing page explaining PasteVault and linking to creation."""
    return render_template('index.html')


@app.route('/create', methods=['GET', 'POST'])
def create_paste():
    """
    Handles both displaying the paste creation form (GET)
    and processing the submitted form with optional file/image upload (POST).
    """
    if request.method == 'GET':
        return render_template('create.html', errors={}, form_data={})

    # Retrieve and sanitize form inputs
    title = (request.form.get('title') or '').strip()
    content = request.form.get('content') or ''
    expiry_key = request.form.get('expiry', 'never')
    uploaded_file = request.files.get('file')

    # Server-side validation
    errors = {}

    if not title:
        errors['title'] = "Title is required."
    elif len(title) > 100:
        errors['title'] = "Title cannot exceed 100 characters."

    has_valid_file = bool(uploaded_file and uploaded_file.filename and uploaded_file.filename.strip())

    # Either text content or an attached file must be provided
    if not content.strip() and not has_valid_file:
        errors['content'] = "Please provide text content, an attached file/image, or both."
    elif len(content) > 50000:
        errors['content'] = "Content cannot exceed 50,000 characters."

    if expiry_key not in EXPIRY_MAP:
        errors['expiry'] = "Invalid expiration option selected."

    # Validate file upload if present
    original_name = None
    stored_filename = None
    file_size = None
    file_mimetype = None

    if has_valid_file:
        original_name = uploaded_file.filename.strip()
        safe_name = secure_filename(original_name)
        if not safe_name:
            errors['file'] = "Invalid file name. Please rename the file and try again."

    # If validation fails, return form with errors and preserve input
    if errors:
        return render_template(
            'create.html',
            errors=errors,
            form_data={'title': title, 'content': content, 'expiry': expiry_key}
        ), 400

    # Calculate expiration datetime
    created_at = utc_now()
    delta = EXPIRY_MAP[expiry_key]
    expires_at = (created_at + delta) if delta else None

    # Generate unique short ID and secret creator deletion token
    short_id = generate_short_id()
    delete_token = secrets.token_urlsafe(24)

    # Save attached file to disk if provided
    if has_valid_file:
        stored_filename = f"{short_id}_{secure_filename(original_name)}"
        file_dest = os.path.join(app.config['UPLOAD_FOLDER'], stored_filename)
        uploaded_file.save(file_dest)
        file_size = os.path.getsize(file_dest)
        file_mimetype = uploaded_file.mimetype or 'application/octet-stream'

    new_paste = Paste(
        short_id=short_id,
        delete_token=delete_token,
        title=title,
        content=content if content.strip() else None,
        file_filename=stored_filename,
        file_original_name=original_name,
        file_size=file_size,
        file_mimetype=file_mimetype,
        created_at=created_at,
        expires_at=expires_at,
        view_count=0
    )

    db.session.add(new_paste)
    db.session.commit()

    # Store creator token in client's signed HTTP session cookie
    session[f'delete_token_{short_id}'] = delete_token

    return redirect(url_for('view_paste', short_id=short_id))


@app.route('/p/<short_id>')
def view_paste(short_id: str):
    """
    Finds and displays a paste by its short ID.
    Checks expiration, increments the view counter, checks creator authorization,
    and renders content/files safely.
    """
    paste = Paste.query.filter_by(short_id=short_id).first()

    # Paste does not exist
    if not paste:
        return render_template(
            'error.html',
            error_title="Paste Not Found",
            error_message="The requested paste does not exist or has already been deleted."
        ), 404

    # Paste has expired
    if paste.is_expired():
        # Remove attached file and record from database
        cleanup_paste_file(paste)
        db.session.delete(paste)
        db.session.commit()
        return render_template('expired.html'), 410

    # Verify whether current visitor is the creator
    is_creator = is_authorized_creator(paste)

    # Increment view count
    paste.view_count += 1
    db.session.commit()

    return render_template('paste.html', paste=paste, is_creator=is_creator)


@app.route('/p/<short_id>/file')
def download_file(short_id: str):
    """
    Streams or downloads the attached file for a paste.
    Checks expiration and serves the file safely using send_from_directory.
    """
    paste = Paste.query.filter_by(short_id=short_id).first()

    if not paste or not paste.file_filename:
        return render_template(
            'error.html',
            error_title="File Not Found",
            error_message="No file is associated with this paste."
        ), 404

    if paste.is_expired():
        cleanup_paste_file(paste)
        db.session.delete(paste)
        db.session.commit()
        return render_template('expired.html'), 410

    # If requested as download or if it's a non-image file, set as_attachment=True
    download_flag = request.args.get('download', '0') == '1'
    as_attachment = download_flag or not paste.is_image

    return send_from_directory(
        app.config['UPLOAD_FOLDER'],
        paste.file_filename,
        as_attachment=as_attachment,
        download_name=paste.file_original_name
    )


@app.route('/p/<short_id>/delete', methods=['POST'])
def delete_paste(short_id: str):
    """
    Deletes a paste given its short ID.
    Enforces authorization: only the creator possessing the secret token can delete.
    """
    paste = Paste.query.filter_by(short_id=short_id).first()

    if not paste:
        flash("Paste not found or has already been removed.", "info")
        return redirect(url_for('index'))

    # Verify authorization
    if not is_authorized_creator(paste):
        return render_template(
            'error.html',
            error_title="Permission Denied",
            error_message="Only the creator of this paste has permission to delete it."
        ), 403

    # Clean up file and remove database record
    cleanup_paste_file(paste)
    db.session.delete(paste)
    db.session.commit()

    # Clear creator token from session
    session.pop(f'delete_token_{short_id}', None)
    flash("Paste and attached files were successfully deleted.", "success")

    return redirect(url_for('index'))


@app.route('/health')
def health_check():
    """Simple JSON health-check route."""
    return jsonify({"status": "ok"}), 200


@app.errorhandler(403)
def handle_403(e):
    """Custom 403 Forbidden error handler."""
    return render_template(
        'error.html',
        error_title="Permission Denied",
        error_message="You do not have permission to perform this action."
    ), 403


@app.errorhandler(404)
def handle_404(e):
    """Custom 404 Not Found error handler."""
    return render_template(
        'error.html',
        error_title="Page Not Found",
        error_message="The page you are looking for does not exist."
    ), 404


@app.errorhandler(413)
def handle_413(e):
    """Custom 413 Payload Too Large error handler for oversized file uploads."""
    return render_template(
        'error.html',
        error_title="File Too Large",
        error_message="The uploaded file exceeds the 10 MB maximum allowed limit."
    ), 413


@app.errorhandler(500)
def handle_500(e):
    """Custom 500 Internal Server Error handler."""
    return render_template(
        'error.html',
        error_title="Internal Server Error",
        error_message="Something went wrong on our end. Please try again later."
    ), 500


# Auto-create tables on startup
with app.app_context():
    db.create_all()


if __name__ == '__main__':
    # Run the Flask development server on port 5000
    app.run(host='127.0.0.1', port=5000, debug=True)
