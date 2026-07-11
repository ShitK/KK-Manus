'use client';

import {
  AlertCircle,
  Activity,
  Database,
  Radio,
  RefreshCcw,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useAgentRunDiagnosticsQuery } from '@/hooks/react-query/threads/use-agent-run';
import { cn } from '@/lib/utils';

type AgentRunDiagnosticsPanelProps = {
  agentRunId: string | null;
  enabled: boolean;
};

function formatDate(value: string | null) {
  if (!value) return 'not set';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleTimeString();
}

export function AgentRunDiagnosticsPanel({
  agentRunId,
  enabled,
}: AgentRunDiagnosticsPanelProps) {
  const diagnosticsQuery = useAgentRunDiagnosticsQuery(
    agentRunId,
    enabled && !!agentRunId,
  );
  const diagnostics = diagnosticsQuery.data;

  if (!enabled) return null;

  return (
    <div className="mx-auto mb-3 w-full max-w-3xl px-4">
      <div className="rounded-md border border-border bg-background/95 p-3 text-xs shadow-sm">
        <div className="mb-3 flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2 font-medium">
            <Activity className="h-4 w-4 text-muted-foreground" />
            <span>Agent Run Diagnostics</span>
            {agentRunId && (
              <code className="truncate rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">
                {agentRunId}
              </code>
            )}
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-7 w-7"
            onClick={() => {
              void diagnosticsQuery.refetch();
            }}
            disabled={!agentRunId || diagnosticsQuery.isFetching}
            title="Refresh diagnostics"
          >
            <RefreshCcw
              className={cn(
                'h-3.5 w-3.5',
                diagnosticsQuery.isFetching && 'animate-spin',
              )}
            />
          </Button>
        </div>

        {!agentRunId && (
          <div className="text-muted-foreground">No active or recent agent run selected.</div>
        )}

        {agentRunId && diagnosticsQuery.isLoading && (
          <div className="text-muted-foreground">Loading diagnostics...</div>
        )}

        {agentRunId && diagnosticsQuery.isError && (
          <div className="flex items-center gap-2 text-destructive">
            <AlertCircle className="h-4 w-4" />
            <span>Failed to load diagnostics.</span>
          </div>
        )}

        {diagnostics && (
          <div className="grid gap-3 md:grid-cols-3">
            <div className="space-y-1">
              <div className="flex items-center gap-1.5 font-medium">
                <Database className="h-3.5 w-3.5" />
                Run
              </div>
              <div>Status: {diagnostics.agent_run.status}</div>
              <div>Started: {formatDate(diagnostics.agent_run.started_at)}</div>
              <div>Completed: {formatDate(diagnostics.agent_run.completed_at)}</div>
              {diagnostics.agent_run.error && (
                <div className="text-destructive">Error: {diagnostics.agent_run.error}</div>
              )}
            </div>

            <div className="space-y-1">
              <div className="flex items-center gap-1.5 font-medium">
                <Radio className="h-3.5 w-3.5" />
                Stream
              </div>
              <div>Redis responses: {diagnostics.redis.response_count}</div>
              <div>Active keys: {diagnostics.redis.active_instance_keys.length}</div>
              <div>Messages: {diagnostics.messages.total}</div>
              <div>Events: {diagnostics.events.total}</div>
            </div>

            <div className="space-y-1">
              <div className="font-medium">Recent message</div>
              <div className="line-clamp-4 text-muted-foreground">
                {diagnostics.messages.recent[0]?.content_preview || 'No message rows found.'}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
