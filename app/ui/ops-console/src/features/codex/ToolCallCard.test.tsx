import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ToolCallCard, ToolCallList, type ToolCallResult } from './ToolCallCard';

const mockSuccessToolCall: ToolCallResult = {
  tool: 'query_telemetry',
  args: { limit: 10, robot_id: 'bot-001' },
  result: {
    ok: true,
    tool: 'query_telemetry',
    data: { rows: [{ ts: 1234567890, angle: 1.5 }], count: 1 },
    execution_time_ms: 42,
  },
};

const mockErrorToolCall: ToolCallResult = {
  tool: 'execute_command',
  args: { command: 'ARM' },
  result: {
    ok: false,
    tool: 'execute_command',
    data: {},
    error: 'Command ARM is blocked for safety reasons',
    execution_time_ms: 5,
  },
};

const mockFlashToolCall: ToolCallResult = {
  tool: 'upload_firmware',
  args: { sketch_path: '/path/to/sketch', board: 'arduino:avr:nano' },
  result: {
    ok: true,
    tool: 'upload_firmware',
    data: { requires_confirmation: true, token: 'abc123' },
    execution_time_ms: 150,
  },
};

const mockEmptyArgsToolCall: ToolCallResult = {
  tool: 'get_probe_results',
  args: {},
  result: {
    ok: true,
    tool: 'get_probe_results',
    data: { compat: null, connect: null },
    execution_time_ms: 12,
  },
};

const mockLongJsonToolCall: ToolCallResult = {
  tool: 'search_docs',
  args: { query: 'This is a very long search query that should be truncated in the summary view to prevent overflow issues' },
  result: {
    ok: true,
    tool: 'search_docs',
    data: {
      chunks: [
        { text: 'Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.', score: 0.95 },
        { text: 'Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.', score: 0.87 },
      ],
    },
    execution_time_ms: 234,
  },
};

const mockToolCallWithReasoning: ToolCallResult = {
  tool: 'query_telemetry',
  args: { limit: 5 },
  result: {
    ok: true,
    tool: 'query_telemetry',
    data: { rows: [], count: 0 },
    execution_time_ms: 18,
  },
  reasoning: 'I need to check the recent telemetry data to understand the current robot state before making tuning recommendations.',
};

describe('ToolCallCard', () => {
  it('renders success tool call with correct badge and status', () => {
    render(<ToolCallCard toolCall={mockSuccessToolCall} />);
    
    expect(screen.getByText('query_telemetry')).toBeInTheDocument();
    expect(screen.getByText('read')).toBeInTheDocument();
    expect(screen.getByText('✓')).toBeInTheDocument();
    expect(screen.getByText('42ms')).toBeInTheDocument();
  });

  it('renders error tool call with error status and styling', () => {
    render(<ToolCallCard toolCall={mockErrorToolCall} />);
    
    expect(screen.getByText('execute_command')).toBeInTheDocument();
    expect(screen.getByText('write')).toBeInTheDocument();
    expect(screen.getByText('✗')).toBeInTheDocument();
    
    const card = screen.getByRole('article');
    expect(card.className).toContain('status-error');
    expect(card.className).toContain('category-write');
  });

  it('applies correct badge color for read tools (blue)', () => {
    render(<ToolCallCard toolCall={mockSuccessToolCall} />);
    
    const badge = screen.getByText('read');
    expect(badge.className).toContain('read');
  });

  it('applies correct badge color for write tools (amber)', () => {
    render(<ToolCallCard toolCall={mockErrorToolCall} />);
    
    const badge = screen.getByText('write');
    expect(badge.className).toContain('write');
  });

  it('applies correct badge color for flash tools (red)', () => {
    render(<ToolCallCard toolCall={mockFlashToolCall} />);
    
    const badge = screen.getByText('flash');
    expect(badge.className).toContain('flash');
  });

  it('expands and collapses on click', () => {
    render(<ToolCallCard toolCall={mockSuccessToolCall} />);
    
    // Initially collapsed - no details visible
    expect(screen.queryByText('Arguments')).not.toBeInTheDocument();
    
    // Click to expand
    const header = screen.getByRole('button');
    fireEvent.click(header);
    
    // Now details should be visible
    expect(screen.getByText('Arguments')).toBeInTheDocument();
    expect(screen.getByText('Result')).toBeInTheDocument();
    
    // Click to collapse
    fireEvent.click(header);
    expect(screen.queryByText('Arguments')).not.toBeInTheDocument();
  });

  it('shows error message when expanded for error tool call', () => {
    render(<ToolCallCard toolCall={mockErrorToolCall} />);
    
    const header = screen.getByRole('button');
    fireEvent.click(header);
    
    expect(screen.getByText('Error')).toBeInTheDocument();
    expect(screen.getByText('Command ARM is blocked for safety reasons')).toBeInTheDocument();
  });

  it('handles missing/empty args gracefully', () => {
    render(<ToolCallCard toolCall={mockEmptyArgsToolCall} />);
    
    // Summary should show "(no args)"
    expect(screen.getByText('(no args)')).toBeInTheDocument();
    
    // Expand to see fallback
    const header = screen.getByRole('button');
    fireEvent.click(header);
    
    expect(screen.getByText('(no arguments)')).toBeInTheDocument();
  });

  it('truncates long args in summary without overflow', () => {
    render(<ToolCallCard toolCall={mockLongJsonToolCall} />);
    
    // The args summary should be truncated
    const summary = screen.getByText(/query=This is a very long/);
    expect(summary.textContent?.endsWith('…')).toBe(true);
    expect(summary.textContent?.length).toBeLessThanOrEqual(61); // 60 chars + ellipsis
  });

  it('renders JSON blocks with correct class for overflow handling', () => {
    render(<ToolCallCard toolCall={mockLongJsonToolCall} defaultExpanded />);
    
    const jsonBlocks = document.querySelectorAll('.tool-call-json');
    expect(jsonBlocks.length).toBeGreaterThan(0);
    jsonBlocks.forEach((block) => {
      expect(block.classList.contains('tool-call-json')).toBe(true);
    });
  });

  it('starts expanded when defaultExpanded is true', () => {
    render(<ToolCallCard toolCall={mockSuccessToolCall} defaultExpanded />);
    
    expect(screen.getByText('Arguments')).toBeInTheDocument();
  });

  it('shows reasoning when present and expanded', () => {
    render(<ToolCallCard toolCall={mockToolCallWithReasoning} defaultExpanded />);
    
    expect(screen.getByText('Why this tool?')).toBeInTheDocument();
    expect(screen.getByText(/I need to check the recent telemetry/)).toBeInTheDocument();
  });

  it('does not show reasoning section when reasoning is not present', () => {
    render(<ToolCallCard toolCall={mockSuccessToolCall} defaultExpanded />);
    
    expect(screen.queryByText('Why this tool?')).not.toBeInTheDocument();
  });

  it('does not show reasoning when collapsed even if present', () => {
    render(<ToolCallCard toolCall={mockToolCallWithReasoning} />);
    
    // Collapsed by default
    expect(screen.queryByText('Why this tool?')).not.toBeInTheDocument();
  });
});

describe('ToolCallList', () => {
  it('renders multiple tool calls', () => {
    render(<ToolCallList toolCalls={[mockSuccessToolCall, mockErrorToolCall, mockFlashToolCall]} />);
    
    expect(screen.getByText('query_telemetry')).toBeInTheDocument();
    expect(screen.getByText('execute_command')).toBeInTheDocument();
    expect(screen.getByText('upload_firmware')).toBeInTheDocument();
  });

  it('returns null for empty array', () => {
    const { container } = render(<ToolCallList toolCalls={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it('returns null for undefined', () => {
    const { container } = render(<ToolCallList toolCalls={undefined as unknown as ToolCallResult[]} />);
    expect(container.firstChild).toBeNull();
  });
});
