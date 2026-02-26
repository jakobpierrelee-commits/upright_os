"""
AI Manager - OpenAI/Codex chat and thread management.

Extracted from server.py to domains/ai_agent/
"""

from __future__ import annotations

import json
import os
import pathlib
import secrets
import select
import shutil
import ssl
import subprocess
import threading
import time
from typing import Any, Callable, Dict, Optional
from urllib import request as urlrequest
from urllib import error as urlerror

try:
    import certifi
except ImportError:
    certifi = None


class AIManager:
    def __init__(self, repo_root: pathlib.Path) -> None:
        self.repo_root = repo_root
        self.default_api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        self.default_model = os.environ.get("OPENAI_MODEL", "gpt-5-codex")
        self.base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.ssl_context = self._build_ssl_context()
        self.state_path = repo_root / "app" / "bridge" / "ai_threads.json"
        self.state_backup_dir = repo_root / "app" / "bridge" / "ai_threads_backups"
        self.max_state_backups = 8
        self._lock = threading.Lock()
        self._threads: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._active_thread: Dict[str, str] = {}
        self._load_state()

    def _load_state_from_raw(self, raw: Any) -> bool:
        if not isinstance(raw, dict):
            return False
        threads = raw.get("threads")
        active = raw.get("active_thread")
        if not isinstance(threads, dict):
            return False

        clean_threads: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for skey, bucket in threads.items():
            if not isinstance(skey, str) or not isinstance(bucket, dict):
                continue
            clean_bucket: Dict[str, Dict[str, Any]] = {}
            for tid, entry in bucket.items():
                if not isinstance(tid, str) or not isinstance(entry, dict):
                    continue
                msgs = entry.get("messages", [])
                if not isinstance(msgs, list):
                    msgs = []
                clean_msgs = []
                for m in msgs[-120:]:
                    if not isinstance(m, dict):
                        continue
                    role = str(m.get("role", "assistant"))
                    text = str(m.get("text", ""))
                    ts = float(m.get("ts", time.time()) or time.time())
                    clean_msgs.append({"ts": ts, "role": role, "text": text})
                clean_bucket[tid] = {
                    "id": tid,
                    "title": str(entry.get("title", "New Chat") or "New Chat"),
                    "created_at": float(
                        entry.get("created_at", time.time()) or time.time()
                    ),
                    "updated_at": float(
                        entry.get("updated_at", time.time()) or time.time()
                    ),
                    "messages": clean_msgs,
                }
            if clean_bucket:
                clean_threads[skey] = clean_bucket

        clean_active: Dict[str, str] = {}
        if isinstance(active, dict):
            clean_active = {
                str(k): str(v)
                for k, v in active.items()
                if isinstance(k, str) and isinstance(v, str)
            }

        self._threads = clean_threads
        self._active_thread = clean_active
        return True

    def _load_state_file(self, path: pathlib.Path) -> bool:
        try:
            if not path.exists():
                return False
            raw = json.loads(path.read_text(encoding="utf-8"))
            return self._load_state_from_raw(raw)
        except Exception:
            return False

    def _state_backups(self) -> list[pathlib.Path]:
        if not self.state_backup_dir.exists():
            return []
        files = sorted(
            self.state_backup_dir.glob("ai_threads_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        return files

    def _load_state(self) -> None:
        try:
            if self._load_state_file(self.state_path):
                return
            for backup in self._state_backups():
                if self._load_state_file(backup):
                    # Restore primary from latest healthy backup for next boot.
                    self._save_state_locked()
                    return
        except Exception:
            # Keep chat available even if persisted state is malformed.
            return

    def _save_state_locked(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_backup_dir.mkdir(parents=True, exist_ok=True)
        payload = {"threads": self._threads, "active_thread": self._active_thread}
        blob = json.dumps(payload, ensure_ascii=True)
        tmp_path = self.state_path.with_suffix(".tmp")
        tmp_path.write_text(blob, encoding="utf-8")

        if self.state_path.exists():
            stamp = int(time.time() * 1000)
            backup_path = self.state_backup_dir / f"ai_threads_{stamp}.json"
            try:
                shutil.copy2(self.state_path, backup_path)
            except Exception:
                pass

        os.replace(tmp_path, self.state_path)

        backups = self._state_backups()
        for stale in backups[self.max_state_backups :]:
            try:
                stale.unlink(missing_ok=True)
            except Exception:
                pass

    @staticmethod
    def _build_ssl_context() -> ssl.SSLContext:
        # Allow explicit override if the host needs a custom CA bundle.
        ca_bundle = os.environ.get("OPENAI_CA_BUNDLE", "").strip()
        if ca_bundle:
            return ssl.create_default_context(cafile=ca_bundle)
        if certifi is not None:
            return ssl.create_default_context(cafile=certifi.where())
        return ssl.create_default_context()

    def _thread_title(self, user_text: str) -> str:
        t = " ".join(user_text.strip().split())
        if not t:
            return "New Chat"
        return t[:44]

    def _ensure_thread_locked(
        self, session_key: str, thread_id: Optional[str] = None
    ) -> tuple[str, Dict[str, Any]]:
        bucket = self._threads.setdefault(session_key, {})
        active = self._active_thread.get(session_key)
        chosen = thread_id or active
        if chosen and chosen in bucket:
            self._active_thread[session_key] = chosen
            return chosen, bucket[chosen]
        if thread_id and thread_id not in bucket:
            # Explicit thread selection must never silently fall back; callers
            # rely on this to detect stale/missing thread IDs.
            raise RuntimeError("thread_not_found")

        if not chosen and bucket:
            picked = max(
                bucket.values(), key=lambda t: float(t.get("updated_at") or 0.0)
            )
            tid = str(picked["id"])
            self._active_thread[session_key] = tid
            return tid, picked

        new_id = secrets.token_urlsafe(8)
        now = time.time()
        entry = {
            "id": new_id,
            "title": "New Chat",
            "created_at": now,
            "updated_at": now,
            "messages": [],
        }
        bucket[new_id] = entry
        self._active_thread[session_key] = new_id
        self._save_state_locked()
        return new_id, entry

    def _append(
        self, session_key: str, role: str, text: str, *, thread_id: Optional[str] = None
    ) -> str:
        with self._lock:
            tid, thread = self._ensure_thread_locked(session_key, thread_id)
            msgs = thread["messages"]
            msgs.append({"ts": time.time(), "role": role, "text": text})
            if len(msgs) > 120:
                del msgs[: len(msgs) - 120]
            thread["updated_at"] = time.time()
            if role == "user" and thread.get("title", "New Chat") == "New Chat":
                thread["title"] = self._thread_title(text)
            self._active_thread[session_key] = tid
            self._save_state_locked()
            return tid

    def list_threads(self, session_key: str) -> list[Dict[str, Any]]:
        with self._lock:
            bucket = self._threads.get(session_key, {})
            out: list[Dict[str, Any]] = []
            for thread in bucket.values():
                msgs = thread.get("messages", [])
                preview = msgs[-1]["text"][:96] if msgs else ""
                out.append(
                    {
                        "id": thread["id"],
                        "title": thread.get("title", "New Chat"),
                        "created_at": thread.get("created_at"),
                        "updated_at": thread.get("updated_at"),
                        "message_count": len(msgs),
                        "preview": preview,
                    }
                )
            out.sort(key=lambda t: float(t.get("updated_at") or 0.0), reverse=True)
            return out

    def create_thread(
        self, session_key: str, title: Optional[str] = None
    ) -> Dict[str, Any]:
        with self._lock:
            tid, thread = self._ensure_thread_locked(session_key, None)
            # Ensure a fresh thread even if one already exists/active.
            if thread.get("messages"):
                tid = secrets.token_urlsafe(8)
                now = time.time()
                thread = {
                    "id": tid,
                    "title": (title or "New Chat").strip() or "New Chat",
                    "created_at": now,
                    "updated_at": now,
                    "messages": [],
                }
                self._threads.setdefault(session_key, {})[tid] = thread
                self._active_thread[session_key] = tid
            else:
                if title:
                    thread["title"] = title.strip() or "New Chat"
            self._save_state_locked()
            return {
                "id": thread["id"],
                "title": thread["title"],
                "created_at": thread["created_at"],
                "updated_at": thread["updated_at"],
            }

    def select_thread(self, session_key: str, thread_id: str) -> Dict[str, Any]:
        with self._lock:
            bucket = self._threads.get(session_key, {})
            if thread_id not in bucket:
                raise RuntimeError("thread_not_found")
            self._active_thread[session_key] = thread_id
            self._save_state_locked()
            t = bucket[thread_id]
            return {
                "id": t["id"],
                "title": t["title"],
                "created_at": t["created_at"],
                "updated_at": t["updated_at"],
            }

    def status(
        self, *, configured: bool, model: str, session_key: str
    ) -> Dict[str, Any]:
        with self._lock:
            tid, thread = self._ensure_thread_locked(session_key)
            hlen = len(thread.get("messages", []))
            tcount = len(self._threads.get(session_key, {}))
        return {
            "configured": configured,
            "model": model,
            "history_len": hlen,
            "active_thread_id": tid,
            "thread_count": tcount,
        }

    def history(
        self, session_key: str, thread_id: Optional[str] = None
    ) -> list[Dict[str, Any]]:
        with self._lock:
            tid, thread = self._ensure_thread_locked(session_key, thread_id)
            self._active_thread[session_key] = tid
            return list(thread.get("messages", []))

    @staticmethod
    def _extract_output_text(resp: Dict[str, Any]) -> str:
        out = []
        if isinstance(resp.get("output_text"), str) and resp.get("output_text"):
            out.append(resp["output_text"])
        for item in resp.get("output", []) or []:
            for c in item.get("content", []) or []:
                t = c.get("text")
                if isinstance(t, str) and t:
                    out.append(t)
        return "\n".join([x for x in out if x]).strip()

    def chat(
        self,
        *,
        message: str,
        context: Dict[str, Any],
        session_key: str,
        api_key: str,
        model: str,
        thread_id: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not api_key:
            raise RuntimeError("openai_api_key_missing")
        user_msg = message.strip()
        if not user_msg:
            raise RuntimeError("empty_message")

        context_blob = json.dumps(context, separators=(",", ":"), ensure_ascii=True)
        prompt = system_prompt or (
            "You are Codex for UpRight.os, a robotics tuning copilot. "
            "Be concise, practical, and safe. Never claim actions already executed unless tool output confirms it."
        )

        payload = {
            "model": model,
            "input": [
                {"role": "system", "content": [{"type": "input_text", "text": prompt}]},
                {
                    "role": "system",
                    "content": [
                        {"type": "input_text", "text": f"live_context={context_blob}"}
                    ],
                },
                {"role": "user", "content": [{"type": "input_text", "text": user_msg}]},
            ],
        }
        data = json.dumps(payload).encode("utf-8")
        req = urlrequest.Request(
            f"{self.base_url.rstrip('/')}/responses",
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        try:
            with urlrequest.urlopen(req, timeout=30, context=self.ssl_context) as r:
                raw = r.read().decode("utf-8", errors="replace")
            parsed = json.loads(raw)
        except urlerror.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            raise RuntimeError(f"openai_http_error:{exc.code}:{body}") from exc
        except Exception as exc:
            emsg = str(exc)
            if "CERTIFICATE_VERIFY_FAILED" in emsg:
                raise RuntimeError("openai_tls_cert_verify_failed") from exc
            raise RuntimeError(f"openai_request_failed:{exc}") from exc

        answer = self._extract_output_text(parsed) or "(no output)"
        tid = self._append(session_key, "user", user_msg, thread_id=thread_id)
        self._append(session_key, "assistant", answer, thread_id=tid)
        return {"answer": answer, "raw_id": parsed.get("id"), "thread_id": tid}

    def chat_stream(
        self,
        *,
        message: str,
        context: Dict[str, Any],
        session_key: str,
        api_key: str,
        model: str,
        on_delta: Callable[[str], None],
        thread_id: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not api_key:
            raise RuntimeError("openai_api_key_missing")
        user_msg = message.strip()
        if not user_msg:
            raise RuntimeError("empty_message")

        context_blob = json.dumps(context, separators=(",", ":"), ensure_ascii=True)
        prompt = system_prompt or (
            "You are Codex for UpRight.os, a robotics tuning copilot. "
            "Be concise, practical, and safe. Never claim actions already executed unless tool output confirms it."
        )

        payload = {
            "model": model,
            "stream": True,
            "input": [
                {"role": "system", "content": [{"type": "input_text", "text": prompt}]},
                {
                    "role": "system",
                    "content": [
                        {"type": "input_text", "text": f"live_context={context_blob}"}
                    ],
                },
                {"role": "user", "content": [{"type": "input_text", "text": user_msg}]},
            ],
        }
        data = json.dumps(payload).encode("utf-8")
        req = urlrequest.Request(
            f"{self.base_url.rstrip('/')}/responses",
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )

        chunks: list[str] = []
        raw_id: Optional[str] = None
        completed_response: Optional[Dict[str, Any]] = None
        try:
            with urlrequest.urlopen(req, timeout=90, context=self.ssl_context) as r:
                for raw in r:
                    if not raw:
                        continue
                    line = raw.decode("utf-8", errors="replace").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    payload_txt = line[5:].strip()
                    if not payload_txt or payload_txt == "[DONE]":
                        continue
                    evt = json.loads(payload_txt)
                    et = str(evt.get("type", ""))
                    if et == "response.output_text.delta":
                        delta = str(evt.get("delta", ""))
                        if delta:
                            chunks.append(delta)
                            on_delta(delta)
                    elif et == "response.completed":
                        resp = evt.get("response")
                        if isinstance(resp, dict):
                            completed_response = resp
                            rid = resp.get("id")
                            if isinstance(rid, str) and rid:
                                raw_id = rid
        except urlerror.HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            raise RuntimeError(f"openai_http_error:{exc.code}:{body}") from exc
        except Exception as exc:
            emsg = str(exc)
            if "CERTIFICATE_VERIFY_FAILED" in emsg:
                raise RuntimeError("openai_tls_cert_verify_failed") from exc
            raise RuntimeError(f"openai_request_failed:{exc}") from exc

        answer = "".join(chunks).strip()
        if (not answer) and completed_response:
            answer = self._extract_output_text(completed_response)
        answer = answer or "(no output)"
        tid = self._append(session_key, "user", user_msg, thread_id=thread_id)
        self._append(session_key, "assistant", answer, thread_id=tid)
        return {"answer": answer, "raw_id": raw_id, "thread_id": tid}

    def chat_codex_cli(
        self,
        *,
        message: str,
        context: Dict[str, Any],
        session_key: str,
        model: str,
        thread_id: Optional[str] = None,
        system_prompt: Optional[str] = None,
        timeout_s_override: Optional[int] = None,
    ) -> Dict[str, Any]:
        user_msg = message.strip()
        if not user_msg:
            raise RuntimeError("empty_message")

        selected_model = str(model or "gpt-5-codex").strip() or "gpt-5-codex"
        prompt = system_prompt or (
            "You are Codex for UpRight.os. Be concise, practical, and evidence-driven."
        )
        context_blob = json.dumps(context, ensure_ascii=True, separators=(",", ":"))
        composed = (
            f"{prompt}\n\n"
            f"live_context={context_blob}\n\n"
            f"user_request={user_msg}"
        )

        out_path = (
            pathlib.Path("/tmp") / f"upright-codex-last-{secrets.token_urlsafe(10)}.txt"
        )
        cmd = [
            "codex",
            "exec",
            "--skip-git-repo-check",
            "-C",
            str(self.repo_root),
            "-s",
            "danger-full-access",
            "-c",
            "shell_environment_policy.inherit=all",
            "-m",
            selected_model,
            "--output-last-message",
            str(out_path),
            composed,
        ]
        timeout_s = (
            int(timeout_s_override)
            if isinstance(timeout_s_override, int) and timeout_s_override > 0
            else int(os.environ.get("UPRIGHT_CODEX_EXEC_TIMEOUT_S", "180"))
        )
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=max(30, timeout_s),
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"codex_cli_timeout:{int(max(30, timeout_s))}s") from exc
        except Exception as exc:
            raise RuntimeError(f"codex_cli_failed:{exc}") from exc

        answer = ""
        try:
            if out_path.exists():
                answer = out_path.read_text(encoding="utf-8").strip()
        except Exception:
            answer = ""
        finally:
            try:
                out_path.unlink(missing_ok=True)
            except Exception:
                pass

        if proc.returncode != 0:
            stderr_tail = (proc.stderr or proc.stdout or "").strip()[-480:]
            raise RuntimeError(f"codex_cli_error:{stderr_tail or proc.returncode}")

        answer = answer or "(no output)"
        tid = self._append(session_key, "user", user_msg, thread_id=thread_id)
        self._append(session_key, "assistant", answer, thread_id=tid)
        return {"answer": answer, "thread_id": tid, "provider": "codex_cli"}

    def chat_codex_cli_stream(
        self,
        *,
        message: str,
        context: Dict[str, Any],
        session_key: str,
        model: str,
        on_delta: Callable[[str], None],
        on_progress: Optional[Callable[[str], None]] = None,
        thread_id: Optional[str] = None,
        system_prompt: Optional[str] = None,
        timeout_s_override: Optional[int] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> Dict[str, Any]:
        user_msg = message.strip()
        if not user_msg:
            raise RuntimeError("empty_message")

        selected_model = str(model or "gpt-5-codex").strip() or "gpt-5-codex"
        prompt = system_prompt or (
            "You are Codex for UpRight.os. Be concise, practical, and evidence-driven."
        )
        context_blob = json.dumps(context, ensure_ascii=True, separators=(",", ":"))
        composed = (
            f"{prompt}\n\n"
            f"live_context={context_blob}\n\n"
            f"user_request={user_msg}"
        )

        out_path = (
            pathlib.Path("/tmp") / f"upright-codex-last-{secrets.token_urlsafe(10)}.txt"
        )
        cmd = [
            "codex",
            "exec",
            "--skip-git-repo-check",
            "-C",
            str(self.repo_root),
            "-s",
            "danger-full-access",
            "-c",
            "shell_environment_policy.inherit=all",
            "-m",
            selected_model,
            "--output-last-message",
            str(out_path),
            composed,
        ]
        timeout_s = (
            int(timeout_s_override)
            if isinstance(timeout_s_override, int) and timeout_s_override > 0
            else int(os.environ.get("UPRIGHT_CODEX_EXEC_TIMEOUT_S", "180"))
        )
        max_wait_s = max(30, int(timeout_s))
        start = time.time()
        proc: Optional[subprocess.Popen[str]] = None
        captured_lines: list[str] = []
        capture_answer = False
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    raise RuntimeError("codex_cli_cancelled")
                if (time.time() - start) > max_wait_s:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    raise RuntimeError(f"codex_cli_timeout:{max_wait_s}s")
                if proc.stdout is None:
                    break
                ready, _, _ = select.select([proc.stdout], [], [], 0.2)
                if not ready:
                    continue
                line = proc.stdout.readline()
                if line == "" and proc.poll() is not None:
                    break
                if not line:
                    continue
                raw = line.rstrip("\r\n")
                low = raw.strip().lower()
                if on_progress and raw.strip():
                    on_progress(raw)
                if low == "codex":
                    capture_answer = True
                    continue
                if capture_answer:
                    if low.startswith("tokens used"):
                        capture_answer = False
                        continue
                    if raw.strip():
                        captured_lines.append(raw)
                        on_delta(raw + "\n")

            rc = int(proc.wait(timeout=2))
            if rc != 0:
                stderr_tail = "\n".join(captured_lines[-8:]).strip()[-480:]
                raise RuntimeError(f"codex_cli_error:{stderr_tail or rc}")
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"codex_cli_timeout:{max_wait_s}s") from exc
        except Exception:
            raise
        finally:
            try:
                if proc and proc.poll() is None:
                    proc.kill()
            except Exception:
                pass

        answer = "\n".join(captured_lines).strip()
        try:
            if out_path.exists():
                file_answer = out_path.read_text(encoding="utf-8").strip()
                if file_answer:
                    answer = file_answer
        except Exception:
            pass
        finally:
            try:
                out_path.unlink(missing_ok=True)
            except Exception:
                pass

        answer = answer or "(no output)"
        tid = self._append(session_key, "user", user_msg, thread_id=thread_id)
        self._append(session_key, "assistant", answer, thread_id=tid)
        return {"answer": answer, "thread_id": tid, "provider": "codex_cli"}
