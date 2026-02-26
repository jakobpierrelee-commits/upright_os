"""
Auth Manager - User authentication and OpenAI key management.

Extracted from server.py to domains/session_traceability/
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import pathlib
import secrets
import sqlite3
import ssl
import threading
import time
from typing import Any, Dict, Optional
from urllib import error as urlerror
from urllib import request as urlrequest

try:
    import certifi
except Exception:
    certifi = None


class AuthManager:
    def __init__(self, repo_root: pathlib.Path) -> None:
        self.repo_root = repo_root
        self.db_path = repo_root / "app" / "bridge" / "upright_auth.db"
        self.secret_path = repo_root / "app" / "bridge" / ".auth_secret"
        self.base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.openai_verify_timeout_s = float(
            os.environ.get("OPENAI_KEY_VERIFY_TIMEOUT_S", "10")
        )
        self.ssl_context = self._build_ssl_context()
        self._lock = threading.Lock()
        self._secret = self._load_or_create_secret()
        self._init_db()

    @staticmethod
    def _build_ssl_context() -> ssl.SSLContext:
        ca_bundle = os.environ.get("OPENAI_CA_BUNDLE", "").strip()
        if ca_bundle:
            return ssl.create_default_context(cafile=ca_bundle)
        if certifi is not None:
            return ssl.create_default_context(cafile=certifi.where())
        return ssl.create_default_context()

    def _load_or_create_secret(self) -> bytes:
        env = os.environ.get("UPRIGHT_AUTH_SECRET", "").strip()
        if env:
            return env.encode("utf-8")
        if self.secret_path.exists():
            return self.secret_path.read_bytes()
        self.secret_path.parent.mkdir(parents=True, exist_ok=True)
        val = secrets.token_urlsafe(48).encode("utf-8")
        self.secret_path.write_bytes(val)
        try:
            os.chmod(self.secret_path, 0o600)
        except Exception:
            pass
        return val

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        return con

    def _init_db(self) -> None:
        with self._connect() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  email TEXT UNIQUE NOT NULL,
                  pw_salt BLOB NOT NULL,
                  pw_hash BLOB NOT NULL,
                  created_at REAL NOT NULL
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                  token_hash TEXT PRIMARY KEY,
                  user_id INTEGER NOT NULL,
                  created_at REAL NOT NULL,
                  expires_at REAL NOT NULL,
                  FOREIGN KEY(user_id) REFERENCES users(id)
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS user_openai (
                  user_id INTEGER PRIMARY KEY,
                  api_key_cipher TEXT NOT NULL,
                  model TEXT NOT NULL,
                  updated_at REAL NOT NULL,
                  FOREIGN KEY(user_id) REFERENCES users(id)
                )
                """
            )
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS password_resets (
                  token_hash TEXT PRIMARY KEY,
                  user_id INTEGER NOT NULL,
                  created_at REAL NOT NULL,
                  expires_at REAL NOT NULL,
                  used_at REAL,
                  FOREIGN KEY(user_id) REFERENCES users(id)
                )
                """
            )
            con.commit()

    @staticmethod
    def _normalize_email(email: str) -> str:
        return email.strip().lower()

    def _hash_password(self, password: str, salt: bytes) -> bytes:
        return hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, 200_000, dklen=32
        )

    def _hash_token(self, token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _derive_enc_key(self) -> bytes:
        return hashlib.pbkdf2_hmac(
            "sha256", self._secret, b"upright-openai-key", 120_000, dklen=32
        )

    def _encrypt(self, plain: str) -> str:
        key = self._derive_enc_key()
        p = plain.encode("utf-8")
        out = bytes([p[i] ^ key[i % len(key)] for i in range(len(p))])
        return base64.b64encode(out).decode("ascii")

    def _decrypt(self, cipher_b64: str) -> str:
        key = self._derive_enc_key()
        b = base64.b64decode(cipher_b64.encode("ascii"))
        out = bytes([b[i] ^ key[i % len(key)] for i in range(len(b))])
        return out.decode("utf-8")

    def register(self, email: str, password: str) -> Dict[str, Any]:
        em = self._normalize_email(email)
        if not em or "@" not in em:
            raise RuntimeError("invalid_email")
        if len(password) < 8:
            raise RuntimeError("weak_password")
        salt = secrets.token_bytes(16)
        pwh = self._hash_password(password, salt)
        now = time.time()
        with self._lock, self._connect() as con:
            try:
                con.execute(
                    "INSERT INTO users(email,pw_salt,pw_hash,created_at) VALUES(?,?,?,?)",
                    (em, salt, pwh, now),
                )
                con.commit()
            except sqlite3.IntegrityError as exc:
                raise RuntimeError("email_exists") from exc
        return self.login(email, password)

    def login(self, email: str, password: str) -> Dict[str, Any]:
        em = self._normalize_email(email)
        with self._lock, self._connect() as con:
            row = con.execute(
                "SELECT id,email,pw_salt,pw_hash FROM users WHERE email=?", (em,)
            ).fetchone()
            if not row:
                raise RuntimeError("invalid_credentials")
            calc = self._hash_password(password, row["pw_salt"])
            if not hmac.compare_digest(calc, row["pw_hash"]):
                raise RuntimeError("invalid_credentials")
            token = secrets.token_urlsafe(32)
            token_hash = self._hash_token(token)
            now = time.time()
            exp = now + 60 * 60 * 24 * 14
            con.execute(
                "INSERT OR REPLACE INTO sessions(token_hash,user_id,created_at,expires_at) VALUES(?,?,?,?)",
                (token_hash, row["id"], now, exp),
            )
            con.commit()
            return {
                "session_token": token,
                "user": {"id": row["id"], "email": row["email"]},
            }

    def me(self, token: Optional[str]) -> Optional[Dict[str, Any]]:
        if not token:
            return None
        tokh = self._hash_token(token)
        now = time.time()
        with self._lock, self._connect() as con:
            row = con.execute(
                """
                SELECT u.id AS id, u.email AS email, s.expires_at AS expires_at
                FROM sessions s
                JOIN users u ON u.id=s.user_id
                WHERE s.token_hash=?
                """,
                (tokh,),
            ).fetchone()
            if not row:
                return None
            if float(row["expires_at"]) < now:
                con.execute("DELETE FROM sessions WHERE token_hash=?", (tokh,))
                con.commit()
                return None
            krow = con.execute(
                "SELECT model FROM user_openai WHERE user_id=?", (row["id"],)
            ).fetchone()
            return {
                "id": int(row["id"]),
                "email": str(row["email"]),
                "openai_configured": bool(krow),
                "openai_model": (krow["model"] if krow else None),
            }

    def logout(self, token: Optional[str]) -> None:
        if not token:
            return
        tokh = self._hash_token(token)
        with self._lock, self._connect() as con:
            con.execute("DELETE FROM sessions WHERE token_hash=?", (tokh,))
            con.commit()

    def set_openai_key(
        self, user_id: int, api_key: str, model: Optional[str]
    ) -> Dict[str, Any]:
        k = api_key.strip()
        if not k.startswith("sk-"):
            raise RuntimeError("invalid_openai_key")
        if os.environ.get("UPRIGHT_SKIP_OPENAI_KEY_VERIFY", "").strip().lower() not in {
            "1",
            "true",
            "yes",
            "on",
        }:
            req = urlrequest.Request(
                f"{self.base_url.rstrip('/')}/models?limit=1",
                method="GET",
                headers={"Authorization": f"Bearer {k}"},
            )
            try:
                with urlrequest.urlopen(
                    req, timeout=self.openai_verify_timeout_s, context=self.ssl_context
                ) as _:
                    pass
            except urlerror.HTTPError as exc:
                if exc.code in {401, 403}:
                    raise RuntimeError("invalid_openai_key") from exc
                if exc.code == 429:
                    # Rate-limit means the key was accepted by upstream auth.
                    pass
                else:
                    raise RuntimeError(
                        f"openai_key_verification_failed:{exc.code}"
                    ) from exc
            except Exception as exc:
                emsg = str(exc)
                if "CERTIFICATE_VERIFY_FAILED" in emsg:
                    raise RuntimeError("openai_tls_cert_verify_failed") from exc
                raise RuntimeError("openai_key_verification_failed:network") from exc
        m = (model or "gpt-5-codex").strip() or "gpt-5-codex"
        cipher = self._encrypt(k)
        now = time.time()
        with self._lock, self._connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO user_openai(user_id,api_key_cipher,model,updated_at) VALUES(?,?,?,?)",
                (user_id, cipher, m, now),
            )
            con.commit()
        return {"configured": True, "model": m}

    def clear_openai_key(self, user_id: int) -> Dict[str, Any]:
        with self._lock, self._connect() as con:
            con.execute("DELETE FROM user_openai WHERE user_id=?", (user_id,))
            con.commit()
        return {"configured": False, "model": None}

    def get_openai_key(self, user_id: int) -> Optional[Dict[str, Any]]:
        with self._lock, self._connect() as con:
            row = con.execute(
                "SELECT api_key_cipher,model FROM user_openai WHERE user_id=?",
                (user_id,),
            ).fetchone()
            if not row:
                return None
            return {
                "api_key": self._decrypt(row["api_key_cipher"]),
                "model": row["model"],
            }

    def request_password_reset(self, email: str) -> Dict[str, Any]:
        em = self._normalize_email(email)
        now = time.time()
        with self._lock, self._connect() as con:
            user = con.execute("SELECT id FROM users WHERE email=?", (em,)).fetchone()
            # Do not reveal account existence.
            if not user:
                return {
                    "accepted": True,
                    "delivery": "local_token",
                    "reset_token": None,
                    "expires_in_s": 900,
                }

            token = secrets.token_urlsafe(24)
            tokh = self._hash_token(token)
            exp = now + 900
            con.execute(
                "DELETE FROM password_resets WHERE user_id=?", (int(user["id"]),)
            )
            con.execute(
                "INSERT OR REPLACE INTO password_resets(token_hash,user_id,created_at,expires_at,used_at) VALUES(?,?,?,?,NULL)",
                (tokh, int(user["id"]), now, exp),
            )
            con.commit()
            return {
                "accepted": True,
                "delivery": "local_token",
                "reset_token": token,
                "expires_in_s": 900,
            }

    def reset_password(
        self, email: str, token: str, new_password: str
    ) -> Dict[str, Any]:
        em = self._normalize_email(email)
        tok = token.strip()
        if len(new_password) < 8:
            raise RuntimeError("weak_password")
        if not tok:
            raise RuntimeError("invalid_reset_token")

        tokh = self._hash_token(tok)
        now = time.time()
        salt = secrets.token_bytes(16)
        pwh = self._hash_password(new_password, salt)

        with self._lock, self._connect() as con:
            user = con.execute("SELECT id FROM users WHERE email=?", (em,)).fetchone()
            if not user:
                raise RuntimeError("invalid_reset_token")
            uid = int(user["id"])

            row = con.execute(
                """
                SELECT token_hash FROM password_resets
                WHERE token_hash=? AND user_id=? AND used_at IS NULL AND expires_at>=?
                """,
                (tokh, uid, now),
            ).fetchone()
            if not row:
                raise RuntimeError("invalid_reset_token")

            con.execute(
                "UPDATE users SET pw_salt=?, pw_hash=? WHERE id=?", (salt, pwh, uid)
            )
            con.execute(
                "UPDATE password_resets SET used_at=? WHERE token_hash=?", (now, tokh)
            )
            con.execute("DELETE FROM sessions WHERE user_id=?", (uid,))
            con.commit()
        return {"ok": True}
