import { useEffect, useRef, useState, useCallback, type KeyboardEvent as ReactKeyboardEvent } from 'react';
import type { AiHistoryItem, AiProfile, AiStatus, AiThreadSummary, AuthUser } from '../../api';
import { aiConfirmUpload } from '../../api';
import { strings } from '../../strings';
import { ToolCallList } from './ToolCallCard';
import { UploadConfirmModal, extractPendingUpload, type PendingUpload } from './UploadConfirmModal';
import { RagStatusBadge } from './RagStatusBadge';

type Props = {
  bridgeReady: boolean;
  authUser: AuthUser | null;
  ai: AiStatus;
  authAlert: { tone: 'error' | 'ok'; text: string } | null;
  authMode: 'login' | 'register';
  setAuthMode: (mode: 'login' | 'register') => void;
  setAuthAlert: (alert: { tone: 'error' | 'ok'; text: string } | null) => void;
  authEmail: string;
  setAuthEmail: (value: string) => void;
  authPassword: string;
  setAuthPassword: (value: string) => void;
  authBusy: boolean;
  submitAuth: () => Promise<void>;
  openAiKeyInput: string;
  setOpenAiKeyInput: (value: string) => void;
  openAiModelInput: string;
  setOpenAiModelInput: (value: string) => void;
  saveUserOpenAiKey: () => Promise<void>;
  clearUserOpenAiKey: () => Promise<void>;
  runLogout: () => Promise<void>;
  aiHistory: AiHistoryItem[];
  aiThreads: AiThreadSummary[];
  aiActiveThreadId: string | null;
  aiProfiles: AiProfile[];
  aiActiveProfileId: string | null;
  aiProfileLabelInput: string;
  setAiProfileLabelInput: (value: string) => void;
  aiProfileDescriptionInput: string;
  setAiProfileDescriptionInput: (value: string) => void;
  aiProfileInstructionsInput: string;
  setAiProfileInstructionsInput: (value: string) => void;
  aiProfileAllowAutoApplyInput: boolean;
  setAiProfileAllowAutoApplyInput: (value: boolean) => void;
  refreshAiProfiles: () => Promise<void>;
  saveAiProfile: () => Promise<void>;
  activateAiProfile: (profileId: string) => Promise<void>;
  aiInput: string;
  setAiInput: (value: string) => void;
  aiBusy: boolean;
  aiBusyDetail: string | null;
  sendAi: () => Promise<void>;
  refreshThreads: () => Promise<void>;
  startNewChat: () => Promise<void>;
  selectChatThread: (threadId: string) => Promise<void>;
  requestPasswordReset: (email: string) => Promise<{ accepted: boolean; delivery: string; reset_token: string | null; expires_in_s: number }>;
  confirmPasswordReset: (email: string, token: string, newPassword: string) => Promise<void>;
};

export function CodexPanel(props: Props) {
  const {
    bridgeReady,
    authUser,
    ai,
    authAlert,
    authMode,
    setAuthMode,
    setAuthAlert,
    authEmail,
    setAuthEmail,
    authPassword,
    setAuthPassword,
    authBusy,
    submitAuth,
    openAiKeyInput,
    setOpenAiKeyInput,
    openAiModelInput,
    setOpenAiModelInput,
    saveUserOpenAiKey,
    clearUserOpenAiKey,
    runLogout,
    aiHistory,
    aiThreads,
    aiActiveThreadId,
    aiProfiles,
    aiActiveProfileId,
    refreshAiProfiles,
    activateAiProfile,
    aiInput,
    setAiInput,
    aiBusy,
    aiBusyDetail,
    sendAi,
    refreshThreads,
    startNewChat,
    selectChatThread,
    requestPasswordReset,
    confirmPasswordReset,
  } = props;
  const [showResetForm, setShowResetForm] = useState(false);
  const [resetEmail, setResetEmail] = useState('');
  const [resetToken, setResetToken] = useState('');
  const [resetPassword, setResetPassword] = useState('');
  const [resetBusy, setResetBusy] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [showProfilePicker, setShowProfilePicker] = useState(false);
  const [profileBusy, setProfileBusy] = useState(false);
  const [thinkingLines, setThinkingLines] = useState<string[]>([]);
  const [pendingUpload, setPendingUpload] = useState<PendingUpload | null>(null);
  const [networkError, setNetworkError] = useState<string | null>(null);
  const chatLogRef = useRef<HTMLDivElement | null>(null);
  const composerRef = useRef<HTMLTextAreaElement | null>(null);

  // Network connectivity check - detect disconnects
  useEffect(() => {
    const checkOnline = () => {
      if (!navigator.onLine) {
        setNetworkError('Network disconnected. Check your connection.');
      } else {
        setNetworkError(null);
      }
    };

    checkOnline();
    window.addEventListener('online', checkOnline);
    window.addEventListener('offline', checkOnline);

    return () => {
      window.removeEventListener('online', checkOnline);
      window.removeEventListener('offline', checkOnline);
    };
  }, []);

  // Clear network error when bridge reconnects
  useEffect(() => {
    if (bridgeReady && networkError) {
      setNetworkError(null);
    }
  }, [bridgeReady, networkError]);

  // Detect pending upload from latest assistant message
  useEffect(() => {
    const lastAssistant = [...aiHistory].reverse().find((m) => m.role === 'assistant');
    if (!lastAssistant?.meta?.tool_calls) return;
    const pending = extractPendingUpload(lastAssistant.meta.tool_calls);
    if (pending && pending.confirmation_token !== pendingUpload?.confirmation_token) {
      setPendingUpload(pending);
    }
  }, [aiHistory, pendingUpload?.confirmation_token]);

  const handleUploadApprove = useCallback(async (token: string) => {
    const result = await aiConfirmUpload(token, 'approve');
    if (result.ok && result.action === 'approved') {
      return { ok: result.upload_result?.ok ?? false, error: result.upload_result?.error };
    }
    return { ok: false, error: result.error || 'Upload failed' };
  }, []);

  const handleUploadReject = useCallback(() => {
    setPendingUpload(null);
  }, []);

  const runRequestReset = async () => {
    setResetBusy(true);
    try {
      const out = await requestPasswordReset(resetEmail || authEmail);
      if (out.reset_token) setResetToken(out.reset_token);
      setAuthAlert({ tone: 'ok', text: out.reset_token ? 'Reset code generated. Paste or verify the token, then set a new password.' : 'If this account exists, reset instructions are ready.' });
    } catch (e) {
      setAuthAlert({ tone: 'error', text: `Password reset request failed: ${(e as Error).message}` });
    } finally {
      setResetBusy(false);
    }
  };

  const runConfirmReset = async () => {
    setResetBusy(true);
    try {
      await confirmPasswordReset(resetEmail || authEmail, resetToken, resetPassword);
      setResetPassword('');
      setShowResetForm(false);
    } catch (e) {
      setAuthAlert({ tone: 'error', text: `Password reset failed: ${(e as Error).message}` });
    } finally {
      setResetBusy(false);
    }
  };

  const keyConfigured = Boolean(authUser?.openai_configured || ai.configured);
  const settingsVisible = !keyConfigured || showSettings;

  const handleSaveKey = async () => {
    await saveUserOpenAiKey();
    setShowSettings(false);
  };

  const handleDeleteKey = async () => {
    await clearUserOpenAiKey();
    setShowSettings(true);
  };

  const openProfilePicker = async () => {
    setShowProfilePicker(true);
    try {
      await refreshAiProfiles();
    } catch {
      // keep modal open even if refresh fails
    }
  };

  const runActivateProfile = async (profileId: string) => {
    if (!profileId || profileBusy) return;
    setProfileBusy(true);
    try {
      await activateAiProfile(profileId);
      await refreshAiProfiles();
      setShowProfilePicker(false);
    } finally {
      setProfileBusy(false);
    }
  };

  useEffect(() => {
    if (!chatLogRef.current) return;
    chatLogRef.current.scrollTop = chatLogRef.current.scrollHeight;
  }, [aiActiveThreadId, aiHistory]);

  useEffect(() => {
    if (!aiBusy || !chatLogRef.current) return;
    // Keep viewport pinned to latest live progress lines while assistant is working.
    chatLogRef.current.scrollTop = chatLogRef.current.scrollHeight;
  }, [aiBusy, thinkingLines]);

  useEffect(() => {
    if (!aiBusy) {
      setThinkingLines([]);
      return;
    }
    setThinkingLines((prev) => (prev.length ? prev : ['Preparing request...']));
  }, [aiBusy]);

  const formatClock = (ts?: number) => (ts ? new Date(ts).toLocaleTimeString() : 'n/a');
  const pendingSentAt = [...aiHistory].reverse().find((m) => m.role === 'user')?.meta?.sent_at;

  useEffect(() => {
    if (!aiBusy || !aiBusyDetail) return;
    setThinkingLines((prev) => {
      if (prev[prev.length - 1] === aiBusyDetail) return prev;
      return [...prev, aiBusyDetail].slice(-6);
    });
  }, [aiBusy, aiBusyDetail]);

  useEffect(() => {
    if (!aiBusy) return;
    const tick = window.setInterval(() => {
      const elapsedMs = pendingSentAt ? Math.max(0, Date.now() - pendingSentAt) : 0;
      const elapsedS = (elapsedMs / 1000).toFixed(1);
      const heartbeat = `Still working (${elapsedS}s)...`;
      setThinkingLines((prev) => {
        if (prev[prev.length - 1] === heartbeat) return prev;
        return [...prev, heartbeat].slice(-6);
      });
    }, 3500);
    return () => window.clearInterval(tick);
  }, [aiBusy, pendingSentAt]);

  const autoSizeComposer = useCallback(() => {
    const el = composerRef.current;
    if (!el || el.classList.contains('collapsing')) return;
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight}px`;
  }, []);

  useEffect(() => {
    autoSizeComposer();
  }, [aiInput, autoSizeComposer]);

  const handleSend = useCallback(async () => {
    if (!bridgeReady || aiBusy || !aiInput.trim()) return;
    const el = composerRef.current;
    if (el) {
      el.classList.add('collapsing');
      el.style.height = `${el.scrollHeight}px`;
      window.requestAnimationFrame(() => {
        if (composerRef.current) composerRef.current.style.height = '64px';
      });
    }
    try {
      await sendAi();
    } finally {
      window.setTimeout(() => {
        if (!composerRef.current) return;
        composerRef.current.classList.remove('collapsing');
        autoSizeComposer();
      }, 220);
    }
  }, [aiBusy, aiInput, autoSizeComposer, bridgeReady, sendAi]);

  const handleInputChange = useCallback((value: string) => {
    setAiInput(value);
    window.requestAnimationFrame(() => autoSizeComposer());
  }, [autoSizeComposer, setAiInput]);

  const handleComposerKeyDown = useCallback((e: ReactKeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
    }
  }, [handleSend]);

  return (
    <section className="panel tool-panel codex-panel" aria-label="Codex assistant">
      <div className="tool-panel-head">
        <h3>{strings.codex.title}</h3>
        <span className="workflow-label">{strings.codex.subtitle}</span>
      </div>
      <div className="tool-panel-body codex-panel-body">
        <section className="firmware-pane codex-pane">
          <div className="codex-status-row">
            <span className={`hud-pill ${bridgeReady ? 'good' : 'bad'}`}>
              {bridgeReady ? strings.codex.bridgeOnline : strings.codex.bridgeOffline}
            </span>
            <span className={`hud-pill ${authUser ? 'good' : 'bad'}`}>
              {authUser ? strings.codex.accountLoggedIn : strings.codex.accountLoggedOut}
            </span>
            <span className={`hud-pill ${ai.configured ? 'good' : 'warn'}`}>
              {ai.configured ? strings.codex.keySynced : strings.codex.keyMissing}
            </span>
            <span className="hud-pill unknown">{strings.codex.model} {authUser?.openai_model ?? ai.model ?? 'n/a'}</span>
            <RagStatusBadge authReady={Boolean(authUser)} />
          </div>
          {networkError && (
            <div className="codex-network-banner">
              <span className="codex-network-icon">⚠</span>
              <span>{networkError}</span>
            </div>
          )}
          {authAlert && <p className={`auth-alert ${authAlert.tone}`}>{authAlert.text}</p>}
          {!authUser && (
            <>
              <p className="wizard-subtitle">{strings.codex.signinPrompt}</p>
              <div className="row">
                <button
                  className={authMode === 'login' ? 'active btn-secondary btn-sm' : 'btn-secondary btn-sm'}
                  onClick={() => {
                    setAuthMode('login');
                    setAuthAlert(null);
                  }}
                >
                  {strings.codex.login}
                </button>
                <button
                  className={authMode === 'register' ? 'active btn-secondary btn-sm' : 'btn-secondary btn-sm'}
                  onClick={() => {
                    setAuthMode('register');
                    setAuthAlert(null);
                  }}
                >
                  {strings.codex.register}
                </button>
              </div>
              <label>
                {strings.codex.email}
                <input
                  type="email"
                  value={authEmail}
                  onChange={(e) => setAuthEmail(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && bridgeReady) void submitAuth();
                  }}
                />
              </label>
              <label>
                {strings.codex.password}
                <input
                  type="password"
                  value={authPassword}
                  onChange={(e) => setAuthPassword(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && bridgeReady) void submitAuth();
                  }}
                />
              </label>
              <button className="btn-primary btn-lg" disabled={authBusy || !bridgeReady} onClick={() => void submitAuth()}>
                {authBusy ? strings.codex.working : authMode === 'login' ? strings.codex.login : strings.codex.createAccount}
              </button>
              <div className="row">
                <button
                  className="btn-secondary btn-sm"
                  onClick={() => setShowResetForm((v) => !v)}
                >
                  {strings.codex.forgotPassword}
                </button>
              </div>
              {showResetForm && (
                <>
                  <label>
                    {strings.codex.resetEmail}
                    <input
                      type="email"
                      value={resetEmail}
                      onChange={(e) => setResetEmail(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') void runRequestReset();
                      }}
                    />
                  </label>
                  <div className="row">
                    <button className="btn-secondary btn-sm" disabled={resetBusy} onClick={() => void runRequestReset()}>{strings.codex.requestResetCode}</button>
                  </div>
                  <label>
                    {strings.codex.resetToken}
                    <input type="text" value={resetToken} onChange={(e) => setResetToken(e.target.value)} />
                  </label>
                  <label>
                    {strings.codex.newPassword}
                    <input
                      type="password"
                      value={resetPassword}
                      onChange={(e) => setResetPassword(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') void runConfirmReset();
                      }}
                    />
                  </label>
                  <div className="row">
                    <button className="btn-primary btn-lg" disabled={resetBusy || !resetToken || !resetPassword} onClick={() => void runConfirmReset()}>{strings.codex.applyPasswordReset}</button>
                    <button className="btn-secondary btn-sm" disabled={resetBusy} onClick={() => setShowResetForm(false)}>{strings.codex.closeReset}</button>
                  </div>
                </>
              )}
            </>
          )}

          {authUser && (
            <>
              <div className="row">
                {keyConfigured && (
                  <button className="btn-secondary btn-sm" onClick={() => setShowSettings((v) => !v)}>
                    {showSettings ? strings.codex.closeSettings : strings.codex.settings}
                  </button>
                )}
                <button className="btn-secondary btn-sm" onClick={() => void openProfilePicker()}>
                  {strings.codex.assistantProfile}
                </button>
                <button className="btn-secondary btn-sm" onClick={() => setShowHistory((v) => !v)}>
                  {showHistory ? strings.codex.hideLastChats : strings.codex.revealLastChats}
                </button>
                <button className="btn-secondary btn-sm" onClick={() => void runLogout()}>{strings.codex.logout}</button>
              </div>

              {settingsVisible && (
                <>
                  <div className="grid2">
                    <label>
                      {strings.codex.openAiApiKey}
                      <input
                        type="password"
                        value={openAiKeyInput}
                        onChange={(e) => setOpenAiKeyInput(e.target.value)}
                        placeholder="sk-..."
                      />
                    </label>
                    <label>
                      {strings.codex.model}
                      <input value={openAiModelInput} onChange={(e) => setOpenAiModelInput(e.target.value)} />
                    </label>
                  </div>
                  <div className="row">
                    <button className="btn-primary btn-lg" onClick={() => void handleSaveKey()}>{strings.codex.saveKey}</button>
                    <button className="btn-danger btn-md" onClick={() => void handleDeleteKey()}>{strings.codex.deleteKey}</button>
                  </div>
                </>
              )}

              {showHistory && (
                <div className="codex-history-block">
                  <div className="row">
                    <button className="btn-primary btn-sm" onClick={() => void startNewChat()}>{strings.codex.startNewChat}</button>
                    <button className="btn-secondary btn-sm" onClick={() => void refreshThreads()}>{strings.tune.refresh}</button>
                  </div>
                  <div className="codex-thread-list">
                    <p className="wizard-subtitle">{strings.codex.recentChats}</p>
                    {aiThreads.length === 0 && <p className="wizard-subtitle">{strings.codex.noChatHistory}</p>}
                    {aiThreads.map((thread) => (
                      <button
                        key={thread.id}
                        className={`codex-thread-item ${aiActiveThreadId === thread.id ? 'active' : ''}`}
                        onClick={() => void selectChatThread(thread.id)}
                      >
                        <span>{thread.title || 'New Chat'}</span>
                        <small>{thread.message_count} msgs</small>
                      </button>
                    ))}
                  </div>
                </div>
              )}
              <div className="codex-chat-shell">
                <div className="codex-chat-log" ref={chatLogRef}>
                  <div className="codex-chat-log-inner">
                    {aiHistory.length === 0 && <p className="wizard-subtitle">{strings.codex.noChatHistory}</p>}
                    {aiHistory.map((m, idx) => (
                      <div key={`${m.ts}-${idx}`} className={`codex-msg ${m.role}`}>
                        <span className="codex-role">{m.role}</span>
                        {m.role === 'assistant' && m.meta?.tool_calls && m.meta.tool_calls.length > 0 && (
                          <ToolCallList toolCalls={m.meta.tool_calls} />
                        )}
                        <pre>{m.text}</pre>
                        {m.role === 'assistant' && m.meta?.request_ms !== undefined && (
                          <div className="codex-msg-meta">
                            sent {formatClock(m.meta.sent_at)} · done {formatClock(m.meta.done_at)} · first-byte {m.meta.first_byte_ms != null ? `${(m.meta.first_byte_ms / 1000).toFixed(2)}s` : 'n/a'} · {(m.meta.request_ms / 1000).toFixed(2)}s
                          </div>
                        )}
                      </div>
                    ))}
                    {aiBusy && (
                      <div className="codex-msg assistant thinking">
                        <span className="codex-role">assistant</span>
                        <div className="codex-thinking-stream" aria-live="polite">
                          {thinkingLines.map((line, idx) => (
                            <p key={`${idx}-${line}`}>{line}</p>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
                <div className="row serial-send-row codex-send-row">
                  <textarea
                    ref={composerRef}
                    value={aiInput}
                    onChange={(e) => handleInputChange(e.target.value)}
                    placeholder={strings.codex.chatPlaceholder}
                    onKeyDown={handleComposerKeyDown}
                  />
                  <button className="codex-send-btn" disabled={!ai.configured || aiBusy || !bridgeReady} onClick={() => void handleSend()}>
                    ↑
                  </button>
                </div>
                {!bridgeReady && <p className="wizard-subtitle">{strings.codex.bridgeWaitHint}</p>}
                {!ai.configured && <p className="wizard-subtitle">{strings.codex.enableChatHint}</p>}
              </div>
            </>
          )}
        </section>
      </div>
      {authUser && showProfilePicker && (
        <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Assistant profile selector">
          <div className="preflight-modal codex-profile-modal">
            <h3>{strings.codex.assistantProfile}</h3>
            <p className="wizard-subtitle">{strings.codex.profileLockedHint}</p>
            <div className="codex-profile-list">
              {aiProfiles.length === 0 && <p className="wizard-subtitle">{strings.codex.noProfiles}</p>}
              {aiProfiles.map((p) => {
                const active = p.profile_id === aiActiveProfileId;
                return (
                  <div key={p.profile_id} className={`codex-profile-item ${active ? 'active' : ''}`}>
                    <div className="codex-profile-item-body">
                      <p><strong>{p.label}</strong>{active ? ' (active)' : ''}</p>
                      {p.description ? <p className="wizard-subtitle">{p.description}</p> : null}
                    </div>
                    <button className="btn-primary btn-sm" disabled={active || profileBusy} onClick={() => void runActivateProfile(p.profile_id)}>
                      {active ? 'Active' : strings.codex.activateProfile}
                    </button>
                  </div>
                );
              })}
            </div>
            <div className="row">
              <button className="btn-secondary btn-sm" disabled={profileBusy} onClick={() => void refreshAiProfiles()}>{strings.tune.refresh}</button>
              <button className="btn-secondary btn-sm" disabled={profileBusy} onClick={() => setShowProfilePicker(false)}>{strings.modal.cancel}</button>
            </div>
          </div>
        </div>
      )}
      {pendingUpload && (
        <UploadConfirmModal
          pending={pendingUpload}
          onApprove={handleUploadApprove}
          onReject={handleUploadReject}
        />
      )}
    </section>
  );
}
