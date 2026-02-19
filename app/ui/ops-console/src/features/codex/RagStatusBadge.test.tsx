import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { RagStatusBadge } from './RagStatusBadge';

const mockRagStats = {
  doc_chunk_count: 42,
  embedded_docs_count: 8,
  embedding_model: 'text-embedding-3-small',
  chunk_size: 1500,
  has_openai_key: true,
};

vi.mock('../../api', () => ({
  aiRagStats: vi.fn(),
}));

import { aiRagStats } from '../../api';

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

  it('shows warning state when no OpenAI key', async () => {
    vi.mocked(aiRagStats).mockResolvedValue({
      ...mockRagStats,
      has_openai_key: false,
    });
    render(<RagStatusBadge authReady={true} />);

    await waitFor(() => {
      expect(screen.getByText('RAG ○ 42')).toBeInTheDocument();
    });

    const badge = screen.getByText('RAG ○ 42');
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

  it('includes stats details in tooltip', async () => {
    vi.mocked(aiRagStats).mockResolvedValue(mockRagStats);
    render(<RagStatusBadge authReady={true} />);

    await waitFor(() => {
      const badge = screen.getByText('RAG ✓ 42');
      const title = badge.getAttribute('title') ?? '';
      expect(title).toContain('8 docs');
      expect(title).toContain('42 chunks');
      expect(title).toContain('text-embedding-3-small');
      expect(title).toContain('1500');
    });
  });
});
