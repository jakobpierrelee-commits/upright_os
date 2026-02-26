from __future__ import annotations

import json
from typing import Any, Callable, Dict, Optional


def apply_sse_headers(
    *,
    send_response: Callable[[int], Any],
    send_header: Callable[[str, str], Any],
    end_headers: Callable[[], Any],
) -> None:
    send_response(200)
    send_header("Content-Type", "text/event-stream")
    send_header("Cache-Control", "no-cache")
    send_header("Connection", "keep-alive")
    send_header("Access-Control-Allow-Origin", "*")
    send_header(
        "Access-Control-Allow-Headers", "Content-Type, Authorization, X-Session-Token"
    )
    send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
    end_headers()


def make_sse_emitter(
    *,
    wfile: Any,
    is_disconnected: Optional[Callable[[], bool]] = None,
    on_write_error: Optional[Callable[[], Any]] = None,
) -> Callable[[str, Dict[str, Any]], None]:
    def _emit(name: str, payload_obj: Dict[str, Any]) -> None:
        if is_disconnected is not None and is_disconnected():
            return
        blob = (
            f"event: {name}\ndata: {json.dumps(payload_obj, ensure_ascii=True)}\n\n"
        ).encode("utf-8")
        try:
            wfile.write(blob)
            wfile.flush()
        except Exception:
            if on_write_error is not None:
                on_write_error()

    return _emit
