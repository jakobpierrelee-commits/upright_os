type Props = {
  comm: { state: string; running: boolean; returncode: number | null; log_tail: string[] };
  commArtifacts: { latest_metrics: string | null; latest_run: string | null };
  estopLatched: boolean;
  runFull: () => Promise<void>;
  refreshStatus: () => Promise<void>;
};

export function CommissionPage({ comm, commArtifacts, estopLatched, runFull, refreshStatus }: Props) {
  return (
    <section>
      <h2>Commissioning</h2>
      <div className="row">
        <button disabled={comm.running || estopLatched} onClick={() => void runFull()}>
          Run Full (Auto)
        </button>
        <button onClick={() => void refreshStatus()}>
          Refresh Status
        </button>
      </div>
      <p>State: <strong>{comm.state}</strong> running={comm.running ? 'yes' : 'no'} return={String(comm.returncode)}</p>
      <p>Latest metrics: {commArtifacts.latest_metrics ?? 'n/a'}</p>
      <p>Latest run: {commArtifacts.latest_run ?? 'n/a'}</p>
      <pre className="logbox">{comm.log_tail.join('\n')}</pre>
    </section>
  );
}
