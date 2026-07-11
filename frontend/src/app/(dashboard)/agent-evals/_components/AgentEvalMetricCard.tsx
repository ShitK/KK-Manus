import {
  AlertTriangle,
  CheckCircle2,
  CircleSlash,
  Info,
} from 'lucide-react';
import type { AgentEvalMetric } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { agentEvalMetricTone, formatAgentEvalBasis } from '../_utils';

type AgentEvalMetricCardProps = {
  metric: AgentEvalMetric;
};

const toneClasses = {
  success: {
    border: 'border-emerald-500/25',
    icon: 'text-emerald-600 dark:text-emerald-300',
    badge: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
  },
  warning: {
    border: 'border-amber-500/30',
    icon: 'text-amber-600 dark:text-amber-300',
    badge: 'border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300',
  },
  danger: {
    border: 'border-red-500/30',
    icon: 'text-red-600 dark:text-red-300',
    badge: 'border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-300',
  },
  muted: {
    border: 'border-border',
    icon: 'text-muted-foreground',
    badge: 'border-muted-foreground/20 bg-muted text-muted-foreground',
  },
};

function MetricIcon({ tone }: { tone: keyof typeof toneClasses }) {
  if (tone === 'success') return <CheckCircle2 className="h-4 w-4" />;
  if (tone === 'warning') return <AlertTriangle className="h-4 w-4" />;
  if (tone === 'danger') return <CircleSlash className="h-4 w-4" />;
  return <Info className="h-4 w-4" />;
}

function statusLabel(status: AgentEvalMetric['status']) {
  if (status === 'pass') return '正常';
  if (status === 'warn') return '需关注';
  if (status === 'fail') return '失败';
  return '不适用';
}

export function AgentEvalMetricCard({ metric }: AgentEvalMetricCardProps) {
  const tone = agentEvalMetricTone(metric.status);
  const classes = toneClasses[tone];

  return (
    <section className={cn('rounded-md border p-4', classes.border)}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <span className={classes.icon}>
            <MetricIcon tone={tone} />
          </span>
          <h3 className="truncate text-sm font-medium">{metric.label}</h3>
        </div>
        <Badge variant="outline" className={classes.badge}>
          {statusLabel(metric.status)}
        </Badge>
      </div>

      <p className="mt-3 text-sm text-foreground">{metric.summary}</p>

      {metric.details.length > 0 && (
        <div className="mt-3 space-y-1 text-xs text-muted-foreground">
          {metric.details.slice(0, 4).map((detail, index) => (
            <div key={`${metric.id}-detail-${index}`}>- {detail}</div>
          ))}
        </div>
      )}

      {metric.basis.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1">
          {metric.basis.slice(0, 5).map((basis) => (
            <Badge key={basis} variant="outline" className="text-[10px] text-muted-foreground">
              {formatAgentEvalBasis(basis)}
            </Badge>
          ))}
        </div>
      )}

      {metric.recommendation && (
        <p className="mt-3 text-xs text-muted-foreground">{metric.recommendation}</p>
      )}
    </section>
  );
}
