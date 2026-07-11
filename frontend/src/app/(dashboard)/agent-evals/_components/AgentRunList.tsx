import { RefreshCcw, Radio } from 'lucide-react';
import type { AgentEvalRunSummary } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { agentEvalStatusLabel, formatAgentEvalTime } from '../_utils';

type AgentRunListProps = {
  runs: AgentEvalRunSummary[];
  selectedRunId: string | null;
  isLoading: boolean;
  isFetching: boolean;
  onSelectRun: (agentRunId: string) => void;
  onRefresh: () => void;
};

function statusBadgeClass(status: string) {
  if (status === 'running') return 'border-blue-500/30 bg-blue-500/10 text-blue-700 dark:text-blue-300';
  if (status === 'completed') return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300';
  if (status === 'failed' || status === 'error') return 'border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-300';
  return 'border-muted-foreground/20 bg-muted text-muted-foreground';
}

export function AgentRunList({
  runs,
  selectedRunId,
  isLoading,
  isFetching,
  onSelectRun,
  onRefresh,
}: AgentRunListProps) {
  return (
    <aside className="flex min-h-[260px] flex-col border-b lg:min-h-0 lg:border-b-0 lg:border-r">
      <div className="flex items-center justify-between gap-3 border-b px-4 py-3">
        <div>
          <div className="text-sm font-medium">最近 Agent Runs</div>
          <div className="text-xs text-muted-foreground">运行中优先，最多 20 条</div>
        </div>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          onClick={onRefresh}
          title="刷新运行列表"
        >
          <RefreshCcw className={cn('h-4 w-4', isFetching && 'animate-spin')} />
        </Button>
      </div>

      <ScrollArea className="min-h-0 flex-1">
        <div className="space-y-2 p-3">
          {isLoading &&
            Array.from({ length: 4 }).map((_, index) => (
              <div key={index} className="rounded-md border p-3">
                <Skeleton className="h-4 w-32" />
                <Skeleton className="mt-2 h-3 w-full" />
                <Skeleton className="mt-2 h-3 w-24" />
              </div>
            ))}

          {!isLoading && runs.length === 0 && (
            <div className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
              暂无 Agent Run。启动一次任务后，这里会显示运行评估入口。
            </div>
          )}

          {!isLoading &&
            runs.map((run) => {
              const selected = selectedRunId === run.agent_run_id;
              return (
                <button
                  key={run.agent_run_id}
                  type="button"
                  onClick={() => onSelectRun(run.agent_run_id)}
                  className={cn(
                    'w-full rounded-md border p-3 text-left transition-colors hover:bg-muted/50',
                    selected && 'border-primary bg-primary/5',
                  )}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium">
                        {run.thread_name || run.thread_id}
                      </div>
                      <div className="mt-1 truncate font-mono text-[11px] text-muted-foreground">
                        {run.agent_run_id}
                      </div>
                    </div>
                    <Badge variant="outline" className={statusBadgeClass(run.status)}>
                      {agentEvalStatusLabel(run.status)}
                    </Badge>
                  </div>
                  <div className="mt-3 flex items-center gap-2 text-xs text-muted-foreground">
                    <Radio className={cn('h-3.5 w-3.5', run.is_active && 'text-emerald-500')} />
                    <span>{run.summary}</span>
                  </div>
                  <div className="mt-2 text-xs text-muted-foreground">
                    更新于 {formatAgentEvalTime(run.updated_at || run.started_at)}
                  </div>
                </button>
              );
            })}
        </div>
      </ScrollArea>
    </aside>
  );
}
