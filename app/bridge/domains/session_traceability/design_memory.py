"""
Design Memory Store - Design iteration memory with observations and ratings.

Extracted from server.py to domains/session_traceability/
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import secrets
import threading
import time
from typing import Any, Dict, Optional


class DesignMemoryStore:
    """Durable design iteration memory: auto observations + operator ratings."""

    def __init__(self, repo_root: pathlib.Path, max_entries: int = 600) -> None:
        self.path = repo_root / "app" / "bridge" / "design_memory.json"
        self.max_entries = max(50, int(max_entries))
        self._lock = threading.Lock()
        self._entries: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            entries = raw.get("entries", []) if isinstance(raw, dict) else []
            if not isinstance(entries, list):
                entries = []
            parsed: Dict[str, Dict[str, Any]] = {}
            for node in entries:
                if not isinstance(node, dict):
                    continue
                design_id = str(node.get("design_id", "")).strip()
                if not design_id:
                    continue
                parsed[design_id] = dict(node)
            self._entries = parsed
        except Exception:
            self._entries = {}

    def _save_locked(self) -> None:
        rows = sorted(
            self._entries.values(),
            key=lambda r: float(r.get("updated_at", 0.0) or 0.0),
            reverse=True,
        )[: self.max_entries]
        payload = {
            "version": 1,
            "updated_at": time.time(),
            "entries": rows,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
        os.replace(tmp, self.path)

    @staticmethod
    def _normalize_obs(observation: Dict[str, Any]) -> Dict[str, str]:
        keys = [
            "runtime_version",
            "tune_version",
            "ident",
            "hash",
            "sketch_hash",
            "sketch_revision",
            "profile_id",
            "profile_label",
            "fqbn",
            "port",
            "board_id",
            "test_type",
        ]
        out: Dict[str, str] = {}
        for key in keys:
            val = str(observation.get(key, "") or "").strip()
            if val:
                out[key] = val
        return out

    @staticmethod
    def _design_id_from_obs(obs: Dict[str, str]) -> str:
        material = "|".join(
            [
                obs.get("runtime_version", ""),
                obs.get("tune_version", ""),
                obs.get("ident", ""),
                obs.get("hash", ""),
                obs.get("sketch_hash", ""),
                obs.get("profile_id", ""),
                obs.get("fqbn", ""),
            ]
        )
        if not material.replace("|", "").strip():
            material = f"unknown|{time.time():.6f}|{secrets.token_hex(6)}"
        return "design_" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]

    @staticmethod
    def _event_score_raw(node: Dict[str, Any]) -> float:
        success = int(node.get("success_count", 0) or 0)
        failure = int(node.get("failure_count", 0) or 0)
        up = int(node.get("user_positive", 0) or 0)
        down = int(node.get("user_negative", 0) or 0)
        return float((success * 3) + (up * 5) - (failure * 2) - (down * 6))

    @staticmethod
    def _event_score_norm(node: Dict[str, Any]) -> float:
        raw = DesignMemoryStore._event_score_raw(node)
        return max(0.0, min(100.0, 50.0 + (raw * 5.0)))

    @staticmethod
    def _evidence_score(node: Dict[str, Any]) -> float:
        evidence = node.get("evidence")
        if not isinstance(evidence, dict):
            return 0.0
        checks = evidence.get("checks")
        if not isinstance(checks, dict):
            return 0.0

        weights: Dict[str, float] = {
            "upload_ok": 25.0,
            "reconnect_ok": 20.0,
            "preflight_ok": 15.0,
            "prearm_ok": 15.0,
            "telemetry_feed_ok": 10.0,
            "no_fault": 10.0,
            "safe_mode_ok": 5.0,
        }
        score = 0.0
        for key, weight in weights.items():
            if bool(checks.get(key, False)):
                score += weight
        return max(0.0, min(100.0, score))

    @staticmethod
    def _balance_score(node: Dict[str, Any]) -> float:
        evidence = node.get("evidence")
        if not isinstance(evidence, dict):
            return 50.0
        sources = evidence.get("sources")
        if not isinstance(sources, dict):
            return 50.0

        status_snapshot = sources.get("status_snapshot")
        s = status_snapshot if isinstance(status_snapshot, dict) else {}

        def _f(*keys: str) -> Optional[float]:
            for k in keys:
                v = s.get(k)
                try:
                    return float(v)
                except Exception:
                    continue
            return None

        ang = _f("ang")
        out_sat_flag = str(s.get("output_saturated", "")).strip().lower()
        out_sat = out_sat_flag in {"1", "true", "yes"}
        u_unsat = _f("pid_u_unsat")
        u_sat = _f("pid_u_sat", "out")
        loop_hz = _f("loop_hz", "loopHz", "hz")
        if loop_hz is None:
            period_us = _f("period_us", "loop_period_us")
            if period_us is not None and period_us > 0:
                loop_hz = 1_000_000.0 / period_us
        overrun = str(s.get("overrun", "0")).strip() not in {"", "0", "false", "False"}
        fault = str(s.get("fault", "")).strip() not in {"", "0"}

        score = 100.0
        if fault:
            score -= 25.0
        if ang is None:
            score -= 20.0
        else:
            a = abs(float(ang))
            if a > 12.0:
                score -= 35.0
            elif a > 6.0:
                score -= 22.0
            elif a > 3.0:
                score -= 12.0
            elif a > 1.5:
                score -= 6.0
        if out_sat:
            score -= 10.0
        if u_unsat is not None and u_sat is not None and abs(u_unsat - u_sat) >= 6.0:
            score -= 8.0
        if overrun:
            score -= 12.0
        if loop_hz is None:
            score -= 15.0
        elif loop_hz < 20.0:
            score -= 20.0
        elif loop_hz < 40.0:
            score -= 10.0

        ow = sources.get("overwatch_score_pct")
        try:
            owf = float(ow)
            if 0.0 <= owf <= 100.0:
                score = (score * 0.6) + (owf * 0.4)
        except Exception:
            pass

        return round(max(0.0, min(100.0, score)), 2)

    @staticmethod
    def _score(node: Dict[str, Any]) -> float:
        balance = DesignMemoryStore._balance_score(node)
        event_norm = DesignMemoryStore._event_score_norm(node)
        evidence = DesignMemoryStore._evidence_score(node)
        return round((balance * 0.5) + (evidence * 0.3) + (event_norm * 0.2), 2)

    def report(
        self,
        *,
        session_key: str,
        observation: Dict[str, Any],
        success: bool,
        source: str,
        note: str = "",
    ) -> Dict[str, Any]:
        session = str(session_key or "global").strip() or "global"
        obs = self._normalize_obs(observation if isinstance(observation, dict) else {})
        design_id = self._design_id_from_obs(obs)
        now = time.time()
        with self._lock:
            row = self._entries.get(design_id)
            if not isinstance(row, dict):
                row = {
                    "design_id": design_id,
                    "created_at": now,
                    "updated_at": now,
                    "last_session_key": session,
                    "sources": [],
                    "success_count": 0,
                    "failure_count": 0,
                    "user_positive": 0,
                    "user_negative": 0,
                    "notes": [],
                }
                self._entries[design_id] = row
            for k, v in obs.items():
                row[k] = v
            evidence = observation.get("evidence")
            if isinstance(evidence, dict):
                row["evidence"] = dict(evidence)
            row["updated_at"] = now
            row["last_session_key"] = session
            src = str(source or "unknown").strip() or "unknown"
            sources = row.get("sources")
            if not isinstance(sources, list):
                sources = []
            if src not in sources:
                sources.append(src)
            row["sources"] = sources[-12:]
            if success:
                row["success_count"] = int(row.get("success_count", 0) or 0) + 1
            else:
                row["failure_count"] = int(row.get("failure_count", 0) or 0) + 1
            if note:
                notes = row.get("notes")
                if not isinstance(notes, list):
                    notes = []
                notes.append(
                    {
                        "at": now,
                        "source": src,
                        "text": str(note)[:320],
                    }
                )
                row["notes"] = notes[-16:]
            row["event_score_raw"] = self._event_score_raw(row)
            row["event_score"] = self._event_score_norm(row)
            row["evidence_score"] = self._evidence_score(row)
            row["balance_score"] = self._balance_score(row)
            row["score"] = self._score(row)
            self._save_locked()
            return dict(row)

    def rate(
        self,
        *,
        design_id: str,
        rating: str,
        note: str = "",
        source: str = "user_input",
        session_key: str = "global",
    ) -> Dict[str, Any]:
        did = str(design_id or "").strip()
        if not did:
            raise RuntimeError("design_id_required")
        r = str(rating or "").strip().lower()
        if r not in {"positive", "negative"}:
            raise RuntimeError("rating_invalid")
        now = time.time()
        with self._lock:
            row = self._entries.get(did)
            if not isinstance(row, dict):
                raise RuntimeError("design_not_found")
            if r == "positive":
                row["user_positive"] = int(row.get("user_positive", 0) or 0) + 1
            else:
                row["user_negative"] = int(row.get("user_negative", 0) or 0) + 1
            row["updated_at"] = now
            row["last_session_key"] = str(session_key or "global").strip() or "global"
            if note:
                notes = row.get("notes")
                if not isinstance(notes, list):
                    notes = []
                notes.append(
                    {
                        "at": now,
                        "source": str(source or "user_input"),
                        "text": str(note)[:320],
                    }
                )
                row["notes"] = notes[-16:]
            row["event_score_raw"] = self._event_score_raw(row)
            row["event_score"] = self._event_score_norm(row)
            row["evidence_score"] = self._evidence_score(row)
            row["balance_score"] = self._balance_score(row)
            row["score"] = self._score(row)
            self._save_locked()
            return dict(row)

    def best(
        self,
        *,
        session_key: str = "",
        profile_id: str = "",
    ) -> Optional[Dict[str, Any]]:
        session = str(session_key or "").strip()
        pid = str(profile_id or "").strip()
        with self._lock:
            rows = list(self._entries.values())
        if pid:
            rows = [r for r in rows if str(r.get("profile_id", "")).strip() == pid]
        if session:
            scoped = [
                r for r in rows if str(r.get("last_session_key", "")).strip() == session
            ]
            if scoped:
                rows = scoped
        if not rows:
            return None
        rows.sort(
            key=lambda r: (
                float(r.get("score", self._score(r)) or 0.0),
                float(r.get("updated_at", 0.0) or 0.0),
            ),
            reverse=True,
        )
        top = dict(rows[0])
        top["event_score_raw"] = float(
            top.get("event_score_raw", self._event_score_raw(top)) or 0.0
        )
        top["event_score"] = float(
            top.get("event_score", self._event_score_norm(top)) or 0.0
        )
        top["evidence_score"] = float(
            top.get("evidence_score", self._evidence_score(top)) or 0.0
        )
        top["balance_score"] = float(
            top.get("balance_score", self._balance_score(top)) or 0.0
        )
        top["score"] = float(top.get("score", self._score(top)) or 0.0)
        return top

    def list_recent(self, *, limit: int = 30) -> list:
        take = max(1, min(int(limit), self.max_entries))
        with self._lock:
            rows = sorted(
                self._entries.values(),
                key=lambda r: float(r.get("updated_at", 0.0) or 0.0),
                reverse=True,
            )[:take]
        out: list = []
        for row in rows:
            node = dict(row)
            node["event_score_raw"] = float(
                node.get("event_score_raw", self._event_score_raw(node)) or 0.0
            )
            node["event_score"] = float(
                node.get("event_score", self._event_score_norm(node)) or 0.0
            )
            node["evidence_score"] = float(
                node.get("evidence_score", self._evidence_score(node)) or 0.0
            )
            node["balance_score"] = float(
                node.get("balance_score", self._balance_score(node)) or 0.0
            )
            node["score"] = float(node.get("score", self._score(node)) or 0.0)
            out.append(node)
        return out
