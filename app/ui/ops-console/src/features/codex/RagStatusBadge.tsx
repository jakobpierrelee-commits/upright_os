import { useEffect, useState, useCallback } from 'react';
import { aiRagStats, type RagStats } from '../../api';

type Props = {
  authReady: boolean;
};

export function RagStatusBadge({ authReady }: Props) {
  const [stats, setStats] = useState<RagStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchStats = useCallback(async () => {
    if (!authReady) return;
    setLoading(true);
    setError(null);
    try {
      const s = await aiRagStats();
      setStats(s);
    } catch (e) {
      setError((e as Error).message ?? 'fetch_failed');
      setStats(null);
    } finally {
      setLoading(false);
    }
  }, [authReady]);

  useEffect(() => {
    void fetchStats();
  }, [fetchStats]);

  if (!authReady) {
    return null;
  }

  if (loading && !stats) {
    return <span className="hud-pill unknown">RAG …</span>;
  }

  if (error) {
    return (
      <span className="hud-pill warn" title={`RAG error: ${error}`}>
        RAG ⚠
      </span>
    );
  }

  if (!stats) {
    return <span className="hud-pill unknown">RAG —</span>;
  }

  const ready = stats.doc_chunk_count > 0 && stats.has_openai_key;
  const tone = ready ? 'good' : 'warn';
  const title = `${stats.embedded_docs_count} docs / ${stats.doc_chunk_count} chunks\nModel: ${stats.embedding_model}\nChunk size: ${stats.chunk_size}`;

  return (
    <span className={`hud-pill ${tone}`} title={title}>
      RAG {ready ? '✓' : '○'} {stats.doc_chunk_count}
    </span>
  );
}
