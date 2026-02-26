"""
Commissioning Manager - Hardware commissioning workflow management.

Extracted from server.py to domains/tuning_intelligence/
"""

from __future__ import annotations

import pathlib
import subprocess
import threading
import time
from typing import Any, Dict, Optional


class CommissioningManager:
    def __init__(
        self, repo_root: pathlib.Path, default_port: str, default_baud: int
    ) -> None:
        self.repo_root = repo_root
        self.default_port = default_port
        self.default_baud = default_baud
        self.default_config = repo_root / "tests" / "commissioning_config.json"
        self.default_out_dir = repo_root / "tests" / "results"
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._state = "idle"
        self._started_at: Optional[float] = None
        self._finished_at: Optional[float] = None
        self._returncode: Optional[int] = None
        self._log: list[str] = []
        self._last_cmd: list[str] = []

    def _set(self, **kwargs: Any) -> None:
        with self._lock:
            for k, v in kwargs.items():
                setattr(self, k, v)

    def _append_log(self, line: str) -> None:
        with self._lock:
            self._log.append(line)
            self._log = self._log[-500:]

    def run(
        self,
        *,
        port: Optional[str] = None,
        baud: Optional[int] = None,
        config: Optional[str] = None,
        out_dir: Optional[str] = None,
        auto_prompts: bool = True,
    ) -> Dict[str, Any]:
        with self._lock:
            if self._running:
                raise RuntimeError("commissioning_running")
            self._running = True
            self._state = "running"
            self._started_at = time.time()
            self._finished_at = None
            self._returncode = None
            self._log = []

        p = port or self.default_port
        b = str(baud or self.default_baud)
        c = config or str(self.default_config)
        o = out_dir or str(self.default_out_dir)
        cmd = [
            "python3",
            str(self.repo_root / "tools" / "commissioning_runner.py"),
            "--port",
            p,
            "--baud",
            b,
            "--config",
            c,
            "--out-dir",
            o,
        ]
        if auto_prompts:
            cmd.append("--auto-prompts")
        self._set(_last_cmd=cmd)

        def worker() -> None:
            rc = -1
            try:
                proc = subprocess.Popen(
                    cmd,
                    cwd=str(self.repo_root),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                assert proc.stdout is not None
                for ln in proc.stdout:
                    self._append_log(ln.rstrip())
                rc = proc.wait()
            except Exception as exc:
                self._append_log(f"ERROR: {exc}")
            finally:
                self._set(
                    _running=False,
                    _state="passed" if rc == 0 else "failed",
                    _finished_at=time.time(),
                    _returncode=rc,
                )

        t = threading.Thread(target=worker, daemon=True)
        self._set(_thread=t)
        t.start()
        return self.status()

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "state": self._state,
                "running": self._running,
                "started_at": self._started_at,
                "finished_at": self._finished_at,
                "returncode": self._returncode,
                "last_cmd": self._last_cmd,
                "log_tail": self._log[-120:],
            }

    def artifacts(self, out_dir: Optional[str] = None) -> Dict[str, Any]:
        target = pathlib.Path(out_dir) if out_dir else self.default_out_dir
        metrics = sorted(
            target.glob("metrics_*.json"), key=lambda p: p.stat().st_mtime, reverse=True
        )
        runs = sorted(
            target.glob("run_*.csv"), key=lambda p: p.stat().st_mtime, reverse=True
        )
        return {
            "out_dir": str(target),
            "latest_metrics": str(metrics[0]) if metrics else None,
            "latest_run": str(runs[0]) if runs else None,
            "metrics": [str(p) for p in metrics[:20]],
            "runs": [str(p) for p in runs[:20]],
        }
