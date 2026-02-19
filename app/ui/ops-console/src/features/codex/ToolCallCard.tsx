import { useState, useCallback } from 'react';

export type ToolCallResult = {
  tool: string;
  args: Record<string, unknown>;
  result: {
    ok: boolean;
    tool: string;
    data: Record<string, unknown>;
    error?: string;
    execution_time_ms: number;
  };
};

type ToolCategory = 'read' | 'write' | 'flash';

const TOOL_CATEGORIES: Record<string, ToolCategory> = {
  get_probe_results: 'read',
  query_telemetry: 'read',
  query_checkpoints: 'read',
  search_docs: 'read',
  execute_command: 'write',
  edit_sketch_value: 'write',
  generate_sketch: 'write',
  compile_firmware: 'write',
  upload_firmware: 'flash',
};

function getToolCategory(tool: string): ToolCategory {
  return TOOL_CATEGORIES[tool] ?? 'read';
}

function truncateArgs(args: Record<string, unknown>, maxLen = 60): string {
  if (!args || Object.keys(args).length === 0) return '(no args)';
  const str = Object.entries(args)
    .map(([k, v]) => `${k}=${typeof v === 'string' ? v : JSON.stringify(v)}`)
    .join(', ');
  return str.length > maxLen ? `${str.slice(0, maxLen - 1)}…` : str;
}

function formatJson(obj: unknown): string {
  try {
    return JSON.stringify(obj, null, 2);
  } catch {
    return String(obj);
  }
}

type Props = {
  toolCall: ToolCallResult;
  defaultExpanded?: boolean;
};

export function ToolCallCard({ toolCall, defaultExpanded = false }: Props) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const toggle = useCallback(() => setExpanded((v) => !v), []);

  const { tool, args, result } = toolCall;
  const category = getToolCategory(tool);
  const ok = result?.ok ?? false;
  const error = result?.error;
  const execTime = result?.execution_time_ms ?? 0;
  const data = result?.data ?? {};

  const hasArgs = args && Object.keys(args).length > 0;
  const hasData = data && Object.keys(data).length > 0;

  return (
    <article
      className={`tool-call-card category-${category} ${ok ? 'status-ok' : 'status-error'}`}
      aria-label={`Tool call: ${tool}`}
    >
      <button
        type="button"
        className="tool-call-header"
        onClick={toggle}
        aria-expanded={expanded}
      >
        <span className={`tool-call-badge ${category}`}>{category}</span>
        <span className="tool-call-name">{tool}</span>
        <span className="tool-call-args-summary">{truncateArgs(args)}</span>
        <span className={`tool-call-status ${ok ? 'ok' : 'error'}`}>
          {ok ? '✓' : '✗'}
        </span>
        <span className="tool-call-time">{execTime.toFixed(0)}ms</span>
        <span className="tool-call-expand-icon">{expanded ? '▾' : '▸'}</span>
      </button>

      {expanded && (
        <div className="tool-call-details">
          {hasArgs && (
            <div className="tool-call-section">
              <span className="tool-call-section-label">Arguments</span>
              <pre className="tool-call-json">{formatJson(args)}</pre>
            </div>
          )}
          {!hasArgs && (
            <div className="tool-call-section">
              <span className="tool-call-section-label">Arguments</span>
              <p className="tool-call-empty">(no arguments)</p>
            </div>
          )}

          {error && (
            <div className="tool-call-section tool-call-error-section">
              <span className="tool-call-section-label">Error</span>
              <p className="tool-call-error-msg">{error}</p>
            </div>
          )}

          {hasData && (
            <div className="tool-call-section">
              <span className="tool-call-section-label">Result</span>
              <pre className="tool-call-json">{formatJson(data)}</pre>
            </div>
          )}
          {!hasData && !error && (
            <div className="tool-call-section">
              <span className="tool-call-section-label">Result</span>
              <p className="tool-call-empty">(no data returned)</p>
            </div>
          )}
        </div>
      )}
    </article>
  );
}

type ToolCallListProps = {
  toolCalls: ToolCallResult[];
};

export function ToolCallList({ toolCalls }: ToolCallListProps) {
  if (!toolCalls || toolCalls.length === 0) return null;

  return (
    <div className="tool-call-list" aria-label="Tool calls executed">
      {toolCalls.map((tc, idx) => (
        <ToolCallCard key={`${tc.tool}-${idx}`} toolCall={tc} />
      ))}
    </div>
  );
}
