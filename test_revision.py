import base64
import hashlib
import io
import re
import unittest
from datetime import date
from unittest.mock import patch
from PIL import Image
from app import create_app, normalize_html, VERIFY_TOKEN


class RevisionTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({'TESTING': True, 'SECRET_KEY': 'test'})
        self.client = self.app.test_client()

    def test_verify_independent_hash(self):
        response = self.client.get('/verify')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'text/html')
        body = response.get_data(as_text=True)
        self.assertIn(VERIFY_TOKEN, body)
        self.assertIn(date.today().isoformat(), body)
        # Независимый расчёт, без вызова normalize_html приложения.
        canonical = '\n'.join(' '.join(line.split())
                              for line in body.splitlines() if line.strip())
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        self.assertEqual(response.headers['X-Verify-Hash'], digest)
        self.assertRegex(digest, r'^[0-9a-f]{64}$')

    def test_normalization_and_date_change(self):
        self.assertEqual(normalize_html(' \r\n <p>  A\tB </p> \r\n\n'), '<p> A B </p>')
        with patch('app.date') as mocked:
            mocked.today.return_value = date(2026, 11, 14)
            first = self.client.get('/verify')
            mocked.today.return_value = date(2026, 11, 15)
            second = self.client.get('/verify')
        self.assertNotEqual(first.headers['X-Verify-Hash'], second.headers['X-Verify-Hash'])
        self.assertIn(b'2026-11-15', second.data)

    def form(self):
        self.client.get('/')
        with self.client.session_transaction() as session:
            token, csrf = session['captcha_token'], session['csrf']
        return dict(captcha_token=token, csrf=csrf, order='RGB',
                    captcha_answer=self.app.extensions['captcha_store'][token]['answer'])

    def test_nine_conversion_pairs(self):
        for source in ('PNG', 'JPEG', 'WEBP'):
            for target, mime, extension in (
                ('PNG', 'png', 'png'), ('JPEG', 'jpeg', 'jpg'),
                ('WEBP', 'webp', 'webp')):
                with self.subTest(source=source, target=target):
                    stream = io.BytesIO()
                    Image.new('RGB', (4, 3), (20, 80, 160)).save(stream, source)
                    original = Image.open(io.BytesIO(stream.getvalue())).convert('RGB')
                    stream.seek(0)
                    data = self.form()
                    data.update(output_format=target, image=(stream, 'source.' + source.lower()))
                    result = self.client.post('/process', data=data)
                    self.assertEqual(result.status_code, 200)
                    html = result.get_data(as_text=True)
                    match = re.search(r'href="data:image/' + mime + r';base64,([^"]+)"', html)
                    self.assertIsNotNone(match)
                    image = Image.open(io.BytesIO(base64.b64decode(match[1])))
                    self.assertEqual(image.format, target)
                    self.assertEqual(image.size, (4, 3))
                    self.assertIn('download="result_RGB.' + extension + '"', html)
                    if target != 'JPEG':
                        self.assertEqual(image.tobytes(), original.tobytes())
                    else:
                        self.assertLessEqual(max(abs(a-b) for a,b in zip(image.getpixel((0,0)), original.getpixel((0,0)))), 3)

    def test_invalid_output_format(self):
        data = self.form()
        stream = io.BytesIO()
        Image.new('RGB', (2,2)).save(stream, 'PNG')
        stream.seek(0)
        data.update(output_format='SVG', image=(stream, 'x.png'))
        self.assertEqual(self.client.post('/process', data=data).status_code, 400)
