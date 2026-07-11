import { AlertCircle, CheckCircle2, Circle } from 'lucide-react';
import type { AgentEvalTimelineItem } from '@/lib/api';
import { ScrollArea } from '@/components/ui/scroll-area';
import { cn } from '@/lib/utils';
import { formatAgentEvalTime } from '../_utils';

type AgentEvalTimelineProps = {
  items: AgentEvalTimelineItem[];
};

function itemTone(status: AgentEvalTimelineItem['status']) {
  if (status === 'fail') return 'text-red-600 dark:text-red-300';
  if (status === 'warn') return 'text-amber-600 dark:text-amber-300';
  return 'text-emerald-600 dark:text-emerald-300';
}

function TimelineIcon({ status }: { status: AgentEvalTimelineItem['status'] }) {
  if (status === 'fail') return <AlertCircle className="h-4 w-4" />;
  if (status === 'warn') return <Circle className="h-4 w-4 fill-current" />;
  return <CheckCircle2 className="h-4 w-4" />;
}

export function AgentEvalTimeline({ items }: AgentEvalTimelineProps) {
  if (items.length === 0) {
    return (
      <section className="rounded-md border p-4 text-sm text-muted-foreground">
        暂无 timeline 节点。
      </section>
    );
  }

  return (
    <section className="rounded-md border">
      <div className="border-b px-4 py-3">
        <h2 className="text-sm font-medium">执行时间线</h2>
      </div>
      <ScrollArea className="max-h-[360px]">
        <div className="space-y-4 p-4">
          {items.slice(0, 50).map((item, index) => (
            <div key={`${item.kind}-${item.time}-${index}`} className="flex gap-3">
              <div className={cn('mt-0.5', itemTone(item.status))}>
                <TimelineIcon status={item.status} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <span className="text-sm font-medium">{item.title}</span>
                  <span className="font-mono text-[11px] text-muted-foreground">{item.source}</span>
                  <span className="text-xs text-muted-foreground">
                    {formatAgentEvalTime(item.time)}
                  </span>
                </div>
                <p className="mt-1 break-words text-xs text-muted-foreground">
                  {item.description}
                </p>
              </div>
            </div>
          ))}
        </div>
      </ScrollArea>
    </section>
  );
}
