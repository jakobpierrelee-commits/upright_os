import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  cleanChatStream,
  cleanDesignMemoryRate,
  cleanDesignMemoryReportSuccess,
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
  type CleanToolCall,
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
  const [pendingUserText, setPendingUserText] = useState('');
  const [awaitingFirstToken, setAwaitingFirstToken] = useState(false);
  const [waitingHintVisible, setWaitingHintVisible] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const [attachments, setAttachments] = useState<CleanAttachment[]>([]);
  const [dragActive, setDragActive] = useState(false);
  const uploadInputRef = useRef<HTMLInputElement | null>(null);
  const [opsLog, setOpsLog] = useState<Array<{ ts: number; text: string }>>([]);
  const [failureBanner, setFailureBanner] = useState<{ kind: string; detail: string } | null>(null);
  const [latestToolCalls, setLatestToolCalls] = useState<CleanToolCall[]>([]);
  const [markBusy, setMarkBusy] = useState(false);
  const [lastDesignMark, setLastDesignMark] = useState<{
    designId: string;
    score: number;
    balanceScore: number;
    eventScore: number;
    evidenceScore: number;
  } | null>(null);
  const [activeExecContext, setActiveExecContext] = useState<{
    sketch: string;
    board: string;
    bootloader: string;
    port: string;
    profile: string;
  }>({
    sketch: '(unknown)',
    board: '(unknown)',
    bootloader: '(unknown)',
    port: '(none)',
    profile: '(none)',
  });
  const [runtimeIdentity, setRuntimeIdentity] = useState<{
    runtime: string;
    tune: string;
    ident: string;
    hash: string;
  }>({
    runtime: '',
    tune: '',
    ident: '',
    hash: '',
  });
  const [activePanelTab, setActivePanelTab] = useState<'chat' | 'activity'>('chat');
  const lastGlobalKeyRef = useRef<string>('');
  const lastThreadsRefreshRef = useRef<number>(0);

  const readExecutionContext = useCallback(() => {
    try {
      const sketch = String(window.localStorage.getItem('clean.firmware.sketch_folder') || '').trim() || '(unknown)';
      const board = String(window.localStorage.getItem('clean.firmware.board_id') || '').trim() || '(unknown)';
      const bootloader = String(window.localStorage.getItem('clean.firmware.bootloader_id') || '').trim() || '(unknown)';
      const port = String(window.localStorage.getItem('clean.firmware.port') || '').trim() || '(none)';
      const profile = String(window.localStorage.getItem('clean.active_profile_id') || '').trim() || '(none)';
      setActiveExecContext({ sketch, board, bootloader, port, profile });
    } catch {
      // ignore
    }
  }, []);

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
      const st = await cleanStatus(mode);
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
      setRuntimeIdentity({
        runtime: String((st.status as Record<string, unknown>)?.runtime ?? (st.status as Record<string, unknown>)?.runtime_version ?? '').trim(),
        tune: String((st.status as Record<string, unknown>)?.tune ?? (st.status as Record<string, unknown>)?.tune_version ?? '').trim(),
        ident: String((st.status as Record<string, unknown>)?.ident ?? '').trim(),
        hash: String((st.status as Record<string, unknown>)?.hash ?? '').trim(),
      });
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
      const now = Date.now();
      if ((now - lastThreadsRefreshRef.current) >= 2000) {
        const th = await cleanThreads(mode);
        setThreads(th.threads);
        lastThreadsRefreshRef.current = now;
      }
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
    // compat/nano: faster polling while STATUS is low-rate ascii telemetry.
    // Keep this adapter-level and replace with transport-aware streaming on faster MCUs.
    const id = window.setInterval(() => { void refresh(); }, 200);
    return () => window.clearInterval(id);
  }, [refresh]);

  useEffect(() => {
    readExecutionContext();
    const id = window.setInterval(() => readExecutionContext(), 1500);
    return () => window.clearInterval(id);
  }, [readExecutionContext]);

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

  useEffect(() => {
    if (!busy || !awaitingFirstToken) {
      setWaitingHintVisible(false);
      return;
    }
    const timer = window.setTimeout(() => {
      setWaitingHintVisible(true);
    }, 2000);
    return () => window.clearTimeout(timer);
  }, [awaitingFirstToken, busy]);

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

  const markBuildWorkedWell = useCallback(async (): Promise<void> => {
    if (markBusy || !apiContractOk) return;
    setMarkBusy(true);
    try {
      const sessionKey = `local:clean:${mode}`;
      const observation = {
        runtime_version: runtimeIdentity.runtime,
        tune_version: runtimeIdentity.tune,
        ident: runtimeIdentity.ident,
        hash: runtimeIdentity.hash,
        profile_id: activeExecContext.profile !== '(none)' ? activeExecContext.profile : '',
        board_id: activeExecContext.board !== '(unknown)' ? activeExecContext.board : '',
        port: activeExecContext.port !== '(none)' ? activeExecContext.port : '',
        test_type: 'manual_success_mark',
      };
      const report = await cleanDesignMemoryReportSuccess({
        session_key: sessionKey,
        source: 'codex_panel',
        note: `Marked worked well from clean panel (${mode})`,
        success: true,
        profile_id: observation.profile_id,
        test_type: observation.test_type,
        observation,
      });
      const designId = String(report.design?.design_id || '').trim();
      if (!designId) throw new Error('design_id_missing');
      const rated = await cleanDesignMemoryRate({
        session_key: sessionKey,
        design_id: designId,
        rating: 'positive',
        note: 'Operator-confirmed worked well',
      });
      const score = Number(rated.design?.score ?? report.design?.score ?? 0);
      const balanceScore = Number(rated.design?.balance_score ?? report.design?.balance_score ?? 0);
      const eventScore = Number(rated.design?.event_score ?? report.design?.event_score ?? 0);
      const evidenceScore = Number(rated.design?.evidence_score ?? report.design?.evidence_score ?? 0);
      setLastDesignMark({ designId, score, balanceScore, eventScore, evidenceScore });
      pushOpLog(
        `design memory updated: ${designId} (score ${score.toFixed(1)} | balance ${balanceScore.toFixed(1)} | event ${eventScore.toFixed(1)} | evidence ${evidenceScore.toFixed(1)})`,
      );
      setFailureBanner(null);
      publishGlobalStatus({
        level: 'ok',
        summary: 'Design marked worked well',
        source: 'codex',
        ts: Date.now(),
      });
    } catch (err) {
      const em = String(err);
      setFailureBanner(classifyFailure(em));
      pushOpLog(`design memory update failed: ${em.slice(0, 120)}`);
      publishGlobalStatus({
        level: 'warn',
        summary: 'Design mark failed',
        source: 'codex',
        ts: Date.now(),
      });
    } finally {
      setMarkBusy(false);
    }
  }, [
    activeExecContext.board,
    activeExecContext.port,
    activeExecContext.profile,
    apiContractOk,
    classifyFailure,
    markBusy,
    mode,
    publishGlobalStatus,
    pushOpLog,
    runtimeIdentity.hash,
    runtimeIdentity.ident,
    runtimeIdentity.runtime,
    runtimeIdentity.tune,
  ]);

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
    setPendingUserText(text);
    setAwaitingFirstToken(true);
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
            setStatusLine('Request accepted. Waiting for first token...');
          },
          onDelta: (chunk) => {
            setAwaitingFirstToken(false);
            setStatusLine('Streaming response...');
            setStreamText((prev) => `${prev}${chunk}`);
          },
        },
        controller.signal,
      );
      setHistory(out.history);
      setThreads(out.threads);
      if (out.thread_id) setThreadId(out.thread_id);
      setLatestToolCalls(out.tool_calls ?? []);
      setInput('');
      setAttachments([]);
      setStreamText('');
      setPendingUserText('');
      setAwaitingFirstToken(false);
      setStatusLine(`runtime: ${out.executor}`);
      pushOpLog(`chat complete (${out.executor}) · tools=${String((out.tool_calls ?? []).length)}`);
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
      setPendingUserText('');
      setAwaitingFirstToken(false);
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
  const sendDisabledReason = useMemo(() => {
    if (busy) return 'request in progress';
    if (!apiContractOk) return 'bridge API outdated';
    if (!online) return 'Codex offline';
    if (!input.trim()) return 'type a message';
    return '';
  }, [apiContractOk, busy, input, online]);

  return (
    <div className="clean-codex-shell clean-card clean-gradient">
      <div className="clean-card-head">
        <h2>Codex Connection</h2>
        <div className={`clean-pill ${online ? 'ok' : 'bad'}`}>{online ? 'ONLINE (CODEX)' : 'OFFLINE'}</div>
      </div>
      {lastDesignMark && (
        <div className="clean-codex-meta">
          design: {lastDesignMark.designId} · score {lastDesignMark.score.toFixed(1)} (balance {lastDesignMark.balanceScore.toFixed(1)} / event {lastDesignMark.eventScore.toFixed(1)} / evidence {lastDesignMark.evidenceScore.toFixed(1)})
        </div>
      )}
      <div className="clean-codex-meta">model: {model} · {statusLine}</div>
      <div className="clean-panel-tabs" role="tablist" aria-label="Codex panel sections">
        <button
          role="tab"
          aria-selected={activePanelTab === 'chat'}
          className={`clean-panel-tab ${activePanelTab === 'chat' ? 'active' : ''}`}
          onClick={() => setActivePanelTab('chat')}
        >
          Chat
        </button>
        <button
          role="tab"
          aria-selected={activePanelTab === 'activity'}
          className={`clean-panel-tab ${activePanelTab === 'activity' ? 'active' : ''}`}
          onClick={() => setActivePanelTab('activity')}
        >
          Activity
        </button>
      </div>

      <div className="clean-codex-row">
        <button className="clean-btn" onClick={() => void runNewThread()} disabled={busy || !apiContractOk}>New Thread</button>
        <button className="clean-btn clean-btn-alt" onClick={() => void runRefresh()} disabled={busy}>Refresh</button>
        <button
          className="clean-btn clean-btn-alt"
          onClick={() => void markBuildWorkedWell()}
          disabled={busy || markBusy || !apiContractOk}
          title="Report current build as worked well and rate it positive"
        >
          {markBusy ? 'Marking...' : 'Mark Worked Well'}
        </button>
      </div>

      {activePanelTab === 'activity' && (
        <>
          <div className="clean-exec-context" aria-label="Codex execution context">
            <div className="clean-exec-context-head">Active Execution Context</div>
            <div className="clean-exec-context-grid">
              <span>sketch</span><span>{activeExecContext.sketch}</span>
              <span>board</span><span>{activeExecContext.board}</span>
              <span>bootloader</span><span>{activeExecContext.bootloader}</span>
              <span>port</span><span>{activeExecContext.port}</span>
              <span>profile</span><span>{activeExecContext.profile}</span>
              <span>thread</span><span>{threadId || '(new)'}</span>
            </div>
          </div>
          {failureBanner && (
            <div className="clean-failure-banner" role="status" aria-live="polite">
              <span className="kind">{failureBanner.kind.replace('_', ' ')}</span>
              <span className="detail">{failureBanner.detail}</span>
            </div>
          )}
          {opsLog.length > 0 && (
            <div className="clean-ops-log" aria-label="Operations log">
              {opsLog.slice(0, 8).map((row) => (
                <div key={`${row.ts}-${row.text}`} className="clean-ops-log-row">
                  <span className="time">{new Date(row.ts).toLocaleTimeString()}</span>
                  <span className="text">{row.text}</span>
                </div>
              ))}
            </div>
          )}
          {latestToolCalls.length > 0 && (
            <div className="clean-tool-rail" aria-label="Structured tool output">
              <div className="clean-exec-context-head">Tool Output</div>
              {latestToolCalls.slice(0, 12).map((tc, idx) => {
                const ok = Boolean(tc?.result?.ok);
                const dt = Number(tc?.result?.execution_time_ms ?? 0);
                const argKeys = Object.keys(tc?.arguments ?? {}).slice(0, 4);
                return (
                  <div key={`${tc.name}-${String(idx)}`} className={`clean-tool-row ${ok ? 'ok' : 'fail'}`}>
                    <div className="clean-tool-row-head">
                      <span className="name">{tc.name}</span>
                      <span className={`status ${ok ? 'ok' : 'fail'}`}>{ok ? 'PASS' : 'FAIL'}</span>
                      <span className="meta">{dt > 0 ? `${dt}ms` : 'n/a'}</span>
                    </div>
                    <div className="clean-tool-row-meta">
                      args: {argKeys.length > 0 ? argKeys.join(', ') : 'none'}
                    </div>
                    {!ok && tc?.result?.error && (
                      <div className="clean-tool-row-err">{String(tc.result.error)}</div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}

      {activePanelTab === 'chat' && (
        <>
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
            {(busy || sendDisabledReason) && (
              <div className="clean-chat-status-rail">
                {busy && pendingUserText.trim() && (
                  <div className="clean-chat-status-row">
                    <span className="label">pending</span>
                    <span className="value">{pendingUserText}</span>
                  </div>
                )}
                {busy && awaitingFirstToken && waitingHintVisible && (
                  <div className="clean-chat-status-row">
                    <span className="label">status</span>
                    <span className="value">Waiting for first token...</span>
                  </div>
                )}
                {busy && !awaitingFirstToken && (
                  <div className="clean-chat-status-row">
                    <span className="label">status</span>
                    <span className="value">Streaming response...</span>
                  </div>
                )}
                {sendDisabledReason && (
                  <div className="clean-chat-status-row warn">
                    <span className="label">blocked</span>
                    <span className="value">{sendDisabledReason}</span>
                  </div>
                )}
              </div>
            )}
            <div className="clean-codex-row">
              <button className="clean-btn" onClick={() => void send()} disabled={Boolean(sendDisabledReason)}>
                {busy ? 'Sending...' : 'Send'}
              </button>
              <button className="clean-btn clean-btn-danger" onClick={cancelSend} disabled={!busy}>
                Cancel
              </button>
              {busy && <span className="clean-send-progress">working... {sendElapsedS}s</span>}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
