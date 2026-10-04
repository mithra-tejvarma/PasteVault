# PasteVault - Technical Interview Study Guide

This document contains concise, high-impact answers to key architectural, security, and design questions about **PasteVault**. It is tailored for CSE students and software engineering job interviews.

---

### 1. What problem does PasteVault solve?
PasteVault provides an instant, distraction-free way to share raw text, code snippets, notes, or debugging logs with others through a short, clean URL without requiring account registration, complex logins, or third-party tracking. It also provides automatic expiration so temporary snippets don't persist indefinitely.

---

### 2. Why Flask?
Flask is a lightweight Python WSGI microframework that gives direct control over routing, request parsing, and template rendering without imposing rigid project structure or heavyweight boilerplate like Django. It is ideal for small, focused services, educational codebases, and microservices because every line of code serves a clear purpose.

---

### 3. Why SQLite?
SQLite is a serverless, zero-configuration, file-based relational database engine embedded directly into the application process. 
- It requires no standalone database server daemon, background processes, or network overhead.
- The entire database is stored in a single file (`instance/pastevault.db`), making local setup, testing, and portability seamless.

---

### 4. Why SQLAlchemy?
SQLAlchemy is a Python Object-Relational Mapper (ORM).
- **Security**: It automatically uses parameterized SQL queries under the hood, protecting the application from SQL Injection attacks.
- **Maintainability**: It allows us to define database tables as Python classes (`Paste`) and manipulate database rows as standard Python objects rather than concatenating error-prone raw SQL queries.
- **Portability**: It decouples application logic from the database vendor. Switching from SQLite to PostgreSQL or MySQL requires only changing the connection string (`SQLALCHEMY_DATABASE_URI`) with zero changes to model queries.

---

### 5. How does a request travel from browser to Flask?
1. The user performs an action (e.g. clicks "Create Paste" or visits `/p/Ab12X`).
2. The browser constructs an HTTP request (method, headers, body) and transmits it over TCP/IP to the host and port (`127.0.0.1:5000`).
3. Flask's WSGI server receives the raw HTTP packet, parses the HTTP method and URI path, and matches it against registered route decorators (e.g., `@app.route('/p/<short_id>')`).
4. Flask parses parameters, query strings, and form bodies into the `request` context object and calls the associated Python view function.
5. The view function interacts with the database via SQLAlchemy, renders a Jinja2 HTML template or JSON response, and returns an HTTP response object (with status code and headers) back to the browser.

---

### 6. How is a paste stored?
A paste is stored as a single record in the `pastes` table in SQLite with the following schema:
- `id` (INTEGER PRIMARY KEY AUTOINCREMENT): Internal numeric identifier.
- `short_id` (VARCHAR(8) UNIQUE INDEX): Publicly exposed shareable code (e.g. `Ab12X9`).
- `title` (VARCHAR(100)): Sanitized title of the paste.
- `content` (TEXT): The full text/code content (up to 50,000 characters).
- `created_at` (DATETIME): UTC timestamp recorded when the record was inserted.
- `expires_at` (DATETIME, nullable): UTC timestamp when the paste should expire, or `NULL` if it never expires.
- `view_count` (INTEGER): Counter incremented on each non-expired GET view.

---

### 7. How is the short ID generated?
The short ID is generated using Python’s cryptographically secure standard library module `secrets`:
```python
alphabet = string.ascii_letters + string.digits  # 62 characters
candidate = ''.join(secrets.choice(alphabet) for _ in range(6))
```
- With 6 characters chosen from 62 possible symbols, there are $62^6 \approx 56.8 \text{ billion}$ unique combinations.
- To guarantee uniqueness and handle the rare chance of collisions, the generator checks `Paste.query.filter_by(short_id=candidate).first()`. If no record exists with that ID, it is assigned. If a collision occurs, it retries with a new candidate.

---

### 8. How does the application detect expiration?
The application uses **lazy expiration check** upon access:
1. Each paste has an `expires_at` column storing a UTC datetime (or `NULL`).
2. When a user requests `/p/<short_id>`, the server queries the paste and checks `paste.is_expired()`:
   ```python
   def is_expired(self):
       if self.expires_at is None:
           return False
       return utc_now() > self.expires_at
   ```
3. If current UTC time is greater than `expires_at`, the route deletes the expired record from SQLite to free storage, and immediately returns the `expired.html` template with an HTTP `410 Gone` status code.
4. The paste content is never sent to the client once expired.

---

### 9. Why is delete implemented using POST?
According to the HTTP/1.1 specification (RFC 7231):
- **`GET` must be safe and idempotent**: GET requests are intended strictly for data retrieval and should never trigger side-effects or state modifications on the server.
- **Vulnerabilities of GET deletion**:
  - Web crawlers, search indexers, and browser pre-fetchers automatically follow GET links, which would accidentally delete pastes without user consent.
  - Cross-Site Request Forgery (CSRF): An attacker could trick a user into opening an image tag `<img src="/p/Ab12X/delete">`, causing unauthorized deletion.
- **POST** is semantically designed for state-changing operations and allows proper validation and form confirmation.

---

### 10. How does the copy button work?
The copy functionality is implemented in vanilla JavaScript:
1. It listens for click events on the `#btn-copy-content` and `#btn-copy-url` buttons.
2. It uses the modern asynchronous Clipboard API:
   ```javascript
   navigator.clipboard.writeText(text).then(...)
   ```
3. If the browser does not support `navigator.clipboard` or is running in an insecure non-HTTPS context, it uses a fallback mechanism (`document.execCommand('copy')` via a hidden textarea).
4. Upon success, it updates the button label to "Copied!" and reveals a toast notification for 2 seconds, providing immediate visual feedback.

---

### 11. How is user content protected from XSS (Cross-Site Scripting)?
Cross-Site Scripting occurs when untrusted user input is rendered directly into the HTML DOM as executable markup or script tags.
In PasteVault:
1. **Jinja2 Auto-Escaping**: We deliberately do **not** use the `|safe` filter on `paste.content` or `paste.title`. Jinja2 automatically escapes HTML characters (`<` becomes `&lt;`, `>` becomes `&gt;`, `"` becomes `&#34;`, `&` becomes `&amp;`).
2. **Whitespace Preservation via CSS**: To render code indentation and line breaks naturally without converting newlines to unescaped `<br>` tags, we use the CSS rule:
   ```css
   white-space: pre-wrap;
   ```
   This ensures malicious scripts like `<script>alert('pwned')</script>` are rendered strictly as harmless visual text strings.

---

### 12. What happens when a paste doesn't exist?
When a user visits a non-existent short ID (e.g. `/p/doesNotExist`):
1. `Paste.query.filter_by(short_id=short_id).first()` returns `None`.
2. Flask renders the custom `error.html` template informing the user:
   > *"The requested paste does not exist or has already been deleted."*
3. The response is sent with an HTTP **404 Not Found** status code.
4. A button is provided to return to the home page or create a new paste.

---

### 13. What happens when two pastes accidentally get the same short ID?
Two pastes can never collide in the database due to two safeguards:
1. **Application-level collision check**: Before committing a paste, `generate_short_id()` queries the database. If a generated string already exists, the function regenerates a new random string in a retry loop.
2. **Database-level constraint**: The `short_id` column is defined with `unique=True`. Even under concurrent race conditions, SQLite will enforce a unique constraint violation rather than allowing duplicate keys.

---

### 14. What is the difference between GET and POST in this project?

| Feature | GET | POST |
|---|---|---|
| **Intended Purpose** | Reading data (safe, idempotent) | Submitting data / altering server state |
| **Data Transmission** | Via URL parameters / query string | Inside HTTP request body |
| **Browser Caching** | Can be cached and bookmarked | Never cached by default |
| **Usage in PasteVault** | `GET /` (home), `GET /create` (render form), `GET /p/<id>` (view paste), `GET /health` | `POST /create` (create paste), `POST /p/<id>/delete` (delete paste) |

---

### 15. What would you change if the application had 100,000 users?
If PasteVault scaled to 100,000 daily active users:
1. **Database**: Replace single-file SQLite with a managed relational database like **PostgreSQL** or **MySQL** to handle high concurrent writes and connection pooling.
2. **WSGI Production Server**: Run Flask behind a production-grade WSGI application server like **Gunicorn** or **uWSGI** with multiple worker processes, reverse-proxied by **Nginx**.
3. **Caching Layer (Redis / Memcached)**:
   - Cache frequently accessed pastes in memory (e.g. Redis) with TTL matching paste expiration, eliminating 90%+ of read queries to the database.
   - Buffer view counter updates in Redis before batch-writing to the database to prevent database write lock contention.
4. **Background Expiration Job**: Replace lazy per-request deletion with a background worker (e.g. Celery beat or a cron job) that periodically runs `DELETE FROM pastes WHERE expires_at < NOW()`.
5. **Rate Limiting & Abuse Prevention**: Implement rate limiting (e.g. `Flask-Limiter` with Redis) to prevent spamming, DDoS, or scraping.
6. **Object Storage for Large Pastes**: Store large text bodies in an S3-compatible object store (e.g. AWS S3 / Cloudflare R2) and store only metadata and file pointers in the database.
7. **Stateless Horizontal Scaling**: Containerize with Docker and run behind a load balancer across multiple application instances.

---

### 16. How do you ensure only the creator can delete a paste without user accounts?
Without requiring user logins, passwords, or account registration, we implement **anonymous creator authorization** via secret tokens:
1. When a user creates a paste, the server generates an unguessable 24-character cryptographic token:
   ```python
   delete_token = secrets.token_urlsafe(24)
   ```
2. This token is saved in the SQLite `pastes` table for that specific paste, and simultaneously set into the creator's browser via Flask's cryptographically signed HTTP-only session cookie (`session['delete_token_<short_id>']`).
3. When any visitor loads `/p/<short_id>`, the server checks if their session possesses the matching `delete_token`:
   - If **Yes** (the creator): The "Delete Paste" button and "Creator" badge are rendered.
   - If **No** (a public visitor): The delete button is completely omitted from the HTML DOM.
4. When a deletion request arrives at `POST /p/<short_id>/delete`, the backend re-verifies the token using `secrets.compare_digest()`. If an unauthorized third party attempts to forge a deletion request, Flask rejects it with **HTTP 403 Forbidden**.

---

### 17. How are files and images stored and served, and why not store them in the database as BLOBs?
Files and images are stored using the **Filesystem Storage + Database Metadata** pattern:
- The raw file bytes are saved to a dedicated local directory: `instance/uploads/<short_id>_<sanitized_filename>`.
- The database stores only the metadata: `file_filename`, `file_original_name`, `file_size`, and `file_mimetype`.
- Files are served safely using Flask's built-in `send_from_directory()`.

**Why not store files as BLOBs in SQLite?**
1. **Database Page Fragmentation & Bloat**: Relational database engines store rows in fixed-size B-tree pages (typically 4 KB). Storing multi-megabyte binary blobs causes page overflow, rapid database file inflation, and inefficient disk I/O.
2. **Memory & Query Performance**: Simple metadata queries (e.g. `SELECT title, created_at`) become dramatically slower if heavy binary data lives in the same table, exhausting database buffer pools.
3. **Streaming & Caching**: Files on disk can take direct advantage of OS page caches, web server kernel streaming (e.g. `sendfile`), and CDN caching, which cannot be done cleanly with database BLOBs.

---

### 18. What security measures protect file uploads in PasteVault?
1. **Path Traversal Prevention**: User filenames could contain malicious sequences like `../../etc/passwd` or `..\system32\`. We sanitize all filenames using Werkzeug's `secure_filename()` and prefix with `short_id_` to prevent overwriting server files.
2. **Denial of Service (DoS) Prevention via Upload Caps**: We enforce `app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024` (10 MB). Flask terminates oversized payloads early and returns HTTP `413 Payload Too Large`.
3. **Orphan File Prevention / TTL Cleanup**: When a paste expires or is manually deleted by the creator, the application executes `os.remove()` to unlink the physical file from disk so storage is never leaked.
