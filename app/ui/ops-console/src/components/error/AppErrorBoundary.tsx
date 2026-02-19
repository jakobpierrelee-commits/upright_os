import type { ErrorInfo, ReactNode } from 'react';
import { Component } from 'react';

type Props = {
  children: ReactNode;
};

type State = {
  hasError: boolean;
  message: string;
};

export class AppErrorBoundary extends Component<Props, State> {
  public constructor(props: Props) {
    super(props);
    this.state = { hasError: false, message: '' };
  }

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, message: error.message || 'Unknown render error' };
  }

  public componentDidCatch(error: Error, info: ErrorInfo): void {
    // Keep failure details in console for local debugging.
    // eslint-disable-next-line no-console
    console.error('AppErrorBoundary caught error', error, info);
  }

  public render(): ReactNode {
    if (!this.state.hasError) return this.props.children;
    return (
      <main className="app-fallback" role="alert" aria-live="assertive">
        <h1>UpRight.os Console Error</h1>
        <p>The UI hit an unexpected render error and stopped safely.</p>
        <p>{this.state.message}</p>
        <button onClick={() => window.location.reload()}>Reload Console</button>
      </main>
    );
  }
}
