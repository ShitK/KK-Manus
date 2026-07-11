import type { AgentEvalMetricStatus, AgentEvalRunSummary } from '@/lib/api';

export function formatAgentEvalTime(value: string | null): string {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

export function formatAgentEvalTokenCount(value: number): string {
  return new Intl.NumberFormat('en-US', {
    maximumFractionDigits: 0,
  }).format(value || 0);
}

export function agentEvalStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    running: '运行中',
    completed: '已完成',
    failed: '失败',
    error: '错误',
    stopped: '已停止',
  };
  return labels[status] || status;
}

export function agentEvalMetricTone(
  status: AgentEvalMetricStatus,
): 'success' | 'warning' | 'danger' | 'muted' {
  if (status === 'pass') return 'success';
  if (status === 'warn') return 'warning';
  if (status === 'fail') return 'danger';
  return 'muted';
}

export function formatAgentEvalBasis(value: string): string {
  const labels: Record<string, string> = {
    'agent_run.status': '运行状态',
    'agent_run.error': '运行错误',
    'agent_run.completed_at': '完成时间',
    'agent_run.updated_at': '更新时间',
    'messages.created_at': '消息时间',
    'messages.content': '消息内容',
    'events.timestamp': '事件时间',
    'events.content': '事件内容',
    'redis.active_instance_keys': 'Redis 活动实例',
    'redis.response_count': 'Redis 响应数',
    workflow_payload: 'Workflow 结构化数据',
    'workflow_payload.errors': 'Workflow 错误',
    'workflow_payload.warnings': 'Workflow 提醒',
    'workflow_payload.workflow.stage': 'Workflow 阶段',
    'context_snapshot.redaction_policy': '上下文脱敏策略',
    'evidence_policy.allowed_evidence_ids': '允许引用的证据',
  };
  return labels[value] || value;
}

export function sortAgentEvalRuns(
  runs: AgentEvalRunSummary[],
): AgentEvalRunSummary[] {
  return [...runs].sort((a, b) => {
    if (a.status === 'running' && b.status !== 'running') return -1;
    if (a.status !== 'running' && b.status === 'running') return 1;
    const aTime = new Date(a.updated_at || a.started_at || 0).getTime();
    const bTime = new Date(b.updated_at || b.started_at || 0).getTime();
    return bTime - aTime;
  });
}
