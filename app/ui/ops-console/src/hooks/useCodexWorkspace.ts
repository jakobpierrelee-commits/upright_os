import { useCallback, useMemo, useReducer } from 'react';
import {
  aiChat,
  aiChatWithTools,
  aiProfileActivate,
  aiProfiles,
  aiProfileSave,
  aiStatus,
  aiNewThread,
  aiSelectThread,
  aiThreads,
  authConfirmPasswordReset,
  authDeleteOpenAiKey,
  authLogin,
  authLogout,
  authMe,
  authRequestPasswordReset,
  authRegister,
  authSetOpenAiKey,
  setSessionToken,
} from '../api';
import { codexReducer, initialCodexState } from '../features/codex/codexReducer';

const SESSION_STORAGE_KEY = 'upright.session_token';

function readSessionToken(): string {
  try {
    return localStorage.getItem(SESSION_STORAGE_KEY) ?? '';
  } catch {
    return '';
  }
}

function persistSessionToken(token: string): void {
  try {
    if (token) localStorage.setItem(SESSION_STORAGE_KEY, token);
    else localStorage.removeItem(SESSION_STORAGE_KEY);
  } catch {
    // ignore storage errors
  }
}

function attachAssistantTiming(
  history: import('../api').AiHistoryItem[],
  sentAt: number,
  doneAt: number,
  firstByteMs: number | null,
): import('../api').AiHistoryItem[] {
  const requestMs = Math.max(0, doneAt - sentAt);
  const next = [...history];
  for (let i = next.length - 1; i >= 0; i -= 1) {
    if (next[i].role === 'assistant') {
      next[i] = {
        ...next[i],
        meta: {
          ...(next[i].meta ?? {}),
          sent_at: sentAt,
          done_at: doneAt,
          request_ms: requestMs,
          first_byte_ms: firstByteMs,
        },
      };
      break;
    }
  }
  return next;
}

function attachAssistantApply(
  history: import('../api').AiHistoryItem[],
  apply: {
    ok: boolean;
    snapshot_id?: string;
    applied?: string[];
    status?: import('../types').Status;
    error?: string;
    artifacts?: {
      unified_folder?: string;
      unified_archive?: string;
      unified_main_file?: string;
      sketch_path?: string;
      sketch_backup?: string;
      sketch_bytes?: number;
    };
  } | undefined,
): import('../api').AiHistoryItem[] {
  if (!apply) return history;
  const next = [...history];
  for (let i = next.length - 1; i >= 0; i -= 1) {
    if (next[i].role === 'assistant') {
      next[i] = {
        ...next[i],
        meta: {
          ...(next[i].meta ?? {}),
          apply,
        },
      };
      break;
    }
  }
  return next;
}

export function useCodexWorkspace(onMessage: (text: string) => void) {
  const [state, dispatch] = useReducer(codexReducer, initialCodexState);

  const setAuthMode = useCallback((mode: 'login' | 'register') => dispatch({ type: 'set_auth_mode', payload: mode }), []);
  const setAuthAlert = useCallback((alert: { tone: 'error' | 'ok'; text: string } | null) => dispatch({ type: 'set_auth_alert', payload: alert }), []);
  const setAuthEmail = useCallback((value: string) => dispatch({ type: 'set_auth_email', payload: value }), []);
  const setAuthPassword = useCallback((value: string) => dispatch({ type: 'set_auth_password', payload: value }), []);
  const setOpenAiKeyInput = useCallback((value: string) => dispatch({ type: 'set_openai_key_input', payload: value }), []);
  const setOpenAiModelInput = useCallback((value: string) => dispatch({ type: 'set_openai_model_input', payload: value }), []);
  const setAiInput = useCallback((value: string) => dispatch({ type: 'set_ai_input', payload: value }), []);
  const setAiProfileLabelInput = useCallback((value: string) => dispatch({ type: 'set_ai_profile_label_input', payload: value }), []);
  const setAiProfileDescriptionInput = useCallback((value: string) => dispatch({ type: 'set_ai_profile_description_input', payload: value }), []);
  const setAiProfileInstructionsInput = useCallback((value: string) => dispatch({ type: 'set_ai_profile_instructions_input', payload: value }), []);
  const setAiProfileAllowAutoApplyInput = useCallback((value: boolean) => dispatch({ type: 'set_ai_profile_allow_auto_apply_input', payload: value }), []);

  const refreshAi = useCallback(async () => {
    try {
      const r = await aiStatus();
      dispatch({ type: 'set_ai', payload: r.ai });
      dispatch({ type: 'set_ai_history', payload: r.history });
      dispatch({ type: 'set_ai_threads', payload: r.threads });
      dispatch({ type: 'set_ai_active_thread', payload: r.ai.active_thread_id ?? null });
    } catch {
      dispatch({ type: 'set_ai', payload: { configured: false, model: 'unknown', history_len: 0 } });
      dispatch({ type: 'set_ai_history', payload: [] });
      dispatch({ type: 'set_ai_threads', payload: [] });
      dispatch({ type: 'set_ai_active_thread', payload: null });
    }
  }, []);

  const refreshAiProfiles = useCallback(async () => {
    try {
      const p = await aiProfiles();
      dispatch({ type: 'set_ai_profiles', payload: p.profiles });
      dispatch({ type: 'set_ai_active_profile', payload: p.active_profile_id ?? null });
      const active = p.profiles.find((x) => x.profile_id === p.active_profile_id) ?? p.profiles[0];
      if (active) {
        dispatch({ type: 'set_ai_profile_label_input', payload: active.label ?? '' });
        dispatch({ type: 'set_ai_profile_description_input', payload: active.description ?? '' });
        dispatch({ type: 'set_ai_profile_instructions_input', payload: active.instructions ?? '' });
        dispatch({ type: 'set_ai_profile_allow_auto_apply_input', payload: Boolean(active.policy?.allow_auto_apply ?? true) });
      }
    } catch {
      dispatch({ type: 'set_ai_profiles', payload: [] });
      dispatch({ type: 'set_ai_active_profile', payload: null });
    }
  }, []);

  const bootstrap = useCallback(async () => {
    const storedToken = readSessionToken();
    if (storedToken) setSessionToken(storedToken);
    try {
      const me = await authMe();
      dispatch({ type: 'set_auth_user', payload: me });
      dispatch({ type: 'set_openai_model_input', payload: me.openai_model ?? 'gpt-5-mini' });
    } catch {
      setSessionToken('');
      persistSessionToken('');
      dispatch({ type: 'set_auth_user', payload: null });
    }
    await refreshAi();
    await refreshAiProfiles();
  }, [refreshAi, refreshAiProfiles]);

  const submitAuth = useCallback(async () => {
    dispatch({ type: 'set_auth_busy', payload: true });
    try {
      const email = state.authEmail.trim();
      const password = state.authPassword;
      const r = state.authMode === 'login'
        ? await authLogin(email, password)
        : await authRegister(email, password);
      setSessionToken(r.session_token);
      persistSessionToken(r.session_token);
      dispatch({ type: 'set_auth_user', payload: r.user });
      dispatch({ type: 'set_auth_alert', payload: { tone: 'ok', text: state.authMode === 'login' ? 'Login successful' : 'Account created' } });
      dispatch({ type: 'set_openai_model_input', payload: r.user.openai_model ?? 'gpt-5-mini' });
      dispatch({ type: 'set_auth_password', payload: '' });
      onMessage('Codex account authenticated');
      await refreshAi();
    } catch (e) {
      dispatch({ type: 'set_auth_alert', payload: { tone: 'error', text: `Auth error: ${(e as Error).message}` } });
    } finally {
      dispatch({ type: 'set_auth_busy', payload: false });
    }
  }, [onMessage, refreshAi, state.authEmail, state.authMode, state.authPassword]);

  const saveUserOpenAiKey = useCallback(async () => {
    try {
      const key = state.openAiKeyInput.trim();
      if (!key) {
        dispatch({ type: 'set_auth_alert', payload: { tone: 'error', text: 'OpenAI key is required' } });
        return;
      }
      const model = state.openAiModelInput.trim() || 'gpt-5-mini';
      const out = await authSetOpenAiKey(key, model);
      dispatch({ type: 'set_ai', payload: { ...state.ai, configured: out.configured, model: out.model } });
      dispatch({ type: 'patch_auth_user', payload: { openai_configured: out.configured, openai_model: out.model } });
      dispatch({ type: 'set_openai_key_input', payload: '' });
      dispatch({ type: 'set_auth_alert', payload: { tone: 'ok', text: `OpenAI key saved (${out.model})` } });
      onMessage('OpenAI key saved');
      await refreshAi();
      await refreshAiProfiles();
    } catch (e) {
      dispatch({ type: 'set_auth_alert', payload: { tone: 'error', text: `OpenAI key save error: ${(e as Error).message}` } });
    }
  }, [onMessage, refreshAi, refreshAiProfiles, state.ai, state.openAiKeyInput, state.openAiModelInput]);

  const clearUserOpenAiKey = useCallback(async () => {
    try {
      const out = await authDeleteOpenAiKey();
      dispatch({ type: 'set_ai', payload: { ...state.ai, configured: out.configured, model: out.model ?? state.ai.model } });
      dispatch({ type: 'patch_auth_user', payload: { openai_configured: out.configured, openai_model: out.model } });
      dispatch({ type: 'set_auth_alert', payload: { tone: 'ok', text: 'OpenAI key deleted' } });
      onMessage('OpenAI key deleted');
      await refreshAi();
      await refreshAiProfiles();
    } catch (e) {
      dispatch({ type: 'set_auth_alert', payload: { tone: 'error', text: `Delete key error: ${(e as Error).message}` } });
    }
  }, [onMessage, refreshAi, refreshAiProfiles, state.ai]);

  const runLogout = useCallback(async () => {
    try {
      await authLogout();
    } catch {
      // ignore server-side logout failures; always clear local session
    }
    setSessionToken('');
    persistSessionToken('');
    dispatch({ type: 'set_auth_user', payload: null });
    dispatch({ type: 'set_ai_history', payload: [] });
    dispatch({ type: 'set_ai_threads', payload: [] });
    dispatch({ type: 'set_ai_active_thread', payload: null });
    dispatch({ type: 'set_ai_profiles', payload: [] });
    dispatch({ type: 'set_ai_active_profile', payload: null });
    dispatch({ type: 'set_auth_alert', payload: { tone: 'ok', text: 'Logged out' } });
    onMessage('Codex logged out');
    await refreshAi();
    await refreshAiProfiles();
  }, [onMessage, refreshAi, refreshAiProfiles]);

  const sendAi = useCallback(async () => {
    const message = state.aiInput.trim();
    if (!message) return;
    const sentAt = Date.now();
    const previousHistory = state.aiHistory;
    const shouldLogAiTurn = import.meta.env.DEV || (() => {
      try {
        return localStorage.getItem('upright.ai.debug') === '1';
      } catch {
        return false;
      }
    })();
    if (shouldLogAiTurn) {
      const lastTwo = previousHistory.slice(-2).map((m) => ({ role: m.role, text: m.text }));
      console.info('[codex.sendAi][request]', {
        thread_id: state.aiActiveThreadId ?? null,
        message_count: previousHistory.length,
        last_two_messages: lastTwo,
      });
    }
    const optimisticHistory = [...state.aiHistory, { ts: sentAt, role: 'user' as const, text: message, meta: { sent_at: sentAt } }];
    dispatch({ type: 'set_ai_history', payload: optimisticHistory });
    dispatch({ type: 'set_ai_input', payload: '' });
    dispatch({ type: 'set_ai_busy', payload: true });
    dispatch({ type: 'set_ai_busy_detail', payload: 'Sending tool-enabled request...' });
    try {
      dispatch({ type: 'set_ai_busy_detail', payload: 'Waiting for model response...' });
      let r = await aiChatWithTools(message, {
        threadId: state.aiActiveThreadId ?? undefined,
        enableTools: true,
      });
      let toolCalls: import('../api').ToolCallResult[] = r.tool_calls ?? [];
      let iterations = r.iterations ?? 1;
      dispatch({ type: 'set_ai_busy_detail', payload: `Response received (${toolCalls.length} tool call${toolCalls.length === 1 ? '' : 's'}).` });

      // Keep chat functional even when bridge tool support is temporarily unavailable.
      if (!r.reply && !r.history.length) {
        dispatch({ type: 'set_ai_busy_detail', payload: 'Tool mode unavailable. Retrying with standard chat...' });
        const fallback = await aiChat(message, state.aiActiveThreadId ?? undefined);
        r = {
          ...fallback,
          tool_calls: [],
          iterations: 1,
        };
        toolCalls = [];
        iterations = 1;
      }

      dispatch({ type: 'set_ai_busy_detail', payload: 'Applying assistant response to thread...' });
      const doneAt = Date.now();
      const timed = attachAssistantTiming(r.history, sentAt, doneAt, null);
      dispatch({ type: 'set_ai_history', payload: timed });
      dispatch({ type: 'set_ai', payload: r.ai });
      dispatch({ type: 'set_ai_threads', payload: r.threads });
      dispatch({ type: 'set_ai_active_thread', payload: r.thread_id ?? r.ai.active_thread_id ?? state.aiActiveThreadId ?? null });
      if (shouldLogAiTurn) {
        const lastTwo = timed.slice(-2).map((m) => ({ role: m.role, text: m.text }));
        console.info('[codex.sendAi][response]', {
          thread_id: r.thread_id ?? r.ai.active_thread_id ?? null,
          message_count: timed.length,
          last_two_messages: lastTwo,
        });
      }
      if (Array.isArray(toolCalls) && toolCalls.length > 0) {
        onMessage(`Codex tools executed: ${toolCalls.length}`);
      } else if (iterations === 1) {
        // no-op; keeps noisy status to minimum
      }
    } catch (e) {
      const errMsg = (e as Error).message || String(e);
      dispatch({ type: 'set_ai_busy_detail', payload: `Request failed: ${errMsg}` });
      if (errMsg.includes('tool_support_not_available')) {
        try {
          dispatch({ type: 'set_ai_busy_detail', payload: 'Tool support unavailable. Falling back to standard chat...' });
          const fallback = await aiChat(message, state.aiActiveThreadId ?? undefined);
          const doneAt = Date.now();
          const timed = attachAssistantTiming(fallback.history, sentAt, doneAt, null);
          dispatch({ type: 'set_ai_history', payload: timed });
          dispatch({ type: 'set_ai', payload: fallback.ai });
          dispatch({ type: 'set_ai_threads', payload: fallback.threads });
          dispatch({ type: 'set_ai_active_thread', payload: fallback.thread_id ?? fallback.ai.active_thread_id ?? state.aiActiveThreadId ?? null });
          onMessage('Codex tool mode unavailable; sent via standard chat.');
          return;
        } catch {
          // fall through to existing error handling below
        }
      }
      dispatch({ type: 'set_ai_history', payload: previousHistory });
      dispatch({ type: 'set_ai_input', payload: message });
      if (shouldLogAiTurn) {
        console.warn('[codex.sendAi][error]', {
          thread_id: state.aiActiveThreadId ?? null,
          error: errMsg,
        });
      }
      if (errMsg.includes('thread_not_found')) {
        onMessage('Codex thread expired or missing. Resynced threads; please retry.');
        try {
          await refreshAi();
        } catch {
          // keep local state if refresh fails
        }
      } else {
        onMessage(`Codex chat error: ${errMsg}`);
      }
    } finally {
      dispatch({ type: 'set_ai_busy', payload: false });
      dispatch({ type: 'set_ai_busy_detail', payload: null });
    }
  }, [onMessage, refreshAi, state.aiActiveThreadId, state.aiHistory, state.aiInput]);

  const refreshThreads = useCallback(async () => {
    const r = await aiThreads();
    dispatch({ type: 'set_ai_threads', payload: r.threads });
    dispatch({ type: 'set_ai', payload: r.ai });
    dispatch({ type: 'set_ai_active_thread', payload: r.ai.active_thread_id ?? state.aiActiveThreadId ?? null });
  }, [state.aiActiveThreadId]);

  const saveAiProfile = useCallback(async () => {
    const label = state.aiProfileLabelInput.trim();
    const instructions = state.aiProfileInstructionsInput.trim();
    if (!label || !instructions) {
      dispatch({ type: 'set_auth_alert', payload: { tone: 'error', text: 'Profile label and instructions are required' } });
      return;
    }
    const out = await aiProfileSave({
      profile_id: state.aiActiveProfileId ?? undefined,
      label,
      description: state.aiProfileDescriptionInput.trim(),
      instructions,
      policy: { allow_auto_apply: state.aiProfileAllowAutoApplyInput },
    });
    dispatch({ type: 'set_ai_profiles', payload: out.profiles });
    dispatch({ type: 'set_ai_active_profile', payload: out.active_profile_id ?? null });
    dispatch({ type: 'set_auth_alert', payload: { tone: 'ok', text: 'Assistant profile saved' } });
  }, [
    state.aiActiveProfileId,
    state.aiProfileAllowAutoApplyInput,
    state.aiProfileDescriptionInput,
    state.aiProfileInstructionsInput,
    state.aiProfileLabelInput,
  ]);

  const activateAiProfile = useCallback(async (profileId: string) => {
    const out = await aiProfileActivate(profileId);
    dispatch({ type: 'set_ai_profiles', payload: out.profiles });
    dispatch({ type: 'set_ai_active_profile', payload: out.active_profile_id ?? null });
    const active = out.profiles.find((p) => p.profile_id === profileId);
    if (active) {
      dispatch({ type: 'set_ai_profile_label_input', payload: active.label ?? '' });
      dispatch({ type: 'set_ai_profile_description_input', payload: active.description ?? '' });
      dispatch({ type: 'set_ai_profile_instructions_input', payload: active.instructions ?? '' });
      dispatch({ type: 'set_ai_profile_allow_auto_apply_input', payload: Boolean(active.policy?.allow_auto_apply ?? true) });
    }
    dispatch({ type: 'set_auth_alert', payload: { tone: 'ok', text: 'Assistant profile activated' } });
  }, []);

  const startNewChat = useCallback(async () => {
    const r = await aiNewThread();
    dispatch({ type: 'set_ai', payload: r.ai });
    dispatch({ type: 'set_ai_threads', payload: r.threads });
    dispatch({ type: 'set_ai_history', payload: r.history });
    dispatch({ type: 'set_ai_active_thread', payload: r.thread.id });
  }, []);

  const selectChatThread = useCallback(async (threadId: string) => {
    const r = await aiSelectThread(threadId);
    dispatch({ type: 'set_ai', payload: r.ai });
    dispatch({ type: 'set_ai_threads', payload: r.threads });
    dispatch({ type: 'set_ai_history', payload: r.history });
    dispatch({ type: 'set_ai_active_thread', payload: r.thread.id });
  }, []);

  const requestPasswordReset = useCallback(async (email: string) => {
    const out = await authRequestPasswordReset(email.trim());
    return out;
  }, []);

  const confirmPasswordReset = useCallback(async (email: string, token: string, newPassword: string) => {
    await authConfirmPasswordReset(email.trim(), token.trim(), newPassword);
    dispatch({ type: 'set_auth_mode', payload: 'login' });
    dispatch({ type: 'set_auth_alert', payload: { tone: 'ok', text: 'Password reset complete. Log in with your new password.' } });
  }, []);

  return useMemo(() => ({
    state,
    actions: {
      bootstrap,
      submitAuth,
      saveUserOpenAiKey,
      clearUserOpenAiKey,
      runLogout,
      sendAi,
      setAuthMode,
      setAuthAlert,
      setAuthEmail,
      setAuthPassword,
      setOpenAiKeyInput,
      setOpenAiModelInput,
      setAiInput,
      setAiProfileLabelInput,
      setAiProfileDescriptionInput,
      setAiProfileInstructionsInput,
      setAiProfileAllowAutoApplyInput,
      requestPasswordReset,
      confirmPasswordReset,
      refreshThreads,
      refreshAiProfiles,
      saveAiProfile,
      activateAiProfile,
      startNewChat,
      selectChatThread,
    },
  }), [activateAiProfile, bootstrap, clearUserOpenAiKey, confirmPasswordReset, refreshAiProfiles, refreshThreads, requestPasswordReset, runLogout, saveAiProfile, saveUserOpenAiKey, selectChatThread, sendAi, setAiInput, setAiProfileAllowAutoApplyInput, setAiProfileDescriptionInput, setAiProfileInstructionsInput, setAiProfileLabelInput, setAuthAlert, setAuthEmail, setAuthMode, setAuthPassword, setOpenAiKeyInput, setOpenAiModelInput, startNewChat, state, submitAuth]);
}
