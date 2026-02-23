import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  cleanChatStream,
  cleanFailureDetailFromError,
  cleanFailureKindFromError,
  cleanNewThread,
  cleanSelectThread,
  cleanStatus,
  cleanThreads,
  cleanUploadFile,
  type CleanAttachment,
  type CleanMessage,
  type CleanMode,
  type CleanThread,
} from './cleanApi';

type GlobalStatusLevel = 'ok' | 'warn' | 'fail';

type GlobalStatusEvent = {
  level: GlobalStatusLevel;
  summary: string;
  source: 'codex' | 'chat' | 'refresh';
  ts: number;
};

function updated(ts?: number): string {
  const v = Number(ts ?? 0);
  if (!Number.isFinite(v) || v <= 0) return 'just now';
  const delta = Math.max(0, Math.floor(Date.now() / 1000 - v));
  if (delta < 60) return `${delta}s`;
  if (delta < 3600) return `${Math.floor(delta / 60)}m`;
  if (delta < 86400) return `${Math.floor(delta / 3600)}h`;
  return `${Math.floor(delta / 86400)}d`;
}

export function CodexPanelClean(
  { mode, onGlobalStatus }: { mode: CleanMode; onGlobalStatus?: (evt: GlobalStatusEvent) => void },
): JSX.Element {
  const [apiContractOk, setApiContractOk] = useState(true);
  const [online, setOnline] = useState(false);
  const [model, setModel] = useState('gpt-5-codex');
  const [statusLine, setStatusLine] = useState('Checking Codex...');
  const [history, setHistory] = useState<CleanMessage[]>([]);
  const [threads, setThreads] = useState<CleanThread[]>([]);
  const [threadId, setThreadId] = useState<string | undefined>(undefined);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const [sendStartedAt, setSendStartedAt] = useState<number | null>(null);
  const [sendElapsedS, setSendElapsedS] = useState(0);
  const [streamText, setStreamText] = useState('');
  const abortRef = useRef<AbortController | null>(null);
  const [attachments, setAttachments] = useState<CleanAttachment[]>([]);
  const [dragActive, setDragActive] = useState(false);
  const uploadInputRef = useRef<HTMLInputElement | null>(null);
  const [opsLog, setOpsLog] = useState<Array<{ ts: number; text: string }>>([]);
  const [failureBanner, setFailureBanner] = useState<{ kind: string; detail: string } | null>(null);
  const lastGlobalKeyRef = useRef<string>('');

  const publishGlobalStatus = useCallback((evt: GlobalStatusEvent): void => {
    if (!onGlobalStatus) return;
    const key = `${evt.level}|${evt.source}|${evt.summary}`;
    if (lastGlobalKeyRef.current === key) return;
    lastGlobalKeyRef.current = key;
    onGlobalStatus(evt);
  }, [onGlobalStatus]);

  const classifyFailure = useCallback((errText: string): { kind: string; detail: string } => {
    return {
      kind: cleanFailureKindFromError(errText),
      detail: cleanFailureDetailFromError('generic', errText),
    };
  }, []);

  const pushOpLog = useCallback((text: string): void => {
    setOpsLog((prev) => [{ ts: Date.now(), text }, ...prev].slice(0, 12));
  }, []);

  const refresh = useCallback(async () => {
    try {
      const [st, th] = await Promise.all([cleanStatus(mode), cleanThreads(mode)]);
      const version = Number(st.clean_api?.version ?? 0);
      const caps = st.clean_api?.capabilities ?? [];
      const hasStream = caps.includes('clean_chat_stream');
      const contractOk = version >= 2 && hasStream;
      setApiContractOk(contractOk);
      if (!contractOk) {
        setOnline(false);
        setStatusLine(`bridge_api_outdated: version=${version || 0} (restart bridge)`);
        publishGlobalStatus({
          level: 'fail',
          summary: 'Bridge API outdated',
          source: 'refresh',
          ts: Date.now(),
        });
        return;
      }
      setOnline(Boolean(st.agent.can_chat));
      setModel(st.agent.model || 'gpt-5-codex');
      if (!busy) {
        if (st.agent.can_chat) {
          setStatusLine('Online (Codex)');
          publishGlobalStatus({
            level: 'ok',
            summary: 'Codex online',
            source: 'codex',
            ts: Date.now(),
          });
        } else {
          const reason = st.agent.degraded_reason || 'codex_login_required';
          setStatusLine(reason);
          publishGlobalStatus({
            level: 'warn',
            summary: `Codex: ${reason}`,
            source: 'codex',
            ts: Date.now(),
          });
        }
      }
      setThreads(th.threads);
    } catch (err) {
      setStatusLine(`status error: ${String(err)}`);
      setOnline(false);
      setApiContractOk(false);
      publishGlobalStatus({
        level: 'fail',
        summary: 'Status check failed',
        source: 'refresh',
        ts: Date.now(),
      });
    }
  }, [busy, mode, publishGlobalStatus]);

  useEffect(() => {
    void refresh();
    const id = window.setInterval(() => { void refresh(); }, 3000);
    return () => window.clearInterval(id);
  }, [refresh]);

  useEffect(() => {
    if (!busy || !sendStartedAt) {
      setSendElapsedS(0);
      return;
    }
    const tick = window.setInterval(() => {
      setSendElapsedS(Math.max(0, Math.floor((Date.now() - sendStartedAt) / 1000)));
    }, 250);
    return () => window.clearInterval(tick);
  }, [busy, sendStartedAt]);

  const runNewThread = useCallback(async () => {
    try {
      const out = await cleanNewThread(mode, 'New Chat');
      setThreadId(out.thread.id);
      setThreads(out.threads);
      setHistory(out.history);
    } catch (err) {
      setStatusLine(`new thread failed: ${String(err)}`);
    }
  }, [mode]);

  const runRefresh = useCallback(async () => {
    try {
      await refresh();
      setStatusLine('refresh complete');
      pushOpLog('refresh complete');
      setFailureBanner(null);
      publishGlobalStatus({
        level: 'ok',
        summary: 'Refresh complete',
        source: 'refresh',
        ts: Date.now(),
      });
    } catch (err) {
      const em = String(err);
      setStatusLine(`refresh error: ${em}`);
      pushOpLog(`refresh error: ${em.slice(0, 120)}`);
      setFailureBanner(classifyFailure(em));
      publishGlobalStatus({
        level: 'fail',
        summary: 'Refresh failed',
        source: 'refresh',
        ts: Date.now(),
      });
    }
  }, [classifyFailure, publishGlobalStatus, pushOpLog, refresh]);

  const send = useCallback(async () => {
    const text = input.trim();
    if (!text || busy || !apiContractOk) return;
    setBusy(true);
    setSendStartedAt(Date.now());
    setStatusLine('Sending request to Codex...');
    pushOpLog('chat started');
    publishGlobalStatus({
      level: 'warn',
      summary: 'Chat request running',
      source: 'chat',
      ts: Date.now(),
    });
    setStreamText('');
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const out = await cleanChatStream(
        mode,
        text,
        threadId,
        attachments,
        {
          onStart: () => {
            setStatusLine('Streaming response...');
          },
          onDelta: (chunk) => {
            setStreamText((prev) => `${prev}${chunk}`);
          },
        },
        controller.signal,
      );
      setHistory(out.history);
      setThreads(out.threads);
      if (out.thread_id) setThreadId(out.thread_id);
      setInput('');
      setAttachments([]);
      setStreamText('');
      setStatusLine(`runtime: ${out.executor}`);
      pushOpLog(`chat complete (${out.executor})`);
      setFailureBanner(null);
      publishGlobalStatus({
        level: 'ok',
        summary: `Chat complete (${out.executor})`,
        source: 'chat',
        ts: Date.now(),
      });
    } catch (err) {
      const em = String(err);
      if (em.includes('AbortError')) setStatusLine('request cancelled');
      else setStatusLine(`chat error: ${em}`);
      pushOpLog(`chat failed: ${em.slice(0, 120)}`);
      if (!em.includes('AbortError')) setFailureBanner(classifyFailure(em));
      if (em.includes('AbortError')) {
        publishGlobalStatus({
          level: 'warn',
          summary: 'Chat cancelled',
          source: 'chat',
          ts: Date.now(),
        });
      } else {
        publishGlobalStatus({
          level: 'fail',
          summary: 'Chat failed',
          source: 'chat',
          ts: Date.now(),
        });
      }
    } finally {
      setBusy(false);
      setSendStartedAt(null);
      abortRef.current = null;
    }
  }, [apiContractOk, attachments, busy, classifyFailure, input, mode, publishGlobalStatus, pushOpLog, threadId]);

  const cancelSend = useCallback((): void => {
    if (abortRef.current) {
      abortRef.current.abort();
      pushOpLog('chat cancelled');
    }
  }, [pushOpLog]);

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>): void => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void send();
    }
  };

  const uploadFiles = useCallback(async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const next: CleanAttachment[] = [];
    for (const file of Array.from(files).slice(0, 6)) {
      try {
        next.push(await cleanUploadFile(file));
      } catch (err) {
        setStatusLine(`upload failed: ${String(err)}`);
      }
    }
    if (next.length) setAttachments((prev) => [...prev, ...next].slice(0, 8));
  }, []);

  const onDrop = (e: DragEvent<HTMLTextAreaElement>): void => {
    e.preventDefault();
    setDragActive(false);
    void uploadFiles(e.dataTransfer.files);
  };

  const threadRows = useMemo(() => threads.slice(0, 12), [threads]);

  return (
    <div className="clean-codex-shell clean-card clean-gradient">
      <div className="clean-card-head">
        <h2>Codex Connection</h2>
        <div className={`clean-pill ${online ? 'ok' : 'bad'}`}>{online ? 'ONLINE (CODEX)' : 'OFFLINE'}</div>
      </div>
      <div className="clean-codex-meta">model: {model} · {statusLine}</div>
      {failureBanner && (
        <div className="clean-failure-banner" role="status" aria-live="polite">
          <span className="kind">{failureBanner.kind.replace('_', ' ')}</span>
          <span className="detail">{failureBanner.detail}</span>
        </div>
      )}
      {opsLog.length > 0 && (
        <div className="clean-ops-log" aria-label="Operations log">
          {opsLog.slice(0, 5).map((row) => (
            <div key={`${row.ts}-${row.text}`} className="clean-ops-log-row">
              <span className="time">{new Date(row.ts).toLocaleTimeString()}</span>
              <span className="text">{row.text}</span>
            </div>
          ))}
        </div>
      )}

      <div className="clean-codex-row">
        <button className="clean-btn" onClick={() => void runNewThread()} disabled={busy || !apiContractOk}>New Thread</button>
        <button className="clean-btn clean-btn-alt" onClick={() => void runRefresh()} disabled={busy}>Refresh</button>
      </div>

      <div className="clean-threads">
        {threadRows.length === 0 ? (
          <div className="clean-thread-empty">No threads yet.</div>
        ) : (
          threadRows.map((t) => (
            <button
              key={t.id}
              className={`clean-thread-row ${threadId === t.id ? 'active' : ''}`}
              onClick={() => {
                void cleanSelectThread(mode, t.id).then((out) => {
                  setThreadId(out.thread.id);
                  setThreads(out.threads);
                  setHistory(out.history);
                }).catch((err) => setStatusLine(`thread load failed: ${String(err)}`));
              }}
            >
              <span className="title">{t.title || 'New Chat'}</span>
              <span className="time">{updated(t.updated_at)}</span>
            </button>
          ))
        )}
      </div>

      <div className="clean-chat-log">
        {busy && streamText.trim() && (
          <article className="clean-msg assistant clean-msg-streaming">
            <header>assistant (streaming)</header>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{streamText}</ReactMarkdown>
          </article>
        )}
        {history.length === 0 ? (
          <div className="clean-thread-empty">Ask for code changes, telemetry analysis, tuning, or debugging.</div>
        ) : history.map((m, i) => (
          <article key={`${m.ts}-${i}`} className={`clean-msg ${m.role}`}>
            <header>{m.role}</header>
            {m.role === 'assistant' ? (
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.text}</ReactMarkdown>
            ) : (
              <p>{m.text}</p>
            )}
          </article>
        ))}
      </div>

      <div className="clean-compose">
        <div className="clean-codex-row">
          <button
            className="clean-btn"
            title="Attach csv/txt/json/images for context"
            onClick={() => uploadInputRef.current?.click()}
            disabled={busy || !apiContractOk}
          >
            +
          </button>
          <span className="clean-subtle">{attachments.map((a) => a.name).join(', ') || 'No files attached'}</span>
        </div>
        <input
          ref={uploadInputRef}
          type="file"
          multiple
          className="clean-hidden-file"
          onChange={(e) => void uploadFiles(e.target.files)}
        />
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          onDrop={onDrop}
          onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
          onDragLeave={() => setDragActive(false)}
          className={`clean-input ${dragActive ? 'drag' : ''}`}
          placeholder="Describe the change or issue. Enter = send, Shift+Enter = newline."
        />
        <div className="clean-codex-row">
          <button className="clean-btn" onClick={() => void send()} disabled={busy || !input.trim() || !online || !apiContractOk}>
            {busy ? 'Sending...' : 'Send'}
          </button>
          <button className="clean-btn clean-btn-danger" onClick={cancelSend} disabled={!busy}>
            Cancel
          </button>
          {busy && <span className="clean-send-progress">working... {sendElapsedS}s</span>}
        </div>
      </div>
    </div>
  );
}
