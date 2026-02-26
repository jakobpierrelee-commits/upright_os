import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  agentChat,
  agentChatStream,
  agentUploadFile,
  agentNewThread,
  agentSelectThread,
  agentSetMode,
  agentStatus,
  agentThreads,
  authLogin,
  authLogout,
  authMe,
  authOpenAiStatus,
  authRegister,
  authSetOpenAiKey,
  setSessionToken,
  type AgentMode,
  type AgentAttachment,
  type AiHistoryItem,
  type AiThreadSummary,
  type AuthUser,
  type ToolCallResult,
} from '../../api';

type Props = Record<string, unknown>;
type RuntimeUiState = {
  openAiConfigured: boolean;
  openAiModel: string;
  openAiModelAllowed: boolean;
  runtimeProvider: string;
  codexLoggedIn: boolean;
  bridgeConnected: boolean;
};

const TOKEN_STORAGE_KEY = 'upright.agent.session_token';
const ADVANCED_PANEL_STORAGE_KEY = 'upright.agent.advanced_panel_open';
const CONNECTION_PANEL_STORAGE_KEY = 'upright.agent.connection_panel_open';
const RESPONSE_DENSITY_STORAGE_KEY = 'upright.agent.response_density';

const MODE_LABELS: Record<AgentMode, string> = {
  app_dev: 'App Dev',
  robot_dev: 'Robot Dev',
  ops_debug: 'Ops Debug',
};

function fmtText(value: unknown): string {
  return String(value ?? '');
}

function decodeTelemetryMode(value: unknown): string {
  const raw = String(value ?? '').trim().toLowerCase();
  if (!raw || raw === '-' || raw === 'none' || raw === 'unknown') return 'Unknown';
  if (raw === '0' || raw === 'idle' || raw === 'safe_idle' || raw === 'safe-idle') return 'Safe Idle';
  if (raw === '1' || raw === 'arm' || raw === 'armed') return 'Armed';
  if (raw === '2' || raw === 'run' || raw === 'balance' || raw === 'balancing') return 'Balancing';
  if (raw === '3' || raw === 'estop' || raw === 'e_stop' || raw === 'e-stop') return 'E-Stop';
  return String(value ?? 'Unknown');
}

function toolSummary(call: ToolCallResult): string {
  const result = call?.result;
  if (!result) return 'no result';
  if (result.ok) return `ok (${Math.round(result.execution_time_ms)}ms)`;
  return result.error ? `error: ${result.error}` : 'error';
}

function formatUpdated(ts?: number): string {
  const v = Number(ts ?? 0);
  if (!Number.isFinite(v) || v <= 0) return 'updated just now';
  const delta = Math.max(0, Math.floor(Date.now() / 1000 - v));
  if (delta < 60) return 'updated just now';
  if (delta < 3600) return `updated ${Math.floor(delta / 60)}m ago`;
  if (delta < 86400) return `updated ${Math.floor(delta / 3600)}h ago`;
  return `updated ${Math.floor(delta / 86400)}d ago`;
}

function normalizeAssistantText(raw: string): string {
  let text = String(raw || '');
  text = text.replace(/\u25a1\s*cite\s*\u25a1/gi, '\n**Source:** ');
  text = text.replace(/�/g, '');
  text = text.replace(/[ \t]+\n/g, '\n');
  text = text.replace(/\n{3,}/g, '\n\n');
  text = text.replace(/(^|\n)-\s*(\*\*[^*\n]+\*\*)/g, '$1\n- $2');
  return text.trim();
}

function compactAssistantText(raw: string): string {
  const text = normalizeAssistantText(raw);
  if (text.length <= 700) return text;
  const lines = text.split('\n').map((l) => l.trim()).filter(Boolean);
  const head = lines.slice(0, 10).join('\n');
  const bullets = lines.filter((l) => l.startsWith('- ')).slice(0, 4).join('\n');
  const compact = `${head}${bullets ? `\n\n${bullets}` : ''}`.trim();
  return `${compact}\n\n_Compact view. Switch to Detailed for full output._`;
}

export function CodexPanel(_: Props): JSX.Element {
  const [mode, setMode] = useState<AgentMode>('robot_dev');
  const [allowedModes, setAllowedModes] = useState<AgentMode[]>(['app_dev', 'robot_dev', 'ops_debug']);
  const [openAiConfigured, setOpenAiConfigured] = useState<boolean>(false);
  const [openAiModel, setOpenAiModel] = useState<string>('');
  const [openAiModelAllowed, setOpenAiModelAllowed] = useState<boolean>(false);
  const [runtimeProvider, setRuntimeProvider] = useState<string>('openai');
  const [codexLoggedIn, setCodexLoggedIn] = useState<boolean>(false);
  const [statusLine, setStatusLine] = useState<string>('Agent ready');
  const [bridgeConnected, setBridgeConnected] = useState<boolean>(false);
  const [statusPreview, setStatusPreview] = useState<string>('');
  const [history, setHistory] = useState<AiHistoryItem[]>([]);
  const [threads, setThreads] = useState<AiThreadSummary[]>([]);
  const [threadId, setThreadId] = useState<string | undefined>(undefined);
  const [input, setInput] = useState<string>('');
  const [busy, setBusy] = useState<boolean>(false);
  const [toolCalls, setToolCalls] = useState<ToolCallResult[]>([]);
  const [iterations, setIterations] = useState<number>(1);
  const [requestState, setRequestState] = useState<'idle' | 'running' | 'done' | 'error'>('idle');
  const [lastPrompt, setLastPrompt] = useState<string>('');
  const [useStreaming, setUseStreaming] = useState<boolean>(true);
  const [threadQuery, setThreadQuery] = useState<string>('');
  const [pinnedThreadIds, setPinnedThreadIds] = useState<string[]>([]);
  const [threadTitleOverrides, setThreadTitleOverrides] = useState<Record<string, string>>({});
  const [attachments, setAttachments] = useState<AgentAttachment[]>([]);
  const [dragActive, setDragActive] = useState<boolean>(false);
  const streamAbortRef = useRef<AbortController | null>(null);
  const uploadInputRef = useRef<HTMLInputElement | null>(null);

  const [user, setUser] = useState<AuthUser | null>(null);
  const [email, setEmail] = useState<string>('');
  const [password, setPassword] = useState<string>('');
  const [authBusy, setAuthBusy] = useState<boolean>(false);
  const [authMode, setAuthMode] = useState<'auto' | 'login' | 'register'>('auto');
  const [authExpanded, setAuthExpanded] = useState<boolean>(false);
  const [connectionExpanded, setConnectionExpanded] = useState<boolean>(true);
  const [responseDensity, setResponseDensity] = useState<'compact' | 'detailed'>('compact');

  const [openAiKeyInput, setOpenAiKeyInput] = useState<string>('');
  const [openAiModelInput, setOpenAiModelInput] = useState<string>('gpt-5-codex');
  const runtimeStableRef = useRef<RuntimeUiState>({
    openAiConfigured: false,
    openAiModel: '',
    openAiModelAllowed: false,
    runtimeProvider: 'openai',
    codexLoggedIn: false,
    bridgeConnected: false,
  });
  const runtimeCandidateRef = useRef<{ sig: string; hits: number }>({ sig: '', hits: 0 });

  const commitRuntimeUi = useCallback((next: RuntimeUiState) => {
    runtimeStableRef.current = next;
    setOpenAiConfigured(next.openAiConfigured);
    setOpenAiModel(next.openAiModel);
    setOpenAiModelAllowed(next.openAiModelAllowed);
    setRuntimeProvider(next.runtimeProvider);
    setCodexLoggedIn(next.codexLoggedIn);
    setBridgeConnected(next.bridgeConnected);
  }, []);

  const applyRuntimeUi = useCallback((next: RuntimeUiState) => {
    const stable = runtimeStableRef.current;
    const stableSig = JSON.stringify(stable);
    const nextSig = JSON.stringify(next);
    if (nextSig === stableSig) {
      runtimeCandidateRef.current = { sig: '', hits: 0 };
      return;
    }
    const cand = runtimeCandidateRef.current;
    if (cand.sig === nextSig) runtimeCandidateRef.current = { sig: nextSig, hits: cand.hits + 1 };
    else runtimeCandidateRef.current = { sig: nextSig, hits: 1 };

    const clearlyGoodCodex = next.runtimeProvider === 'codex_cli' && next.codexLoggedIn && next.openAiModelAllowed;
    if (clearlyGoodCodex || runtimeCandidateRef.current.hits >= 2) {
      commitRuntimeUi(next);
      runtimeCandidateRef.current = { sig: '', hits: 0 };
    }
  }, [commitRuntimeUi]);

  const loadThreads = useCallback(async (nextMode?: AgentMode) => {
    try {
      const d = await agentThreads(nextMode ?? mode);
      setThreads(d.threads);
    } catch {
      // non-fatal
    }
  }, [mode]);

  const refreshAuth = useCallback(async () => {
    try {
      const me = await authMe();
      setUser(me);
      const st = await authOpenAiStatus();
      setOpenAiConfigured(Boolean(st.runtime_has_key || st.configured));
      setOpenAiModel(String(st.model || openAiModel || ''));
      return true;
    } catch {
      setUser(null);
      return false;
    }
  }, [openAiModel]);

  const loadStatus = useCallback(async () => {
    try {
      const d = await agentStatus();
      setMode(d.agent.mode);
      setAllowedModes(d.agent.allowed_modes?.length ? d.agent.allowed_modes : ['app_dev', 'robot_dev', 'ops_debug']);
      applyRuntimeUi({
        openAiConfigured: Boolean(d.agent.openai_configured),
        openAiModel: String(d.agent.openai_model || ''),
        openAiModelAllowed: Boolean(d.agent.openai_model_allowed),
        runtimeProvider: String(d.agent.provider || 'openai'),
        codexLoggedIn: Boolean(d.agent.codex_login?.logged_in),
        bridgeConnected: Boolean(d.health.connected),
      });
      const st = d.status ?? {};
      const parts = [
        `mode=${decodeTelemetryMode(st.mode)}`,
        `ang=${fmtText(st.ang || '-')}`,
        `raw=${fmtText(st.raw || '-')}`,
        `gyro=${fmtText(st.gyro ?? st.gyr ?? st.gx ?? '-')}`,
        `out=${fmtText(st.out || '-')}`,
      ];
      setStatusPreview(parts.join(' '));
      setStatusLine((prev) => (prev.startsWith('status error:') ? 'agent status recovered' : prev));
      await loadThreads(d.agent.mode);
    } catch (err) {
      setStatusLine(`status error: ${String(err)}`);
    }
  }, [applyRuntimeUi, loadThreads]);

  useEffect(() => {
    const token = window.localStorage.getItem(TOKEN_STORAGE_KEY);
    if (token) setSessionToken(token);
    void refreshAuth();
    void loadStatus();
    const id = window.setInterval(() => {
      void loadStatus();
    }, 2600);
    return () => window.clearInterval(id);
  }, [loadStatus, refreshAuth]);

  useEffect(() => {
    try {
      const rawAdvanced = localStorage.getItem(ADVANCED_PANEL_STORAGE_KEY);
      if (rawAdvanced != null) setAuthExpanded(rawAdvanced === '1');
      const rawConnection = localStorage.getItem(CONNECTION_PANEL_STORAGE_KEY);
      if (rawConnection != null) setConnectionExpanded(rawConnection === '1');
      const rawDensity = localStorage.getItem(RESPONSE_DENSITY_STORAGE_KEY);
      if (rawDensity === 'compact' || rawDensity === 'detailed') setResponseDensity(rawDensity);
      const rawPins = localStorage.getItem('upright.agent.pinned_threads');
      if (rawPins) setPinnedThreadIds(JSON.parse(rawPins) as string[]);
      const rawTitles = localStorage.getItem('upright.agent.thread_titles');
      if (rawTitles) setThreadTitleOverrides(JSON.parse(rawTitles) as Record<string, string>);
    } catch {
      // ignore storage errors
    }
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(ADVANCED_PANEL_STORAGE_KEY, authExpanded ? '1' : '0');
    } catch {
      // ignore storage errors
    }
  }, [authExpanded]);

  useEffect(() => {
    try {
      localStorage.setItem(CONNECTION_PANEL_STORAGE_KEY, connectionExpanded ? '1' : '0');
    } catch {
      // ignore storage errors
    }
  }, [connectionExpanded]);

  useEffect(() => {
    try {
      localStorage.setItem(RESPONSE_DENSITY_STORAGE_KEY, responseDensity);
    } catch {
      // ignore storage errors
    }
  }, [responseDensity]);

  const runAuth = useCallback(async () => {
    if (authBusy) return;
    setAuthBusy(true);
    try {
      const em = email.trim();
      const pw = password;
      if (!em || !pw) {
        setStatusLine('auth error: email/password required');
        return;
      }
      let out: { session_token: string; user: AuthUser };
      let resolvedMode: 'login' | 'register' = 'login';
      if (authMode === 'register') {
        out = await authRegister(em, pw);
        resolvedMode = 'register';
      } else if (authMode === 'login') {
        out = await authLogin(em, pw);
        resolvedMode = 'login';
      } else {
        try {
          out = await authLogin(em, pw);
          resolvedMode = 'login';
        } catch (err) {
          const emsg = String((err as Error)?.message ?? err ?? '');
          if (!emsg.includes('invalid_credentials')) throw err;
          out = await authRegister(em, pw);
          resolvedMode = 'register';
        }
      }
      setSessionToken(out.session_token);
      window.localStorage.setItem(TOKEN_STORAGE_KEY, out.session_token);
      setUser(out.user);
      setStatusLine(`${resolvedMode} ok: ${out.user.email}`);
      await refreshAuth();
      await loadStatus();
    } catch (err) {
      setStatusLine(`auth error: ${String(err)}`);
    } finally {
      setAuthBusy(false);
    }
  }, [authBusy, authMode, email, loadStatus, password, refreshAuth]);

  const runLogout = useCallback(async () => {
    setAuthBusy(true);
    try {
      await authLogout();
    } catch {
      // ignore logout transport errors; local clear is authoritative for UI session
    } finally {
      setSessionToken(null);
      window.localStorage.removeItem(TOKEN_STORAGE_KEY);
      setUser(null);
      setOpenAiConfigured(false);
      setStatusLine('logged out');
      setAuthBusy(false);
      await loadStatus();
    }
  }, [loadStatus]);

  const saveOpenAi = useCallback(async () => {
    if (!user) {
      setStatusLine('save key blocked: login required');
      return;
    }
    const key = openAiKeyInput.trim();
    const model = openAiModelInput.trim();
    if (!key || !model) {
      setStatusLine('save key blocked: key and model required');
      return;
    }
    setAuthBusy(true);
    try {
      const out = await authSetOpenAiKey(key, model);
      setOpenAiConfigured(Boolean(out.configured));
      setOpenAiModel(String(out.model || model));
      setOpenAiKeyInput('');
      setStatusLine(`openai key saved (${out.model})`);
      await loadStatus();
    } catch (err) {
      setStatusLine(`save key error: ${String(err)}`);
    } finally {
      setAuthBusy(false);
    }
  }, [loadStatus, openAiKeyInput, openAiModelInput, user]);

  const applyMode = useCallback(async (nextMode: AgentMode) => {
    setBusy(true);
    try {
      const d = await agentSetMode(nextMode);
      setMode(d.mode);
      setAllowedModes(d.allowed_modes?.length ? d.allowed_modes : ['app_dev', 'robot_dev', 'ops_debug']);
      setOpenAiConfigured(Boolean(d.openai_configured));
      setStatusLine(`mission mode set: ${MODE_LABELS[d.mode] ?? d.mode}`);
      setThreadId(undefined);
      setHistory([]);
      setToolCalls([]);
      setIterations(1);
      await loadThreads(d.mode);
    } catch (err) {
      setStatusLine(`mode error: ${String(err)}`);
    } finally {
      setBusy(false);
      await loadStatus();
    }
  }, [loadStatus, loadThreads]);

  const createThread = useCallback(async () => {
    setBusy(true);
    try {
      const d = await agentNewThread(mode);
      setThreadId(d.thread.id);
      setThreads(d.threads);
      setHistory(d.history);
      setToolCalls([]);
      setIterations(1);
      setStatusLine('new thread created');
    } catch (err) {
      setStatusLine(`thread error: ${String(err)}`);
    } finally {
      setBusy(false);
    }
  }, [mode]);

  const selectThread = useCallback(async (id: string) => {
    setBusy(true);
    try {
      const d = await agentSelectThread(mode, id);
      setThreadId(d.thread.id);
      setThreads(d.threads);
      setHistory(d.history);
      setToolCalls([]);
      setIterations(1);
      setStatusLine(`thread selected: ${d.thread.title}`);
    } catch (err) {
      setStatusLine(`thread select error: ${String(err)}`);
    } finally {
      setBusy(false);
    }
  }, [mode]);

  const send = useCallback(async () => {
    const message = input.trim();
    if (!message || busy) return;
    const sentAt = Date.now();
    setBusy(true);
    setRequestState('running');
    setLastPrompt(message);
    setStatusLine('agent thinking...');
    setHistory((prev) => [...prev, { ts: Date.now() / 1000, role: 'user', text: message }]);
    setInput('');
    try {
      if (useStreaming) {
        const ac = new AbortController();
        streamAbortRef.current = ac;
        let streamed = '';
        setHistory((prev) => [...prev, { ts: Date.now() / 1000, role: 'assistant', text: '' }]);
        const d = await agentChatStream(
          message,
          mode,
          threadId,
          attachments,
          {
            onDelta: (txt) => {
              streamed += txt;
              setHistory((prev) => {
                const next = [...prev];
                for (let i = next.length - 1; i >= 0; i -= 1) {
                  if (next[i].role === 'assistant') {
                    next[i] = { ...next[i], text: streamed };
                    break;
                  }
                }
                return next;
              });
            },
          },
          ac.signal,
        );
        setThreadId(d.thread_id);
        setMode(d.agent.mode);
        if (d.history && d.history.length) setHistory(d.history);
        if (d.threads && d.threads.length) setThreads(d.threads);
        setToolCalls(d.tool_calls ?? []);
        setIterations(d.iterations ?? 1);
      } else {
        const d = await agentChat(message, mode, threadId, attachments);
        setThreadId(d.thread_id);
        setMode(d.agent.mode);
        if (d.history && d.history.length) {
          setHistory(d.history);
        } else {
          setHistory((prev) => [...prev, { ts: Date.now() / 1000, role: 'assistant', text: d.reply }]);
        }
        if (d.threads && d.threads.length) setThreads(d.threads);
        setToolCalls(d.tool_calls ?? []);
        setIterations(d.iterations ?? 1);
      }
      setRequestState('done');
      setStatusLine(`response ready (${Date.now() - sentAt}ms)`);
      await loadStatus();
    } catch (err) {
      setRequestState('error');
      const emsg = String(err);
      if (emsg.includes('AbortError')) {
        setStatusLine('request canceled');
      } else {
        setHistory((prev) => [...prev, { ts: Date.now() / 1000, role: 'assistant', text: `error: ${emsg}` }]);
        setStatusLine(`chat error: ${emsg}`);
      }
    } finally {
      setBusy(false);
      streamAbortRef.current = null;
    }
  }, [attachments, busy, input, loadStatus, mode, threadId, useStreaming]);

  const cancelSend = useCallback(() => {
    if (!streamAbortRef.current) return;
    streamAbortRef.current.abort();
  }, []);

  const regenerate = useCallback(async () => {
    if (!lastPrompt || busy) return;
    setInput(lastPrompt);
  }, [busy, lastPrompt]);

  const togglePinThread = useCallback((id: string) => {
    setPinnedThreadIds((prev) => {
      const next = prev.includes(id) ? prev.filter((x) => x !== id) : [id, ...prev];
      try {
        localStorage.setItem('upright.agent.pinned_threads', JSON.stringify(next));
      } catch {
        // ignore
      }
      return next;
    });
  }, []);

  const renameThread = useCallback((id: string) => {
    const current = threadTitleOverrides[id] ?? threads.find((t) => t.id === id)?.title ?? '';
    const next = window.prompt('Rename thread', current);
    if (!next) return;
    setThreadTitleOverrides((prev) => {
      const out = { ...prev, [id]: next.trim() || current };
      try {
        localStorage.setItem('upright.agent.thread_titles', JSON.stringify(out));
      } catch {
        // ignore
      }
      return out;
    });
  }, [threadTitleOverrides, threads]);

  const statusBadge = useMemo(() => {
    if (!bridgeConnected) return 'bridge offline';
    if (runtimeProvider === 'codex_cli' && !codexLoggedIn) return 'codex login required';
    if (runtimeProvider === 'codex_cli' && codexLoggedIn) return 'online (codex)';
    if (!openAiConfigured) return 'openai key missing';
    if (!openAiModelAllowed) return 'model blocked';
    return 'online';
  }, [bridgeConnected, codexLoggedIn, openAiConfigured, openAiModelAllowed, runtimeProvider]);

  const statusTone = useMemo(() => {
    if (!bridgeConnected) return 'bad';
    if (runtimeProvider === 'codex_cli') return codexLoggedIn ? 'ok' : 'warn';
    if (!openAiConfigured || !openAiModelAllowed) return 'warn';
    return 'ok';
  }, [bridgeConnected, codexLoggedIn, openAiConfigured, openAiModelAllowed, runtimeProvider]);

  const showApiKeyControls = runtimeProvider !== 'codex_cli';

  const continueLabel = useMemo(() => {
    const em = email.trim().toLowerCase();
    if (em.endsWith('@gmail.com')) return 'Continue with Gmail';
    return 'Continue';
  }, [email]);

  const runtimeModelLabel = useMemo(() => {
    const m = String(openAiModel || '').trim();
    return m || 'gpt-5-codex';
  }, [openAiModel]);

  const requestStateLabel = useMemo(() => {
    if (requestState === 'running') return 'Running';
    if (requestState === 'done') return 'Ready';
    if (requestState === 'error') return 'Error';
    return 'Idle';
  }, [requestState]);

  const removeAttachment = useCallback((idx: number) => {
    setAttachments((prev) => prev.filter((_, i) => i !== idx));
  }, []);

  const uploadFiles = useCallback(async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setStatusLine(`uploading ${files.length} file(s)...`);
    const next: AgentAttachment[] = [];
    for (const f of Array.from(files).slice(0, 5)) {
      try {
        const att = await agentUploadFile(f);
        next.push(att);
      } catch (err) {
        setStatusLine(`upload failed: ${f.name} (${String(err)})`);
      }
    }
    if (next.length > 0) {
      setAttachments((prev) => [...prev, ...next].slice(-8));
      setStatusLine(`uploaded ${next.length} file(s)`);
    }
    if (uploadInputRef.current) uploadInputRef.current.value = '';
  }, []);

  const onComposerDragOver = useCallback((e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragActive(true);
  }, []);

  const onComposerDragLeave = useCallback((e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragActive(false);
  }, []);

  const onComposerDrop = useCallback((e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragActive(false);
    void uploadFiles(e.dataTransfer?.files ?? null);
  }, [uploadFiles]);

  const visibleThreads = useMemo(() => {
    const q = threadQuery.trim().toLowerCase();
    const sorted = [...threads].sort((a, b) => {
      const ap = pinnedThreadIds.includes(a.id) ? 1 : 0;
      const bp = pinnedThreadIds.includes(b.id) ? 1 : 0;
      if (ap !== bp) return bp - ap;
      return (b.updated_at ?? 0) - (a.updated_at ?? 0);
    });
    if (!q) return sorted;
    return sorted.filter((t) => {
      const ttl = (threadTitleOverrides[t.id] || t.title || '').toLowerCase();
      const prv = (t.preview || '').toLowerCase();
      return ttl.includes(q) || prv.includes(q);
    });
  }, [pinnedThreadIds, threadQuery, threadTitleOverrides, threads]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        e.preventDefault();
        void send();
      }
      if (e.key === 'Escape') cancelSend();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [cancelSend, send]);

  return (
    <section className="tool-panel codex-panel agent-console-v2">
      <div className="tool-panel-head agent-head">
        <h2>AGENT CONSOLE V1</h2>
        <span className="agent-build-tag">ui_build=agent_console_v1</span>
      </div>
      <div className="tool-panel-body codex-pane agent-console-v2-body">
        <section className="agent-now-stack">
          <section className={`agent-now-card agent-connection-card ${connectionExpanded ? 'expanded' : 'collapsed'}`}>
            <div className="agent-now-top">
              <h3>Codex Connection</h3>
              <div className="agent-now-top-right">
                <div className={`agent-chip ${statusTone}`}>{statusBadge}</div>
                <button className="btn-sm" type="button" onClick={() => setConnectionExpanded((v) => !v)}>
                  {connectionExpanded ? 'Hide' : 'Show'}
                </button>
              </div>
            </div>
            {connectionExpanded ? (
              <>
                <div className="agent-now-grid">
                  <span><em>Provider</em><strong>{runtimeProvider}</strong></span>
                  <span><em>Model</em><strong>{runtimeModelLabel}</strong></span>
                  <span><em>User</em><strong>{user ? user.email : 'Not logged in'}</strong></span>
                  <span><em>Iter</em><strong>{iterations}</strong></span>
                </div>
                <p className="hint">{statusPreview || 'no status yet'}</p>
                <div className="agent-now-actions">
                  <button className="btn-sm btn-arm" type="button" disabled={authBusy} onClick={() => void runAuth()}>{continueLabel}</button>
                  <button className="btn-sm" type="button" disabled={busy} onClick={() => void loadStatus()}>Refresh</button>
                  <button className="btn-sm" type="button" disabled={busy} onClick={() => void createThread()}>New Thread</button>
                  <button className={`btn-sm ${useStreaming ? 'btn-arm' : ''}`} disabled={busy} onClick={() => setUseStreaming((v) => !v)}>
                    {useStreaming ? 'Streaming On' : 'Streaming Off'}
                  </button>
                  <span className="hint">{statusLine}</span>
                </div>
              </>
            ) : (
              <p className="hint">Codex connection is online. Press Show to view detailed runtime status.</p>
            )}
          </section>

          <section className="agent-now-card agent-mode-card">
            <div className="agent-mode-inline">
              <h3>Mission Mode</h3>
              <div className="agent-now-segmented" role="group" aria-label="Mission Mode">
                {allowedModes.map((m) => (
                  <button
                    key={m}
                    className={`btn-sm agent-mode-segment ${m === mode ? 'active' : ''}`}
                    disabled={busy}
                    onClick={() => void applyMode(m)}
                  >
                    {MODE_LABELS[m] ?? m}
                  </button>
                ))}
              </div>
              <span className="agent-now-mode">{MODE_LABELS[mode]}</span>
            </div>
          </section>
        </section>

        <section className="codex-chat-shell agent-workspace-shell apple-clean-shell">
          <aside className="codex-thread-list agent-thread-rail">
            <h3>Work</h3>
            <p className="hint">Threads</p>
            <input value={threadQuery} onChange={(e) => setThreadQuery(e.target.value)} placeholder="Search threads..." />
            <div className="codex-thread-list-inner">
              {visibleThreads.length === 0 ? (
                <p className="hint">No threads yet.</p>
              ) : (
                visibleThreads.slice(0, 24).map((t) => (
                  <div key={t.id} className={`thread-row ${threadId === t.id ? 'active' : ''}`}>
                    <button
                      className={`codex-thread-item ${threadId === t.id ? 'active' : ''}`}
                      onClick={() => void selectThread(t.id)}
                      disabled={busy}
                    >
                      <span className="thread-summary">
                        {(threadTitleOverrides[t.id] || t.title || 'Untitled').trim()}
                        {t.preview ? ` - ${t.preview.trim()}` : ''}
                      </span>
                      <small className="thread-updated">{formatUpdated(t.updated_at)}</small>
                    </button>
                    <span className="thread-actions">
                      <button type="button" className="btn-sm" onClick={() => togglePinThread(t.id)} disabled={busy}>
                        {pinnedThreadIds.includes(t.id) ? 'Unpin' : 'Pin'}
                      </button>
                      <button type="button" className="btn-sm" onClick={() => renameThread(t.id)} disabled={busy}>
                        Rename
                      </button>
                    </span>
                  </div>
                ))
              )}
            </div>
          </aside>

          <div className="agent-chat-main">
            <div className="agent-chat-head">
              <h3>Chat</h3>
              <div className="agent-chat-head-right">
                <div className="agent-head-mode-picker" role="group" aria-label="Mission Mode Quick Switch">
                  {allowedModes.map((m) => (
                    <button
                      key={`head-${m}`}
                      type="button"
                      className={`btn-sm agent-mode-segment ${m === mode ? 'active' : ''}`}
                      disabled={busy}
                      onClick={() => void applyMode(m)}
                      title={`Switch to ${MODE_LABELS[m] ?? m}`}
                    >
                      {MODE_LABELS[m] ?? m}
                    </button>
                  ))}
                </div>
                <div className="agent-density-toggle" role="group" aria-label="Response Detail">
                  <button
                    type="button"
                    className={`btn-sm ${responseDensity === 'compact' ? 'btn-arm' : ''}`}
                    onClick={() => setResponseDensity('compact')}
                  >
                    Compact
                  </button>
                  <button
                    type="button"
                    className={`btn-sm ${responseDensity === 'detailed' ? 'btn-arm' : ''}`}
                    onClick={() => setResponseDensity('detailed')}
                  >
                    Detailed
                  </button>
                </div>
                <span className={`agent-state-pill req-state-${requestState}`}>{requestStateLabel}</span>
              </div>
            </div>
            <div className="codex-chat-log" aria-live="polite">
              <div className="codex-chat-log-inner">
                {history.length === 0 ? (
                  <p className="hint">Ask for code changes, telemetry analysis, tuning suggestions, or troubleshooting plans.</p>
                ) : (
                  history.slice(-40).map((item, idx) => (
                    <article key={`${item.ts}-${idx}`} className={`codex-msg ${item.role === 'assistant' ? 'assistant' : 'user'}`}>
                      <div className="codex-msg-meta">{item.role}</div>
                      {item.role === 'assistant' ? (
                        <div className="codex-md">
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {responseDensity === 'compact' ? compactAssistantText(item.text) : normalizeAssistantText(item.text)}
                          </ReactMarkdown>
                        </div>
                      ) : (
                        <pre>{item.text}</pre>
                      )}
                    </article>
                  ))
                )}
              </div>
            </div>

            <div className="codex-send-row agent-send-row">
              <div className="agent-upload-row">
                <input
                  ref={uploadInputRef}
                  type="file"
                  className="agent-upload-input"
                  multiple
                  onChange={(e) => void uploadFiles(e.target.files)}
                />
                <button
                  className="btn-sm agent-upload-btn"
                  type="button"
                  onClick={() => uploadInputRef.current?.click()}
                  disabled={busy}
                  title="Attach csv/txt/.json/images for context"
                >
                  +
                </button>
                {attachments.length > 0 ? (
                  <div className="agent-upload-list">
                    {attachments.map((att, idx) => (
                      <span key={`${att.path || att.name}-${idx}`} className="agent-upload-chip">
                        {att.name}
                        <button type="button" className="btn-sm" onClick={() => removeAttachment(idx)} disabled={busy}>x</button>
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
              <div
                className={`agent-compose-dropzone ${dragActive ? 'is-drag' : ''}`}
                onDragOver={onComposerDragOver}
                onDragEnter={onComposerDragOver}
                onDragLeave={onComposerDragLeave}
                onDrop={onComposerDrop}
              >
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      void send();
                    }
                  }}
                  placeholder="Describe the change or issue..."
                  rows={4}
                  disabled={busy}
                />
              </div>
              <div className="agent-send-actions">
                <button className="codex-send-btn" disabled={busy || !input.trim()} onClick={() => void send()}>
                  {busy ? 'Working...' : 'Send'}
                </button>
                <button className="btn-sm" disabled={!busy} onClick={() => cancelSend()}>Stop</button>
                <button className="btn-sm" disabled={busy || !lastPrompt} onClick={() => void regenerate()}>Regenerate</button>
              </div>
            </div>

            <section className={`agent-details-drawer ${authExpanded ? 'open' : ''}`}>
              <div className="agent-details-head">
                <h3>Details</h3>
                <button className="btn-sm" type="button" onClick={() => setAuthExpanded((v) => !v)}>
                  {authExpanded ? 'Hide' : 'Show'}
                </button>
              </div>
            </section>
            {authExpanded ? (
              <div className="agent-details-popout-wrap" role="dialog" aria-label="Details Popout">
                <button
                  className="agent-details-popout-backdrop"
                  type="button"
                  aria-label="Close details"
                  onClick={() => setAuthExpanded(false)}
                />
                <section className="agent-details-popout">
                  <div className="agent-details-popout-head">
                    <h3>Details</h3>
                    <button className="btn-sm" type="button" onClick={() => setAuthExpanded(false)}>Close</button>
                  </div>
                  <div className="agent-details-body">
                    <section className="agent-details-card">
                      <h4>Login + Provider</h4>
                      <div className="agent-auth-inline">
                        <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" />
                        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="password" />
                        <button className="btn-sm btn-arm" disabled={authBusy} onClick={() => void runAuth()}>{continueLabel}</button>
                      </div>
                      <div className="btn-row">
                        <button className={`btn-sm ${authMode === 'auto' ? 'btn-arm' : ''}`} disabled={authBusy} onClick={() => setAuthMode('auto')}>Auto</button>
                        <button className={`btn-sm ${authMode === 'login' ? 'btn-arm' : ''}`} disabled={authBusy} onClick={() => setAuthMode('login')}>Login</button>
                        <button className={`btn-sm ${authMode === 'register' ? 'btn-arm' : ''}`} disabled={authBusy} onClick={() => setAuthMode('register')}>Register</button>
                        <button className="btn-sm" disabled={authBusy || !user} onClick={() => void runLogout()}>Logout</button>
                      </div>
                      {showApiKeyControls ? (
                        <div className="agent-auth-inline">
                          <input type="password" value={openAiKeyInput} onChange={(e) => setOpenAiKeyInput(e.target.value)} placeholder="OpenAI key (sk-...)" />
                          <input value={openAiModelInput} onChange={(e) => setOpenAiModelInput(e.target.value)} placeholder="model (gpt-5-codex)" />
                          <button className="btn-sm" disabled={authBusy || !user} onClick={() => void saveOpenAi()}>Save</button>
                        </div>
                      ) : (
                        <p className="hint">Using Codex local session login. No API key needed for agent chat.</p>
                      )}
                    </section>
                    <section className="agent-details-card">
                      <h4>Execution Rail</h4>
                      {toolCalls.length === 0 ? (
                        <p className="hint">No tool calls in latest response.</p>
                      ) : (
                        toolCalls.map((call, idx) => (
                          <article key={`${call.tool}-${idx}`} className="codex-thread-item">
                            <strong>{call.tool}</strong>
                            <span>{toolSummary(call)}</span>
                          </article>
                        ))
                      )}
                    </section>
                  </div>
                </section>
              </div>
            ) : null}
          </div>
        </section>
      </div>
    </section>
  );
}
