import io
import os
import re
import shutil
import tempfile
import unittest
from datetime import timedelta

from app import app, db, utc_now
from models import Paste


class PasteVaultTestCase(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for uploaded files during tests
        self.test_upload_dir = tempfile.mkdtemp()
        app.config['UPLOAD_FOLDER'] = self.test_upload_dir
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['WTF_CSRF_ENABLED'] = False

        self.client = app.test_client()

        with app.app_context():
            db.create_all()

    def tearDown(self):
        with app.app_context():
            db.session.remove()
            db.drop_all()
        # Clean up temporary uploads folder
        if os.path.exists(self.test_upload_dir):
            shutil.rmtree(self.test_upload_dir)

    def test_health_check(self):
        """Health check returns status ok."""
        response = self.client.get('/health')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ok"})

    def test_home_page(self):
        """Home page loads with landing content and CTA."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("PasteVault", html)
        self.assertIn("Share text and code with a simple link.", html)
        self.assertIn("Create a Paste", html)
        self.assertIn("Simple Sharing", html)
        self.assertIn("Optional Expiration", html)

    def test_1_and_2_create_and_open_normal_paste(self):
        """Test 1 & 2: Create a normal paste and open generated URL."""
        response = self.client.post('/create', data={
            'title': 'Test Paste 1',
            'content': 'print("Hello World!")\nfor i in range(5):\n    print(i)',
            'expiry': 'never'
        }, follow_redirects=False)

        # Should redirect to /p/<short_id>
        self.assertEqual(response.status_code, 302)
        redirect_url = response.headers['Location']
        self.assertTrue(re.search(r'/p/[A-Za-z0-9]{6}', redirect_url))

        short_id = redirect_url.split('/p/')[-1]

        # Open the generated URL as creator (client has session cookie)
        view_response = self.client.get(f'/p/{short_id}')
        self.assertEqual(view_response.status_code, 200)
        html = view_response.get_data(as_text=True)
        self.assertIn('Test Paste 1', html)
        self.assertIn('print(&#34;Hello World!&#34;)', html)
        self.assertIn('/p/' + short_id, html)
        self.assertIn('Views: <strong>1</strong>', html)
        # Creator badge and delete button should be visible to creator
        self.assertIn('Creator', html)
        self.assertIn('Delete Paste', html)

    def test_3_view_count_increases(self):
        """Test 3: Refresh page and verify view count increases."""
        with app.app_context():
            paste = Paste(
                short_id='cnt123',
                delete_token='dummy_token_123',
                title='Counter Test',
                content='Sample counter body',
                created_at=utc_now(),
                expires_at=None,
                view_count=0
            )
            db.session.add(paste)
            db.session.commit()

        # First visit
        res1 = self.client.get('/p/cnt123')
        self.assertEqual(res1.status_code, 200)
        self.assertIn('Views: <strong>1</strong>', res1.get_data(as_text=True))

        # Second visit
        res2 = self.client.get('/p/cnt123')
        self.assertEqual(res2.status_code, 200)
        self.assertIn('Views: <strong>2</strong>', res2.get_data(as_text=True))

        # Third visit
        res3 = self.client.get('/p/cnt123')
        self.assertEqual(res3.status_code, 200)
        self.assertIn('Views: <strong>3</strong>', res3.get_data(as_text=True))

        with app.app_context():
            updated = Paste.query.filter_by(short_id='cnt123').first()
            self.assertEqual(updated.view_count, 3)

    def test_4_and_5_copy_features_and_xss_protection(self):
        """Test 4 & 5: Check copy buttons present and content is safely escaped."""
        xss_payload = "<script>alert('xss')</script><b>Bold content</b>"
        response = self.client.post('/create', data={
            'title': '<script>alert(1)</script>Safe Title',
            'content': xss_payload,
            'expiry': 'never'
        }, follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)

        # Verify buttons exist for JavaScript Clipboard API
        self.assertIn('id="btn-copy-content"', html)
        self.assertIn('id="btn-copy-url"', html)
        self.assertIn('Copy Content', html)
        self.assertIn('Copy Share URL', html)

        # Verify XSS payload is strictly HTML-escaped and NOT rendered raw
        self.assertNotIn("<script>alert('xss')</script>", html)
        self.assertIn("&lt;script&gt;alert(&#39;xss&#39;)&lt;/script&gt;", html)
        self.assertNotIn("<b>Bold content</b>", html)
        self.assertIn("&lt;b&gt;Bold content&lt;/b&gt;", html)

    def test_6_expiration_ten_minutes(self):
        """Test 6: Create a paste with 10-minute expiration and verify handling."""
        before_creation = utc_now()
        response = self.client.post('/create', data={
            'title': 'Expiring Note',
            'content': 'Secret temp note',
            'expiry': '10m'
        }, follow_redirects=False)

        self.assertEqual(response.status_code, 302)
        short_id = response.headers['Location'].split('/p/')[-1]

        with app.app_context():
            paste = Paste.query.filter_by(short_id=short_id).first()
            self.assertIsNotNone(paste.expires_at)
            expected_min = before_creation + timedelta(minutes=9, seconds=55)
            expected_max = before_creation + timedelta(minutes=10, seconds=5)
            self.assertTrue(expected_min <= paste.expires_at <= expected_max)
            self.assertFalse(paste.is_expired())

        # Viewing before expiry works
        view_res = self.client.get(f'/p/{short_id}')
        self.assertEqual(view_res.status_code, 200)
        self.assertIn('Expiring Note', view_res.get_data(as_text=True))

        # Simulate time passing beyond expiration
        with app.app_context():
            p = Paste.query.filter_by(short_id=short_id).first()
            p.expires_at = utc_now() - timedelta(minutes=1)  # expired 1 minute ago
            db.session.commit()

        # Viewing after expiry returns 410 Expired
        expired_res = self.client.get(f'/p/{short_id}')
        self.assertEqual(expired_res.status_code, 410)
        self.assertIn('Paste Expired', expired_res.get_data(as_text=True))

        # Verify expired paste was cleaned up / deleted from DB
        with app.app_context():
            deleted_check = Paste.query.filter_by(short_id=short_id).first()
            self.assertIsNone(deleted_check)

    def test_7_validation_rejects_invalid_inputs(self):
        """Test 7: Verify invalid title/content is rejected with friendly messages."""
        # 1. Empty title
        res1 = self.client.post('/create', data={
            'title': '   ',
            'content': 'Valid content',
            'expiry': 'never'
        })
        self.assertEqual(res1.status_code, 400)
        self.assertIn('Title is required.', res1.get_data(as_text=True))

        # 2. Empty content and no file
        res2 = self.client.post('/create', data={
            'title': 'Valid Title',
            'content': '   \n  ',
            'expiry': 'never'
        })
        self.assertEqual(res2.status_code, 400)
        self.assertIn('Please provide text content, an attached file/image, or both.', res2.get_data(as_text=True))

        # 3. Title exceeds 100 chars
        res3 = self.client.post('/create', data={
            'title': 'A' * 101,
            'content': 'Valid content',
            'expiry': 'never'
        })
        self.assertEqual(res3.status_code, 400)
        self.assertIn('Title cannot exceed 100 characters.', res3.get_data(as_text=True))

        # 4. Content exceeds 50,000 chars
        res4 = self.client.post('/create', data={
            'title': 'Valid Title',
            'content': 'B' * 50001,
            'expiry': 'never'
        })
        self.assertEqual(res4.status_code, 400)
        self.assertIn('Content cannot exceed 50,000 characters.', res4.get_data(as_text=True))

    def test_8_nonexistent_short_id(self):
        """Test 8: Try opening a nonexistent short ID returns friendly 404."""
        response = self.client.get('/p/noSuch9')
        self.assertEqual(response.status_code, 404)
        html = response.get_data(as_text=True)
        self.assertIn('Paste Not Found', html)

    def test_creator_authorization_and_delete_protection(self):
        """
        Tests creator authorization:
        - Creator (with session) sees Delete button and can delete.
        - Other visitor (new client without session) does NOT see Delete button.
        - Other visitor attempting POST /p/<id>/delete receives 403 Forbidden.
        """
        # Creator client creates paste
        creator_client = self.client
        response = creator_client.post('/create', data={
            'title': 'Creator Protected Paste',
            'content': 'Confidential notes',
            'expiry': 'never'
        }, follow_redirects=False)
        short_id = response.headers['Location'].split('/p/')[-1]

        # 1. Creator visits page: Delete button is visible
        creator_view = creator_client.get(f'/p/{short_id}')
        self.assertEqual(creator_view.status_code, 200)
        self.assertIn('Delete Paste', creator_view.get_data(as_text=True))
        self.assertIn('Creator', creator_view.get_data(as_text=True))

        # 2. Another visitor visits page using a separate client (no session cookie)
        visitor_client = app.test_client()
        visitor_view = visitor_client.get(f'/p/{short_id}')
        self.assertEqual(visitor_view.status_code, 200)
        # Delete button MUST NOT be rendered for third parties!
        self.assertNotIn('Delete Paste', visitor_view.get_data(as_text=True))
        self.assertNotIn('<span class="creator-badge"', visitor_view.get_data(as_text=True))

        # 3. Third-party maliciously sends POST to delete endpoint -> 403 Forbidden!
        unauthorized_delete = visitor_client.post(f'/p/{short_id}/delete')
        self.assertEqual(unauthorized_delete.status_code, 403)
        self.assertIn('Permission Denied', unauthorized_delete.get_data(as_text=True))

        # Verify paste still exists in database
        with app.app_context():
            paste = Paste.query.filter_by(short_id=short_id).first()
            self.assertIsNotNone(paste)

        # 4. Creator sends POST to delete endpoint -> Successfully deleted!
        authorized_delete = creator_client.post(f'/p/{short_id}/delete', follow_redirects=True)
        self.assertEqual(authorized_delete.status_code, 200)
        self.assertIn('Paste and attached files were successfully deleted.', authorized_delete.get_data(as_text=True))

        # Verify paste is now removed
        with app.app_context():
            deleted_check = Paste.query.filter_by(short_id=short_id).first()
            self.assertIsNone(deleted_check)

    def test_file_and_image_upload_and_download(self):
        """
        Tests uploading an image, viewing preview, downloading, and file disk cleanup upon deletion.
        """
        # Create a dummy image file in memory
        dummy_image_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4'
        file_obj = (io.BytesIO(dummy_image_data), 'test_diagram.png')

        response = self.client.post('/create', data={
            'title': 'System Architecture Diagram',
            'content': 'Here is the architecture image attached below.',
            'expiry': 'never',
            'file': file_obj
        }, content_type='multipart/form-data', follow_redirects=False)

        self.assertEqual(response.status_code, 302)
        short_id = response.headers['Location'].split('/p/')[-1]

        # Check DB record
        with app.app_context():
            paste = Paste.query.filter_by(short_id=short_id).first()
            self.assertIsNotNone(paste)
            self.assertTrue(paste.has_file)
            self.assertTrue(paste.is_image)
            self.assertEqual(paste.file_original_name, 'test_diagram.png')
            saved_filename = paste.file_filename
            disk_path = os.path.join(app.config['UPLOAD_FOLDER'], saved_filename)
            self.assertTrue(os.path.exists(disk_path), "File must be saved to disk")

        # View page: Should display image preview
        view_res = self.client.get(f'/p/{short_id}')
        self.assertEqual(view_res.status_code, 200)
        html = view_res.get_data(as_text=True)
        self.assertIn('test_diagram.png', html)
        self.assertIn(f'/p/{short_id}/file', html)
        self.assertIn('attached-image', html)

        # Download / Stream file
        download_res = self.client.get(f'/p/{short_id}/file')
        self.assertEqual(download_res.status_code, 200)
        self.assertEqual(download_res.data, dummy_image_data)
        download_res.close()  # Release open file stream handle on Windows

        # Creator deletes paste -> disk file must also be removed!
        del_res = self.client.post(f'/p/{short_id}/delete')
        self.assertEqual(del_res.status_code, 302)
        self.assertFalse(os.path.exists(disk_path), "File must be deleted from disk on delete")

    def test_file_only_paste(self):
        """Allows creating a paste with only a file and no text content."""
        file_data = b'def add(a, b):\n    return a + b\n'
        file_obj = (io.BytesIO(file_data), 'math_utils.py')

        response = self.client.post('/create', data={
            'title': 'Python Math Helper',
            'content': '',
            'expiry': 'never',
            'file': file_obj
        }, content_type='multipart/form-data', follow_redirects=False)

        self.assertEqual(response.status_code, 302)
        short_id = response.headers['Location'].split('/p/')[-1]

        view_res = self.client.get(f'/p/{short_id}')
        self.assertEqual(view_res.status_code, 200)
        html = view_res.get_data(as_text=True)
        self.assertIn('math_utils.py', html)
        self.assertIn('Download File', html)


if __name__ == '__main__':
    unittest.main()
