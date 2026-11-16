"""ЛР1, вариант 7: Flask, загрузка изображения, CAPTCHA, RGB и графики."""
import hashlib
import re
from datetime import date
import io
import os
import time
import secrets
import threading
from flask import Flask, request, session, render_template, send_file, jsonify, make_response
from PIL import Image, ImageDraw, UnidentifiedImageError
from werkzeug.exceptions import RequestEntityTooLarge
from processing import decode_image, permute_channels, metrics, png_data, charts, ORDERS, encoded_data


VERIFY_TOKEN = 'TUSUR-BAKETIN-20261105-D819EB6B'


def normalize_html(html: str) -> str:
    """Канонизация по правилам задания руководителя."""
    lines = [line.strip() for line in html.split('\n')]
    lines = [line for line in lines if line]
    lines = [re.sub(r'\s+', ' ', line) for line in lines]
    return '\n'.join(lines)


def create_app(config=None):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=os.environ.get('SECRET_KEY') or secrets.token_hex(32),
        MAX_CONTENT_LENGTH=8 * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
    )
    if config:
        app.config.update(config)
    # Одноразовые ответы хранятся на сервере, а не в читаемой cookie.
    store, lock = {}, threading.Lock()
    app.extensions['captcha_store'] = store

    def challenge():
        now = time.time()
        with lock:
            for token in list(store):
                if store[token]['expires'] < now:
                    del store[token]
            if len(store) > 1000:
                store.clear()
            token = secrets.token_urlsafe(24)
            left, right = secrets.randbelow(15) + 1, secrets.randbelow(15) + 1
            store[token] = {'answer': str(left + right), 'left': left,
                            'right': right, 'expires': now + 300}
        session['captcha_token'] = token
        session['csrf'] = secrets.token_urlsafe(24)
        return token

    def page(error=None, result=None, status=200):
        token = challenge()
        return render_template('index.html', token=token, csrf=session['csrf'],
                               orders=ORDERS, error=error, result=result), status

    @app.get('/')
    def index():
        return page()

    @app.get('/captcha/<token>.png')
    def captcha(token):
        if not secrets.compare_digest(token, session.get('captcha_token', '')):
            return 'CAPTCHA не найдена', 404
        with lock:
            item = store.get(token)
        if not item or item['expires'] < time.time():
            return 'CAPTCHA истекла', 410
        image = Image.new('RGB', (220, 60), '#edf3fa')
        draw = ImageDraw.Draw(image)
        for _ in range(10):
            draw.line(tuple(secrets.randbelow(60 if i % 2 else 220)
                            for i in range(4)), fill='#bac7d5', width=1)
        draw.text((30, 14), f"{item['left']} + {item['right']} = ?",
                  fill='#10253b', font_size=24)
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        buffer.seek(0)
        response = send_file(buffer, mimetype='image/png')
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.post('/process')
    def process():
        # Проверки токена и CAPTCHA предшествуют чтению изображения.
        if not secrets.compare_digest(request.form.get('csrf', ''),
                                      session.get('csrf', 'missing')):
            return page('Обновите страницу: токен формы неверен.', status=403)
        token = request.form.get('captcha_token', '')
        if not secrets.compare_digest(token, session.get('captcha_token', '')):
            return page('Проверка на робота не пройдена.', status=400)
        with lock:
            item = store.pop(token, None)  # Повторное использование невозможно.
        answer = request.form.get('captcha_answer', '').strip()
        if (not item or item['expires'] < time.time()
                or not secrets.compare_digest(answer, item['answer'])):
            return page('Неверный или просроченный ответ CAPTCHA.', status=400)
        upload = request.files.get('image')
        if upload is None or not upload.filename:
            return page('Выберите изображение.', status=400)
        try:
            original = decode_image(upload.stream)
            order = request.form.get('order', '')
            result_image = permute_channels(original, order)
            output_format = request.form.get('output_format', 'PNG')
            download, extension = encoded_data(result_image, output_format)
            before, after = metrics(original), metrics(result_image)
            result = {
                'download': download, 'extension': extension,
                'output_format': output_format,
                'order': order, 'before': before, 'after': after,
                'original': png_data(original), 'image': png_data(result_image),
                'before_charts': charts(before, 'Исходное изображение'),
                'after_charts': charts(after, 'Результат ' + order),
            }
            return page(result=result)
        except (ValueError, UnidentifiedImageError, OSError,
                Image.DecompressionBombError, Image.DecompressionBombWarning):
            return page('Файл повреждён, слишком большой или имеет неверный формат/порядок каналов.', status=400)

    @app.get('/verify')
    def verify():
        today = date.today().isoformat()
        html = f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Verification</title></head>
<body>
<h1>Verification</h1>
<p>Token: {VERIFY_TOKEN}</p>
<p>Date: {today}</p>
</body>
</html>
"""
        normalized = normalize_html(html)
        body_hash = hashlib.sha256(
            normalized.encode('utf-8')).hexdigest()
        response = make_response(html)
        response.headers['X-Verify-Hash'] = body_hash
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.get('/health')
    def health():
        return jsonify(status='ok', lab=1, variant=7)

    @app.errorhandler(RequestEntityTooLarge)
    def too_large(error):
        return page('Размер загрузки не должен превышать 8 МиБ.', status=413)

    return app


app = create_app()
if __name__ == '__main__':
    app.run(host='127.0.0.1', port=int(os.environ.get('PORT', 5001)), debug=False)
