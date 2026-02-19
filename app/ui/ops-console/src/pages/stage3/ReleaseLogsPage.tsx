type Props = {
  lines: string[];
  refreshLogs: () => Promise<void>;
};

export function ReleaseLogsPage({ lines, refreshLogs }: Props) {
  return (
    <section>
      <h2>Logs</h2>
      <button onClick={() => void refreshLogs()}>Refresh Lines</button>
      <pre className="logbox">{lines.join('\n')}</pre>
    </section>
  );
}
