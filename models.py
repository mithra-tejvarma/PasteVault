import os
from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy

# Initialize the SQLAlchemy database instance
db = SQLAlchemy()


def utc_now():
    """Returns the current UTC datetime without timezone offset for SQLite compatibility."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Paste(db.Model):
    """
    Paste model representing a stored text/code snippet and optional attached file/image.

    Columns:
        id: Integer primary key (internal use only, not exposed in URLs)
        short_id: Unique 6-character random identifier for public sharing
        delete_token: Secret token generated for creator authorization to delete
        title: User-provided title (max 100 characters)
        content: User-provided text or code (max 50,000 characters, nullable if file provided)
        file_filename: Safe name of attached file on disk (nullable)
        file_original_name: Original user upload filename for display/download (nullable)
        file_size: Size in bytes of attached file (nullable)
        file_mimetype: MIME type of attached file (nullable)
        created_at: Datetime when the paste was created (UTC)
        expires_at: Optional expiration datetime (UTC, nullable)
        view_count: Number of times this paste has been viewed
    """
    __tablename__ = 'pastes'

    id = db.Column(db.Integer, primary_key=True)
    short_id = db.Column(db.String(8), unique=True, nullable=False, index=True)
    delete_token = db.Column(db.String(32), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=True)

    # Optional file/image attachment metadata
    file_filename = db.Column(db.String(255), nullable=True)
    file_original_name = db.Column(db.String(255), nullable=True)
    file_size = db.Column(db.Integer, nullable=True)
    file_mimetype = db.Column(db.String(100), nullable=True)

    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=True)
    view_count = db.Column(db.Integer, default=0, nullable=False)

    def is_expired(self) -> bool:
        """Checks if the paste has passed its expiration datetime."""
        if self.expires_at is None:
            return False
        return utc_now() > self.expires_at

    @property
    def has_file(self) -> bool:
        """Returns True if a file or image is attached to this paste."""
        return bool(self.file_filename)

    @property
    def is_image(self) -> bool:
        """Returns True if the attached file is an image that can be rendered inline."""
        if not self.file_filename:
            return False
        if self.file_mimetype and self.file_mimetype.startswith('image/'):
            return True
        ext = os.path.splitext(self.file_filename)[1].lower()
        return ext in {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.bmp'}

    @property
    def formatted_file_size(self) -> str:
        """Returns a human-readable file size string (e.g. 245.0 KB)."""
        if not self.file_size:
            return "0 B"
        size = self.file_size
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        else:
            return f"{size / (1024 * 1024):.1f} MB"

    def __repr__(self):
        return f"<Paste {self.short_id}: '{self.title}'>"
