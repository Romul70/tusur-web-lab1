"""Независимо проверить хэш /verify: python check_verify.py URL."""
import hashlib
import re
import sys
from urllib.request import urlopen

url = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:5001/verify'
with urlopen(url, timeout=30) as response:
    body = response.read().decode('utf-8')
    expected = response.headers.get('X-Verify-Hash', '')
lines = [line.strip() for line in body.split('\n')]
normalized = '\n'.join(re.sub(r'\s+', ' ', line) for line in lines if line)
actual = hashlib.sha256(normalized.encode('utf-8')).hexdigest()
if not re.fullmatch(r'[0-9a-fA-F]{64}', expected):
    raise SystemExit('ERROR: отсутствует корректный X-Verify-Hash')
if actual != expected.lower():
    raise SystemExit('ERROR: хэш тела не совпал с заголовком')
print('OK: SHA-256 совпадает:', actual)
