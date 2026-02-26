import { describe, expect, it } from 'vitest';
import { inferBoardProfile, resolveBoardProfile } from './boardResolver';

describe('boardResolver', () => {
  it('resolves exact fqbn with high confidence', () => {
    const out = resolveBoardProfile('arduino:avr:nano');
    expect(out.profile.id).toBe('nano');
    expect(out.confidence).toBeGreaterThanOrEqual(0.8);
    expect(out.ambiguous).toBe(false);
  });

  it('resolves alias input', () => {
    const out = resolveBoardProfile('teensy4.1');
    expect(out.profile.id).toBe('teensy41');
    expect(out.confidence).toBeGreaterThan(0.5);
  });

  it('marks ambiguous when input is broad family term', () => {
    const out = resolveBoardProfile('esp32');
    expect(out.profile.family).toBe('esp32');
    expect(out.candidates.length).toBeGreaterThanOrEqual(2);
    expect(out.ambiguous).toBe(true);
  });

  it('inferBoardProfile remains backward-compatible', () => {
    const profile = inferBoardProfile('nano every');
    expect(profile.id).toBe('nano_every');
  });
});
