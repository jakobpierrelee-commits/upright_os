import { BOARD_PROFILES, DEFAULT_BOARD_PROFILE_ID } from './boardRegistry';
import type { BoardProfile, BoardResolution } from './types';

function scoreProfile(profile: BoardProfile, key: string): number {
  if (!key) return 0;
  let score = 0;
  const id = profile.id.toLowerCase();
  const fqbn = profile.fqbn.toLowerCase();
  const label = profile.label.toLowerCase();
  const aliases = profile.aliases.map((a) => a.toLowerCase());
  if (key === id) score += 100;
  if (key === fqbn) score += 100;
  if (key === label) score += 80;
  if (aliases.includes(key)) score += 85;
  if (key.includes(id)) score += 44;
  if (key.includes(fqbn)) score += 40;
  if (label.includes(key)) score += 28;
  if (aliases.some((a) => key.includes(a))) score += 36;
  if (profile.family === 'esp32' && key.includes('esp32')) score += 10;
  if (profile.family === 'teensy' && key.includes('teensy')) score += 10;
  if (profile.family === 'arduino' && (key.includes('arduino') || key.includes('nano') || key.includes('uno'))) score += 8;
  return score;
}

export function resolveBoardProfile(fqbnOrGuess: string): BoardResolution {
  const key = (fqbnOrGuess ?? '').trim().toLowerCase();
  const fallback =
    BOARD_PROFILES.find((p) => p.id === DEFAULT_BOARD_PROFILE_ID) ??
    BOARD_PROFILES[0];
  if (!key) {
    return {
      profile: fallback,
      confidence: 0.2,
      ambiguous: false,
      reason: 'empty_input_fallback',
      candidates: [{ id: fallback.id, label: fallback.label, score: 0 }],
    };
  }
  const scored = BOARD_PROFILES
    .map((p) => ({ profile: p, score: scoreProfile(p, key) }))
    .sort((a, b) => b.score - a.score);
  const best = scored[0] ?? { profile: fallback, score: 0 };
  const second = scored[1] ?? null;
  const ambiguous = Boolean(second && best.score > 0 && second.score >= best.score - 8);
  const confidence = Math.max(0, Math.min(1, best.score / 100));
  const reason = best.score >= 80 ? 'high_confidence_match' : best.score >= 40 ? 'partial_match' : 'low_confidence_fallback';
  return {
    profile: best.profile,
    confidence,
    ambiguous,
    reason,
    candidates: scored.slice(0, 3).map((x) => ({ id: x.profile.id, label: x.profile.label, score: x.score })),
  };
}

export function inferBoardProfile(fqbnOrGuess: string): BoardProfile {
  return resolveBoardProfile(fqbnOrGuess).profile;
}

export function pinNumberFromLabel(label: string): number | null {
  const m = label
    .toUpperCase()
    .match(/(?:^|[^A-Z0-9])(D?|GPIO|IO)(\d{1,2})(?:$|[^A-Z0-9])/);
  if (!m) return null;
  const n = Number.parseInt(m[2], 10);
  return Number.isFinite(n) ? n : null;
}
