import { describe, expect, it } from 'vitest';
import { BOARD_PROFILES } from './boardRegistry';

describe('boardRegistry assets', () => {
  it('includes official docs links for primary supported boards', () => {
    const required = ['nano', 'nano_esp32', 'uno', 'esp32_devkitc_v4', 'teensy41'];
    for (const id of required) {
      const profile = BOARD_PROFILES.find((p) => p.id === id);
      expect(profile, `missing profile ${id}`).toBeTruthy();
      expect(profile?.assets?.docsUrl, `missing docs URL for ${id}`).toBeTruthy();
    }
  });

  it('keeps asset URLs http(s) when present', () => {
    for (const profile of BOARD_PROFILES) {
      const urls = [
        profile.assets?.docsUrl,
        profile.assets?.pinoutUrl,
        profile.assets?.schematicUrl,
        profile.assets?.cadStepUrl,
        profile.assets?.cad3dUrl,
      ].filter(Boolean) as string[];
      for (const url of urls) {
        expect(/^https?:\/\//.test(url)).toBe(true);
      }
    }
  });
});
