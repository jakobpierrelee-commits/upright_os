import React, { Suspense, lazy } from 'react';
import ReactDOM from 'react-dom/client';
import CleanApp from './CleanApp';
import './styles.css';
import './styles/themes.css';
import { AppErrorBoundary } from './components/error/AppErrorBoundary';

const LegacyApp = lazy(async () => await import('./App'));

const legacyEnabled = (() => {
  if ((import.meta.env.VITE_LEGACY_CONSOLE as string | undefined) === '1') return true;
  return false;
})();

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <AppErrorBoundary>
      {legacyEnabled ? (
        <Suspense fallback={<div style={{ padding: 12 }}>Loading legacy console...</div>}>
          <LegacyApp />
        </Suspense>
      ) : (
        <CleanApp />
      )}
    </AppErrorBoundary>
  </React.StrictMode>,
);
