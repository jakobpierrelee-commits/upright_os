import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { RagStatusBadge } from './RagStatusBadge';

const mockRagStats = {
  doc_chunk_count: 42,
  embedded_docs_count: 8,
  embedding_model: 'text-embedding-3-small',
  chunk_size: 1500,
  has_openai_key: true,
  latest_embedding_ts: 1_700_000_000,
};

vi.mock('../../api', () => ({
  aiRagStats: vi.fn(),
  aiRagIndex: vi.fn(),
}));

import { aiRagStats, aiRagIndex } from '../../api';

describe('RagStatusBadge', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when authReady is false', () => {
    const { container } = render(<RagStatusBadge authReady={false} />);
    expect(container.firstChild).toBeNull();
  });

  it('shows loading state initially', () => {
    vi.mocked(aiRagStats).mockImplementation(() => new Promise(() => {}));
    render(<RagStatusBadge authReady={true} />);
    expect(screen.getByText('RAG …')).toBeInTheDocument();
  });

  it('shows ready state with chunk count when RAG is configured', async () => {
    vi.mocked(aiRagStats).mockResolvedValue(mockRagStats);
    render(<RagStatusBadge authReady={true} />);

    await waitFor(() => {
      expect(screen.getByText('RAG ✓ 42')).toBeInTheDocument();
    });

    const badge = screen.getByText('RAG ✓ 42');
    expect(badge.className).toContain('good');
  });

  it('shows warning state when no chunks indexed', async () => {
    vi.mocked(aiRagStats).mockResolvedValue({
      ...mockRagStats,
      doc_chunk_count: 0,
    });
    render(<RagStatusBadge authReady={true} />);

    await waitFor(() => {
      expect(screen.getByText('RAG ○ 0')).toBeInTheDocument();
    });

    const badge = screen.getByText('RAG ○ 0');
    expect(badge.className).toContain('warn');
  });

  it('shows error state on fetch failure', async () => {
    vi.mocked(aiRagStats).mockRejectedValue(new Error('network_error'));
    render(<RagStatusBadge authReady={true} />);

    await waitFor(() => {
      expect(screen.getByText('RAG ⚠')).toBeInTheDocument();
    });

    const badge = screen.getByText('RAG ⚠');
    expect(badge.className).toContain('warn');
    expect(badge.getAttribute('title')).toContain('network_error');
  });

  it('opens panel and shows detailed stats', async () => {
    vi.mocked(aiRagStats).mockResolvedValue(mockRagStats);
    render(<RagStatusBadge authReady={true} />);

    await waitFor(() => {
      expect(screen.getByText('RAG ✓ 42')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('RAG ✓ 42'));

    expect(screen.getByText(/Docs:/)).toBeInTheDocument();
    expect(screen.getByText(/Chunks:/)).toBeInTheDocument();
    expect(screen.getByText(/Freshness:/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Refresh' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reindex' })).toBeInTheDocument();
  });

  it('runs reindex and refreshes stats', async () => {
    vi.mocked(aiRagStats)
      .mockResolvedValueOnce(mockRagStats)
      .mockResolvedValueOnce({ ...mockRagStats, doc_chunk_count: 99, embedded_docs_count: 12 });
    vi.mocked(aiRagIndex).mockResolvedValue({
      docs: { files_processed: 2, files_skipped: 1, chunks_created: 25, errors: [] },
      sketches: { files_processed: 1, files_skipped: 0, chunks_created: 10, errors: [] },
      elapsed_ms: 250,
      ts: 1_700_000_100,
    });

    render(<RagStatusBadge authReady={true} />);

    await waitFor(() => {
      expect(screen.getByText('RAG ✓ 42')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('RAG ✓ 42'));
    fireEvent.click(screen.getByRole('button', { name: 'Reindex' }));

    await waitFor(() => {
      expect(aiRagIndex).toHaveBeenCalled();
      expect(screen.getByText(/Reindex complete:/)).toBeInTheDocument();
    });
  });
});
