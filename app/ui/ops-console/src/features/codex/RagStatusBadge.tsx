import { useEffect, useState, useCallback } from 'react';
import { aiRagIndex, aiRagStats, type RagStats } from '../../api';

type Props = {
  authReady: boolean;
};

function formatFreshness(ts?: number | null): string {
  if (!ts || !Number.isFinite(ts)) return 'never indexed';
  const ageS = Math.max(0, (Date.now() / 1000) - ts);
  if (ageS < 90) return 'fresh (< 1.5m)';
  const mins = ageS / 60;
  if (mins < 120) return `${Math.round(mins)}m ago`;
  const hours = mins / 60;
  if (hours < 72) return `${hours.toFixed(1)}h ago`;
  return `${(hours / 24).toFixed(1)}d ago`;
}

export function RagStatusBadge({ authReady }: Props) {
  const [stats, setStats] = useState<RagStats | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [panelOpen, setPanelOpen] = useState(false);
  const [indexing, setIndexing] = useState(false);
  const [notice, setNotice] = useState<string>('');

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

  if (error && !stats) {
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
  const title = `${stats.embedded_docs_count} docs / ${stats.doc_chunk_count} chunks\nModel: ${stats.embedding_model}\nChunk size: ${stats.chunk_size}\nFreshness: ${formatFreshness(stats.latest_embedding_ts)}`;

  const runReindex = async () => {
    if (indexing) return;
    setIndexing(true);
    setNotice('');
    setError(null);
    try {
      const out = await aiRagIndex({ force_reindex: true });
      const docs = out.docs.files_processed + out.sketches.files_processed;
      const chunks = out.docs.chunks_created + out.sketches.chunks_created;
      setNotice(`Reindex complete: ${docs} files, ${chunks} chunks (${Math.round(out.elapsed_ms)}ms)`);
      await fetchStats();
    } catch (e) {
      setError((e as Error).message ?? 'reindex_failed');
    } finally {
      setIndexing(false);
    }
  };

  return (
    <div className="rag-status-wrap">
      <button
        type="button"
        className={`hud-pill rag-pill-btn ${tone}`}
        title={title}
        onClick={() => setPanelOpen((v) => !v)}
        aria-expanded={panelOpen}
        aria-label="RAG status panel"
      >
        RAG {ready ? '✓' : '○'} {stats.doc_chunk_count}
      </button>
      {panelOpen && (
        <div className="rag-status-panel" role="dialog" aria-label="RAG indexing status">
          <p><strong>Docs:</strong> {stats.embedded_docs_count}</p>
          <p><strong>Chunks:</strong> {stats.doc_chunk_count}</p>
          <p><strong>Model:</strong> {stats.embedding_model}</p>
          <p><strong>Chunk Size:</strong> {stats.chunk_size}</p>
          <p><strong>Freshness:</strong> {formatFreshness(stats.latest_embedding_ts)}</p>
          {error && <p><strong>Error:</strong> {error}</p>}
          {notice && <p>{notice}</p>}
          <div className="rag-status-actions">
            <button type="button" className="btn-secondary btn-sm" onClick={() => void fetchStats()} disabled={loading || indexing}>
              Refresh
            </button>
            <button
              type="button"
              className="btn-secondary btn-sm"
              onClick={() => void runReindex()}
              disabled={indexing || !stats.has_openai_key}
              title={!stats.has_openai_key ? 'OpenAI key required for indexing' : 'Reindex docs and sketches'}
            >
              {indexing ? 'Reindexing…' : 'Reindex'}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
