"""Cache persistente opcional de análises fiscais: criptografia antes do disco.

Somente no volume já existente do Railway e com chave exclusiva de Fernet.
Falhas do cache nunca eliminam a conferência nem enviam dados externamente.
"""
import base64
import hashlib
import hmac
import json
import os
import sqlite3
import threading
import time

from cryptography.fernet import Fernet, InvalidToken

_guard = threading.RLock()
CACHE_SECONDS = 86400
MAX_ITEMS = 100
MAX_BYTES = 512_000


def _storage():
    base = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "")
    key = os.getenv("RAZYNC_AI_CACHE_KEY", "")
    if not base or not os.path.isdir(base) or not key:
        return None
    try:
        cipher = Fernet(key.encode("ascii"))
        secret = base64.urlsafe_b64decode(key.encode("ascii"))
    except (ValueError, TypeError, UnicodeError):
        return None
    if len(secret) != 32:
        return None
    return os.path.join(base, "razync_ai_cache.sqlite3"), cipher, secret


def stable_digest(serialized):
    storage = _storage()
    if storage is None:
        return None
    return hmac.new(storage[2], serialized.encode("utf-8"), hashlib.sha256).hexdigest()


def _connect(path):
    conn = sqlite3.connect(path, timeout=5)
    conn.execute("CREATE TABLE IF NOT EXISTS encrypted_ai_cache "
                 "(id TEXT PRIMARY KEY, expires REAL NOT NULL, ciphertext BLOB NOT NULL)")
    return conn


def read(key):
    storage = _storage()
    if storage is None:
        return None
    path, cipher, _ = storage
    try:
        with _guard, _connect(path) as conn:
            row = conn.execute(
                "SELECT expires, ciphertext FROM encrypted_ai_cache WHERE id=?", (key,)
            ).fetchone()
            if row is None:
                return None
            if row[0] <= time.time():
                conn.execute("DELETE FROM encrypted_ai_cache WHERE id=?", (key,))
                return None
            try:
                return json.loads(cipher.decrypt(row[1]))
            except (InvalidToken, ValueError, TypeError, UnicodeError):
                conn.execute("DELETE FROM encrypted_ai_cache WHERE id=?", (key,))
                return None
    except sqlite3.Error:
        return None


def write(key, response):
    storage = _storage()
    if storage is None:
        return False
    path, cipher, _ = storage
    try:
        plain = json.dumps(response, ensure_ascii=False, default=str).encode("utf-8")
        if len(plain) > MAX_BYTES:
            return False
        encrypted = cipher.encrypt(plain)
        with _guard, _connect(path) as conn:
            conn.execute("INSERT INTO encrypted_ai_cache(id,expires,ciphertext) VALUES(?,?,?) "
                         "ON CONFLICT(id) DO UPDATE SET expires=excluded.expires,ciphertext=excluded.ciphertext",
                         (key, time.time() + CACHE_SECONDS, encrypted))
            conn.execute("DELETE FROM encrypted_ai_cache WHERE expires <= ?", (time.time(),))
            conn.execute("DELETE FROM encrypted_ai_cache WHERE id NOT IN "
                         "(SELECT id FROM encrypted_ai_cache ORDER BY expires DESC LIMIT ?)", (MAX_ITEMS,))
        return True
    except (sqlite3.Error, TypeError, ValueError):
        return False
