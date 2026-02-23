import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import CleanApp from './CleanApp';
import './styles.css';
import './styles/themes.css';
import { AppErrorBoundary } from './components/error/AppErrorBoundary';

const legacyEnabled = (() => {
  if ((import.meta.env.VITE_LEGACY_CONSOLE as string | undefined) === '1') return true;
  return false;
})();

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <AppErrorBoundary>
      {legacyEnabled ? <App /> : <CleanApp />}
    </AppErrorBoundary>
  </React.StrictMode>,
);
