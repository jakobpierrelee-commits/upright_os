import { forwardRef } from 'react';
import { CodexPanelClean } from './CodexPanelClean';
import type { CleanGlobalStatusEvent } from './cleanAppTypes';
import type { CleanMode } from './cleanApi';

type CleanCodexSectionProps = {
  mode: CleanMode;
  onGlobalStatus: (evt: CleanGlobalStatusEvent) => void;
};

export const CleanCodexSection = forwardRef<HTMLElement, CleanCodexSectionProps>(
  function CleanCodexSection({ mode, onGlobalStatus }, ref): JSX.Element {
    return (
      <section className="clean-codex" ref={ref}>
        <CodexPanelClean mode={mode} onGlobalStatus={onGlobalStatus} />
      </section>
    );
  },
);
