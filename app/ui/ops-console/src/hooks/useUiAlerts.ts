import { useCallback, useEffect, useRef, useState } from 'react';

export type AlertTone = 'error' | 'warn' | 'ok' | 'info';
export type AlertFilter = 'all' | AlertTone;

export type UiAlert = {
  id: string;
  tone: AlertTone;
  text: string;
  ts: number;
  source: string;
};

type TimerMap = Map<string, ReturnType<typeof setTimeout>>;

const ACTIVE_MAX = 12;
const HISTORY_MAX = 50;
const AUTO_DISMISS_MS = 5000;
const DEDUPE_WINDOW_MS = 1500;
const DEFAULT_SOURCE = 'general';

function classifyTone(text: string): AlertTone {
  const lower = text.toLowerCase();
  if (/(error|failed|cannot|invalid|missing|blocked|denied|unknown|latched)/.test(lower)) return 'error';
  if (/(warn|risk|watch)/.test(lower)) return 'warn';
  if (/(ok|pass|saved|loaded|applied|prepared|confirmed|complete|detected|found|synced|removed|deleted|imported|copied|refreshed|started|logged)/.test(lower)) return 'ok';
  return 'info';
}

function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
}

export function useUiAlerts() {
  const [active, setActive] = useState<UiAlert[]>([]);
  const [history, setHistory] = useState<UiAlert[]>([]);
  const [filter, setFilter] = useState<AlertFilter>('all');

  const timersRef = useRef<TimerMap>(new Map());
  const lastPushRef = useRef<{ text: string; at: number }>({ text: '', at: 0 });
  const sourceErrorLocksRef = useRef<Map<string, string>>(new Map());

  const clearTimer = useCallback((id: string) => {
    const timer = timersRef.current.get(id);
    if (timer) {
      clearTimeout(timer);
      timersRef.current.delete(id);
    }
  }, []);

  const moveToHistory = useCallback((id: string) => {
    setActive((prev) => {
      const alert = prev.find((a) => a.id === id);
      if (alert) {
        setHistory((h) => [alert, ...h].slice(0, HISTORY_MAX));
      }
      return prev.filter((a) => a.id !== id);
    });
    clearTimer(id);
  }, [clearTimer]);

  const dismiss = useCallback((id: string) => {
    moveToHistory(id);
  }, [moveToHistory]);

  const unlockSource = useCallback((source: string) => {
    sourceErrorLocksRef.current.delete(source || DEFAULT_SOURCE);
  }, []);

  const pushAlert = useCallback((text: string, tone?: AlertTone, source?: string) => {
    const now = Date.now();
    if (text === lastPushRef.current.text && now - lastPushRef.current.at < DEDUPE_WINDOW_MS) {
      return;
    }
    lastPushRef.current = { text, at: now };

    const resolvedTone = tone ?? classifyTone(text);
    const resolvedSource = (source ?? DEFAULT_SOURCE).trim() || DEFAULT_SOURCE;
    if (resolvedTone === 'error') {
      const lockedText = sourceErrorLocksRef.current.get(resolvedSource);
      if (lockedText === text) return;
      sourceErrorLocksRef.current.set(resolvedSource, text);
    }

    const id = generateId();
    const alert: UiAlert = { id, tone: resolvedTone, text, ts: now, source: resolvedSource };

    setActive((prev) => {
      const next = [alert, ...prev];
      if (next.length > ACTIVE_MAX) {
        const overflow = next.slice(ACTIVE_MAX);
        overflow.forEach((a) => clearTimer(a.id));
        setHistory((h) => [...overflow, ...h].slice(0, HISTORY_MAX));
        return next.slice(0, ACTIVE_MAX);
      }
      return next;
    });

    if (resolvedTone === 'ok' || resolvedTone === 'info') {
      const timer = setTimeout(() => moveToHistory(id), AUTO_DISMISS_MS);
      timersRef.current.set(id, timer);
    }
  }, [clearTimer, moveToHistory]);

  const clearNonError = useCallback(() => {
    setActive((prev) => {
      const toMove = prev.filter((a) => a.tone !== 'error');
      const toKeep = prev.filter((a) => a.tone === 'error');
      toMove.forEach((a) => clearTimer(a.id));
      setHistory((h) => [...toMove, ...h].slice(0, HISTORY_MAX));
      return toKeep;
    });
  }, [clearTimer]);

  const clearAll = useCallback(() => {
    setActive((prev) => {
      prev.forEach((a) => clearTimer(a.id));
      setHistory((h) => [...prev, ...h].slice(0, HISTORY_MAX));
      return [];
    });
  }, [clearTimer]);

  const clearHistory = useCallback(() => {
    setHistory([]);
  }, []);

  useEffect(() => {
    const timers = timersRef.current;
    return () => {
      timers.forEach((timer) => clearTimeout(timer));
      timers.clear();
    };
  }, []);

  const filteredActive = filter === 'all' ? active : active.filter((a) => a.tone === filter);
  const filteredHistory = filter === 'all' ? history : history.filter((a) => a.tone === filter);

  return {
    active: filteredActive,
    history: filteredHistory,
    allActive: active,
    allHistory: history,
    filter,
    setFilter,
    pushAlert,
    unlockSource,
    dismiss,
    clearNonError,
    clearAll,
    clearHistory,
  };
}
