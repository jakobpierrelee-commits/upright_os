import pathlib
import sys

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from clean_sse import apply_sse_headers, make_sse_emitter


class _HeaderSink:
    def __init__(self) -> None:
        self.response_code = None
        self.headers: list[tuple[str, str]] = []
        self.ended = False

    def send_response(self, code: int) -> None:
        self.response_code = code

    def send_header(self, key: str, value: str) -> None:
        self.headers.append((key, value))

    def end_headers(self) -> None:
        self.ended = True


class _WFileOk:
    def __init__(self) -> None:
        self.buf: list[bytes] = []
        self.flushed = 0

    def write(self, blob: bytes) -> None:
        self.buf.append(blob)

    def flush(self) -> None:
        self.flushed += 1


class _WFileFail:
    def write(self, blob: bytes) -> None:
        raise RuntimeError("disconnected")

    def flush(self) -> None:
        raise RuntimeError("disconnected")


def test_apply_sse_headers_sets_expected_values() -> None:
    sink = _HeaderSink()
    apply_sse_headers(
        send_response=sink.send_response,
        send_header=sink.send_header,
        end_headers=sink.end_headers,
    )
    assert sink.response_code == 200
    keys = [k for (k, _) in sink.headers]
    assert "Content-Type" in keys
    assert "Cache-Control" in keys
    assert "Connection" in keys
    assert sink.ended is True


def test_make_sse_emitter_writes_blob() -> None:
    wf = _WFileOk()
    emit = make_sse_emitter(wfile=wf)
    emit("start", {"ok": True})
    assert len(wf.buf) == 1
    assert b"event: start" in wf.buf[0]
    assert wf.flushed == 1


def test_make_sse_emitter_honors_disconnected() -> None:
    wf = _WFileOk()
    emit = make_sse_emitter(wfile=wf, is_disconnected=lambda: True)
    emit("start", {"ok": True})
    assert len(wf.buf) == 0
    assert wf.flushed == 0


def test_make_sse_emitter_calls_on_write_error() -> None:
    called = {"n": 0}

    def _on_err() -> None:
        called["n"] += 1

    emit = make_sse_emitter(wfile=_WFileFail(), on_write_error=_on_err)
    emit("start", {"ok": True})
    assert called["n"] == 1
