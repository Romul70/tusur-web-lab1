"""Проверки варианта 7: пиксели, числовые профили, формы, CAPTCHA и ошибки."""
import io
import re
import time
import base64
import unittest
from unittest.mock import patch
from PIL import Image
import numpy as np
from app import create_app
from processing import permute_channels, metrics, ORDERS, decode_image


def sample():
    return Image.fromarray(np.array([[[10, 20, 30], [40, 50, 60]],
                                     [[70, 80, 90], [100, 110, 120]]], dtype=np.uint8))


def upload(image=None):
    buffer = io.BytesIO()
    (image or sample()).save(buffer, format='PNG')
    buffer.seek(0)
    return buffer


class ProcessingTests(unittest.TestCase):
    def test_all_six_orders(self):
        original = np.asarray(sample())
        for order in ORDERS:
            result = np.asarray(permute_channels(sample(), order))
            np.testing.assert_array_equal(result, original[:, :, ['RGB'.index(c) for c in order]])
            self.assertEqual(result.shape, original.shape)

    def test_metrics_exact_values(self):
        result = metrics(sample())
        self.assertEqual(result['mean_rgb'], [55, 65, 75])
        self.assertEqual(result['mean_by_x'], [[40, 50, 60], [70, 80, 90]])
        self.assertEqual(result['mean_by_y'], [[25, 35, 45], [85, 95, 105]])
        for histogram in result['histogram']:
            self.assertEqual(len(histogram), 256)
            self.assertEqual(sum(histogram), 4)

    def test_gray_and_rgba_conversion(self):
        for mode in ('L', 'RGBA'):
            image = Image.new(mode, (2, 2), 80 if mode == 'L' else (10, 20, 30, 0))
            result = decode_image(upload(image))
            self.assertEqual(result.mode, 'RGB')
            self.assertEqual(result.size, (2, 2))


class WebTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({'TESTING': True, 'SECRET_KEY': 'test-only'})
        self.client = self.app.test_client()

    def challenge(self):
        self.client.get('/')
        with self.client.session_transaction() as session:
            token, csrf = session['captcha_token'], session['csrf']
        return {'captcha_token': token, 'csrf': csrf,
                'captcha_answer': self.app.extensions['captcha_store'][token]['answer'], 'order': 'BGR'}

    def test_full_processing_and_charts(self):
        data = self.challenge()
        response = self.client.get('/captcha/' + data['captcha_token'] + '.png')
        self.assertEqual(response.status_code, 200)
        data['image'] = (upload(), 'test.png')
        response = self.client.post('/process', data=data)
        self.assertEqual(response.status_code, 200)
        text = response.get_data(as_text=True)
        self.assertIn('Среднее значение по координате X', text)
        self.assertIn('Среднее значение по координате Y', text)
        images = re.findall(r'src="data:image/png;base64,([^"]+)"', text)
        self.assertEqual(len(images), 8)  # Два изображения и шесть графиков.
        result = Image.open(io.BytesIO(base64.b64decode(images[1])))
        self.assertEqual(result.getpixel((0, 0)), (30, 20, 10))

    def test_captcha_rejection_expiry_and_reuse(self):
        data = self.challenge()
        data['captcha_answer'] = 'wrong'
        data['image'] = (upload(), 'test.png')
        with patch('app.decode_image') as decode:
            self.assertEqual(self.client.post('/process', data=data).status_code, 400)
            decode.assert_not_called()
        data = self.challenge()
        self.app.extensions['captcha_store'][data['captcha_token']]['expires'] = time.time() - 1
        data['image'] = (upload(), 'test.png')
        self.assertEqual(self.client.post('/process', data=data).status_code, 400)
        data = self.challenge()
        first = dict(data, image=(upload(), 'test.png'))
        self.assertEqual(self.client.post('/process', data=first).status_code, 200)
        again = dict(data, image=(upload(), 'test.png'))
        self.assertIn(self.client.post('/process', data=again).status_code, (400, 403))

    def test_invalid_image_order_csrf_and_limit(self):
        for content, order in [(b'not an image', 'BGR'), (upload().getvalue(), 'RRR')]:
            data = self.challenge()
            data.update(image=(io.BytesIO(content), 'bad.png'), order=order)
            self.assertEqual(self.client.post('/process', data=data).status_code, 400)
        data = self.challenge()
        data['csrf'] = 'wrong'
        self.assertEqual(self.client.post('/process', data=data).status_code, 403)
        self.app.config['MAX_CONTENT_LENGTH'] = 100
        self.assertEqual(self.client.post('/process', data={'image': (upload(), 'test.png')}).status_code, 413)
        self.assertEqual(self.client.get('/health').json['variant'], 7)


if __name__ == '__main__':
    unittest.main(verbosity=2)
