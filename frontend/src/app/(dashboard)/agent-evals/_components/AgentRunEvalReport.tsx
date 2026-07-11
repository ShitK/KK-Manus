import { Activity, AlertCircle, RefreshCcw } from 'lucide-react';
import type { AgentRunEvalReport as AgentRunEvalReportType } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';
import { formatAgentEvalTime, formatAgentEvalTokenCount } from '../_utils';
import { AgentEvalMetricCard } from './AgentEvalMetricCard';
import { AgentEvalTimeline } from './AgentEvalTimeline';

type AgentRunEvalReportProps = {
  report: AgentRunEvalReportType | undefined;
  isLoading: boolean;
  isFetching: boolean;
  isError: boolean;
  onRefresh: () => void;
};

function overallClass(status: string) {
  if (status === 'healthy') return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300';
  if (status === 'attention') return 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300';
  return 'border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-300';
}

function overallLabel(status: string) {
  if (status === 'healthy') return '健康';
  if (status === 'attention') return '需关注';
  return '失败';
}

export function AgentRunEvalReport({
  report,
  isLoading,
  isFetching,
  isError,
  onRefresh,
}: AgentRunEvalReportProps) {
  if (isLoading) {
    return (
      <section className="min-h-0 overflow-auto p-4 sm:p-6">
        <div className="space-y-4">
          <Skeleton className="h-24 w-full" />
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {Array.from({ length: 6 }).map((_, index) => (
              <Skeleton key={index} className="h-40 w-full" />
            ))}
          </div>
          <Skeleton className="h-56 w-full" />
        </div>
      </section>
    );
  }

  if (isError) {
    return (
      <section className="min-h-0 overflow-auto p-4 sm:p-6">
        <div className="rounded-md border border-red-500/30 p-4 text-sm text-red-700 dark:text-red-300">
          <div className="flex items-center gap-2 font-medium">
            <AlertCircle className="h-4 w-4" />
            评估报告加载失败
          </div>
          <p className="mt-2 text-muted-foreground">请刷新左侧列表后重新选择该 Agent Run。</p>
        </div>
      </section>
    );
  }

  if (!report) {
    return (
      <section className="min-h-0 overflow-auto p-4 sm:p-6">
        <div className="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground">
          请选择一个 Agent Run。
        </div>
      </section>
    );
  }

  const tokenUsage = report.token_usage;
  const tokenModelLabel = tokenUsage.model || tokenUsage.models?.join(', ') || '';

  return (
    <section className="min-h-0 overflow-auto p-4 sm:p-6">
      <div className="space-y-5">
        <section className="rounded-md border p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <Activity className="h-4 w-4 text-primary" />
                <h2 className="text-base font-semibold">运行报告</h2>
                {isFetching && <RefreshCcw className="h-3.5 w-3.5 animate-spin text-muted-foreground" />}
                <button
                  type="button"
                  aria-label="刷新运行报告"
                  title="刷新运行报告"
                  onClick={onRefresh}
                  disabled={isFetching}
                  className={cn(
                    'inline-flex h-7 w-7 items-center justify-center rounded-md border text-muted-foreground transition-colors hover:bg-muted hover:text-foreground',
                    isFetching && 'cursor-not-allowed opacity-60',
                  )}
                >
                  <RefreshCcw className="h-3.5 w-3.5" />
                </button>
              </div>
              <p className="mt-2 text-sm text-muted-foreground">{report.overall.summary}</p>
              <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                <span>Run: {report.run.agent_run_id}</span>
                <span>Thread: {report.run.thread_name || report.run.thread_id}</span>
                <span>更新: {formatAgentEvalTime(report.run.updated_at || report.run.started_at)}</span>
              </div>
            </div>
            <Badge variant="outline" className={overallClass(report.overall.status)}>
              {overallLabel(report.overall.status)}
            </Badge>
          </div>

          <div className="mt-4 grid gap-3 border-t pt-4 sm:grid-cols-3">
            <div>
              <div className="text-xs text-muted-foreground">Token 消耗</div>
              <div className="mt-1 text-2xl font-semibold">
                {formatAgentEvalTokenCount(tokenUsage.total_tokens)}
              </div>
              {tokenUsage.estimated && (
                <Badge variant="outline" className="mt-2 border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300">
                  估算
                </Badge>
              )}
            </div>
            <div className="text-sm">
              <div className="text-xs text-muted-foreground">输入 / 输出</div>
              <div className="mt-2 text-muted-foreground">
                {tokenUsage.available
                  ? `${formatAgentEvalTokenCount(tokenUsage.prompt_tokens)} / ${formatAgentEvalTokenCount(tokenUsage.completion_tokens)}`
                  : tokenUsage.note}
              </div>
            </div>
            <div className="text-sm">
              <div className="text-xs text-muted-foreground">模型</div>
              <div className="mt-2 break-words text-muted-foreground">
                {tokenModelLabel || '-'}
              </div>
            </div>
          </div>

          {report.overall.next_steps.length > 0 && (
            <div className="mt-4 rounded-md bg-muted/60 p-3">
              <div className="text-xs font-medium">下一步建议</div>
              <div className="mt-2 space-y-1 text-xs text-muted-foreground">
                {report.overall.next_steps.map((step, index) => (
                  <div key={`${step}-${index}`}>- {step}</div>
                ))}
              </div>
            </div>
          )}
        </section>

        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {report.metrics.map((metric) => (
            <AgentEvalMetricCard key={metric.id} metric={metric} />
          ))}
        </div>

        <section className="rounded-md border p-4">
          <h2 className="text-sm font-medium">观测计数</h2>
          <div className="mt-3 grid gap-3 text-xs text-muted-foreground sm:grid-cols-5">
            <div>工具: {report.observations.tool_event_count}</div>
            <div>Workflow: {report.observations.workflow_payload_count}</div>
            <div>提醒: {report.observations.warning_count}</div>
            <div>错误: {report.observations.error_count}</div>
            <div>降级: {report.observations.fallback_count}</div>
          </div>
        </section>

        <AgentEvalTimeline items={report.timeline} />
      </div>
    </section>
  );
}
