'use client';

import type React from 'react';
import { useState } from 'react';
import {
  AlertTriangle,
  Bot,
  CheckCircle,
  Clock,
  Database,
  Eye,
  FileText,
  GitBranch,
  Github,
  HelpCircle,
  Info,
  ListChecks,
  MessageSquare,
  Save,
  ShieldCheck,
  Trash2,
} from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { ScrollArea } from '@/components/ui/scroll-area';
import type {
  GitHubRepoInterviewMemoryCandidatePayload,
  GitHubRepoInterviewVectorMemoryApiError,
  GitHubRepoInterviewVectorMemoryCandidate as ApiVectorMemoryCandidate,
} from '@/lib/api';

import { GenericToolView } from '../GenericToolView';
import type { ToolViewProps } from '../types';
import { formatTimestamp, getToolTitle } from '../utils';
import {
  useConfirmGitHubRepoInterviewMemory,
  useDeleteGitHubRepoInterviewMemory,
  useGitHubRepoInterviewMemories,
} from '@/hooks/react-query/github-repo-interview-memory/use-github-repo-interview-memory';
import {
  useConfirmGitHubRepoInterviewVectorMemory,
  useDeleteGitHubRepoInterviewVectorMemory,
  useGitHubRepoInterviewVectorMemories,
} from '@/hooks/react-query/github-repo-interview-vector-memory/use-github-repo-interview-vector-memory';
import {
  formatGitHubInterviewCategory,
  formatGitHubInterviewDifficulty,
  getGitHubInterviewCategoryDescription,
} from '../github-repo-interview-categories';
import {
  buildGitHubRepoInterviewPrimaryPanelSectionIds,
  buildMultiAgentTraceFlowNodes,
  buildMultiAgentTraceSummary,
  buildWorkflowBoundaryFacts,
  extractGitHubRepoInterviewWorkflowData,
  formatWorkflowDisplayTerm,
  formatWorkflowFactLabel,
  formatWorkflowFactValue,
  formatWorkflowStepStatusLabel,
  groupWorkflowRoles,
  type GitHubRepoInterviewSessionMemory,
  type GitHubRepoInterviewAgentNode,
  type GitHubRepoInterviewMultiAgentTrace,
  type GitHubRepoInterviewMultiAgentTraceFlowNode,
  type GitHubRepoInterviewWorkflowBoundaryFact,
  type GitHubRepoInterviewWorkflowMemoryCandidate,
  type GitHubRepoInterviewVectorMemoryCandidate,
  type GitHubRepoInterviewWorkflowPayload,
  type GitHubRepoInterviewWorkflowStep,
} from './_utils';

function hasText(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0;
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => hasText(item))
    : [];
}

function formatWorkflowValue(value?: string): string | undefined {
  return formatWorkflowDisplayTerm(value) || value;
}

function formatWorkflowSentence(value?: string): string | undefined {
  const displayValue = formatWorkflowValue(value) || value;
  if (!hasText(displayValue)) return undefined;
  return displayValue
    .replaceAll('allowlisted evidence', '允许证据')
    .replaceAll('allowed evidence', '允许证据')
    .replaceAll('repo evidence', '仓库证据');
}

function formatYesNo(value: boolean | undefined): string | undefined {
  if (typeof value !== 'boolean') return undefined;
  return value ? '是' : '否';
}

function formatAgentDisplayName(agent: GitHubRepoInterviewAgentNode): string {
  return (
    formatWorkflowValue(agent.id) ||
    formatWorkflowValue(agent.role_name) ||
    agent.role_name ||
    agent.id ||
    '智能体'
  );
}

function demoClosureStatus(payload: GitHubRepoInterviewWorkflowPayload): string {
  if (payload.errors?.length) return '存在错误';
  if (payload.warnings?.length) return '存在警告';
  return '正常';
}

function toConfirmableMemoryCandidate(
  candidate: GitHubRepoInterviewWorkflowMemoryCandidate,
): GitHubRepoInterviewMemoryCandidatePayload | null {
  const sourceFields = asStringArray(candidate.source_fields);
  const privacy = candidate.privacy;
  if (
    !hasText(candidate.type) ||
    !hasText(candidate.value) ||
    !hasText(candidate.source_stage) ||
    !sourceFields.length ||
    candidate.requires_user_confirmation !== true ||
    candidate.status !== 'candidate_only' ||
    candidate.persisted !== false ||
    privacy?.includes_user_answer !== false ||
    privacy?.includes_follow_up_answer !== false ||
    privacy?.includes_repo_evidence_text !== false
  ) {
    return null;
  }

  return {
    id: hasText(candidate.id) ? candidate.id : undefined,
    type: candidate.type,
    value: candidate.value,
    label: hasText(candidate.label) ? candidate.label : undefined,
    source_stage: candidate.source_stage,
    source_fields: sourceFields,
    requires_user_confirmation: true,
    status: 'candidate_only',
    persisted: false,
    privacy: {
      includes_user_answer: false,
      includes_follow_up_answer: false,
      includes_repo_evidence_text: false,
    },
  };
}

function toConfirmableVectorMemoryCandidate(
  candidate?: GitHubRepoInterviewVectorMemoryCandidate,
): ApiVectorMemoryCandidate | null {
  const privacy = candidate?.privacy;
  if (
    !candidate ||
    !hasText(candidate.id) ||
    candidate.type !== 'practice_experience_summary' ||
    !hasText(candidate.text) ||
    !hasText(candidate.content_hash) ||
    !hasText(candidate.source_thread_id) ||
    candidate.source_stage !== 'summarize' ||
    candidate.requires_user_confirmation !== true ||
    candidate.status !== 'candidate_only' ||
    candidate.persisted !== false ||
    privacy?.includes_user_answer !== false ||
    privacy.includes_follow_up_answer !== false ||
    privacy.includes_repo_evidence_text !== false
  ) {
    return null;
  }
  return {
    id: candidate.id,
    type: 'practice_experience_summary',
    text: candidate.text,
    content_hash: candidate.content_hash,
    target_role: candidate.target_role,
    category: candidate.category,
    source_thread_id: candidate.source_thread_id,
    source_agent_run_id: candidate.source_agent_run_id,
    source_stage: 'summarize',
    requires_user_confirmation: true,
    persisted: false,
    status: 'candidate_only',
    provenance: {
      kind: candidate.provenance?.kind === 'demo_fixture' ? 'demo_fixture' : 'user_confirmed',
    },
    privacy: {
      includes_user_answer: false,
      includes_follow_up_answer: false,
      includes_repo_evidence_text: false,
    },
  };
}

function Section({
  title,
  icon,
  children,
}: {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="border-b border-zinc-200 last:border-b-0 dark:border-zinc-800">
      <div className="flex items-center gap-2.5 bg-zinc-50/80 px-4 py-3 text-sm font-medium text-zinc-700 dark:bg-zinc-900/80 dark:text-zinc-300">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950 [&>svg]:h-5 [&>svg]:w-5">
          {icon}
        </span>
        {title}
      </div>
      <div className="px-4 py-3">{children}</div>
    </section>
  );
}

function TextBlock({ children }: { children?: string }) {
  if (!hasText(children)) return null;
  return (
    <p className="min-w-0 whitespace-pre-wrap break-words text-sm leading-relaxed text-zinc-600 dark:text-zinc-300">
      {children}
    </p>
  );
}

function BulletList({
  items,
  formatItem,
}: {
  items?: string[];
  formatItem?: (item: string) => string;
}) {
  const visible = asStringArray(items);
  if (!visible.length) return null;
  return (
    <ul className="space-y-2">
      {visible.map((item, index) => {
        const displayValue = formatItem ? formatItem(item) : item;
        return (
          <li
            key={`${item}-${index}`}
            className="flex gap-2 text-sm leading-relaxed text-zinc-600 dark:text-zinc-300"
          >
            <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-zinc-300 dark:bg-zinc-600" />
            <span className="min-w-0 break-words">{displayValue}</span>
          </li>
        );
      })}
    </ul>
  );
}

function DetailList({
  items,
}: {
  items?: Array<{ title?: string; detail?: string }>;
}) {
  const visible = Array.isArray(items)
    ? items.filter((item) => hasText(item.title) || hasText(item.detail))
    : [];
  if (!visible.length) return null;
  return (
    <div className="space-y-2">
      {visible.map((item, index) => (
        <div key={`${item.title || 'detail'}-${index}`} className="text-sm leading-relaxed">
          {hasText(item.title) ? (
            <div className="font-medium text-zinc-800 dark:text-zinc-200">
              {item.title}
            </div>
          ) : null}
          <TextBlock>{item.detail}</TextBlock>
        </div>
      ))}
    </div>
  );
}

function ImprovementList({
  items,
}: {
  items?: Array<{ weakness?: string; evidence?: string; suggestion?: string }>;
}) {
  const visible = Array.isArray(items)
    ? items.filter(
        (item) => hasText(item.weakness) || hasText(item.evidence) || hasText(item.suggestion),
      )
    : [];
  if (!visible.length) return null;
  return (
    <div className="space-y-3">
      {visible.map((item, index) => (
        <div key={`${item.weakness || 'improvement'}-${index}`} className="space-y-1 text-sm">
          <div className="font-medium text-zinc-800 dark:text-zinc-200">
            {item.weakness || '待打磨点'}
          </div>
          <TextBlock>{item.evidence}</TextBlock>
          <TextBlock>{item.suggestion}</TextBlock>
        </div>
      ))}
    </div>
  );
}

function AbilityProfileList({
  items,
}: {
  items?: Array<{ dimension?: string; score?: number; rationale?: string }>;
}) {
  const visible = Array.isArray(items)
    ? items.filter(
        (item) =>
          hasText(item.dimension) ||
          typeof item.score === 'number' ||
          hasText(item.rationale),
      )
    : [];
  if (!visible.length) return null;
  return (
    <div className="space-y-2">
      {visible.map((item, index) => (
        <div key={`${item.dimension || 'ability'}-${index}`} className="space-y-1 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-medium text-zinc-800 dark:text-zinc-200">
              {item.dimension || '综合能力'}
            </span>
            {typeof item.score === 'number' ? (
              <Badge variant="outline" className="h-6">
                {item.score}%
              </Badge>
            ) : null}
          </div>
          <TextBlock>{item.rationale}</TextBlock>
        </div>
      ))}
    </div>
  );
}

function SummarySubsection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-2">
      <h4 className="text-sm font-medium text-zinc-800 dark:text-zinc-200">{title}</h4>
      {children}
    </div>
  );
}

function MetadataRows({
  items,
}: {
  items: Array<{ label: string; value: string | number | null | undefined }>;
}) {
  const visibleItems = items.filter((item) =>
    typeof item.value === 'number' ? true : hasText(item.value),
  );
  if (!visibleItems.length) return null;
  return (
    <div className="divide-y divide-zinc-100 border-y border-zinc-100 dark:divide-zinc-800 dark:border-zinc-800">
      {visibleItems.map((item) => (
        <div
          key={item.label}
          className="grid gap-1 py-2 text-sm sm:grid-cols-[8rem_1fr] sm:gap-3"
        >
          <span className="shrink-0 text-zinc-400 dark:text-zinc-500">
            {item.label}
          </span>
          <span className="min-w-0 break-words text-zinc-700 dark:text-zinc-300">
            {item.value}
          </span>
        </div>
      ))}
    </div>
  );
}

function boundaryToneClass(tone: GitHubRepoInterviewWorkflowBoundaryFact['tone']) {
  if (tone === 'success') {
    return 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/20 dark:text-emerald-300';
  }
  if (tone === 'warning') {
    return 'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900 dark:bg-amber-950/20 dark:text-amber-300';
  }
  return 'border-zinc-200 bg-zinc-50 text-zinc-700 dark:border-zinc-800 dark:bg-zinc-900/60 dark:text-zinc-300';
}

function StatusBadge({
  status,
  isStreaming,
}: {
  status?: string;
  isStreaming?: boolean;
}) {
  const effectiveStatus = isStreaming ? 'running' : status || 'success';
  const isError = effectiveStatus === 'error';
  const isPartial = effectiveStatus === 'partial';
  const isRunning = effectiveStatus === 'running';
  return (
    <Badge
      variant="outline"
      className={
        isError
          ? 'h-6 gap-1.5 border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-800 dark:bg-rose-900/20 dark:text-rose-400'
          : isPartial
            ? 'h-6 gap-1.5 border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-400'
            : isRunning
              ? 'h-6 gap-1.5 border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-800 dark:bg-sky-900/20 dark:text-sky-400'
              : 'h-6 gap-1.5 border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-900/20 dark:text-emerald-400'
      }
    >
      {isError ? (
        <AlertTriangle className="h-3.5 w-3.5" />
      ) : isRunning ? (
        <Clock className="h-3.5 w-3.5" />
      ) : (
        <CheckCircle className="h-3.5 w-3.5" />
      )}
      {isError ? '失败' : isPartial ? '部分完成' : isRunning ? '运行中' : '工作流就绪'}
    </Badge>
  );
}

function WorkflowSteps({
  steps,
  payload,
}: {
  steps?: GitHubRepoInterviewWorkflowStep[];
  payload?: GitHubRepoInterviewWorkflowPayload;
}) {
  const visible = Array.isArray(steps) ? steps : [];
  if (!visible.length) return null;
  return (
    <Section title="工作流" icon={<ListChecks className="text-emerald-500" />}>
      <div className="space-y-2">
        {visible.map((step, index) => {
          const status = step.status || 'pending';
          const isDone = status === 'success' || status === 'ready';
          const isError = status === 'error';
          return (
            <div key={`${step.id || 'step'}-${index}`} className="flex gap-3">
              <div
                className={
                  isError
                    ? 'mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-rose-200 bg-rose-50 text-rose-600 dark:border-rose-900 dark:bg-rose-950/30'
                    : isDone
                      ? 'mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-emerald-200 bg-emerald-50 text-emerald-600 dark:border-emerald-900 dark:bg-emerald-950/30'
                      : 'mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-zinc-200 bg-white text-zinc-400 dark:border-zinc-800 dark:bg-zinc-950'
                }
              >
                {isError ? (
                  <AlertTriangle className="h-3.5 w-3.5" />
                ) : isDone ? (
                  <CheckCircle className="h-3.5 w-3.5" />
                ) : (
                  <Clock className="h-3.5 w-3.5" />
                )}
              </div>
              <div className="min-w-0">
                <div className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
                  {step.label || step.id || `Step ${index + 1}`}
                </div>
                <div className="text-xs uppercase tracking-wide text-zinc-400">
                  {formatWorkflowStepStatusLabel(step, payload)}
                </div>
                <TextBlock>{step.detail}</TextBlock>
              </div>
            </div>
          );
        })}
      </div>
    </Section>
  );
}

function DemoClosureSection({
  payload,
}: {
  payload: GitHubRepoInterviewWorkflowPayload;
}) {
  const workflow = payload.data?.workflow;
  const snapshot = payload.data?.context_snapshot;
  const evidenceIds =
    payload.data?.evidence_policy?.allowed_evidence_ids ||
    payload.data?.context_policy?.allowed_evidence_ids ||
    snapshot?.allowed_evidence_ids ||
    [];
  const candidateCount = payload.data?.memory_candidates?.length || 0;
  const savedCount =
    payload.data?.saved_memory_context?.length ??
    snapshot?.saved_memory_count ??
    0;
  const normalizedIntentRows = payload.data?.normalized_intent
    ? Object.entries(payload.data.normalized_intent).map(([key, item]) => ({
        label: formatWorkflowDisplayTerm(key) || key,
        value:
          item.raw && item.normalized
            ? `${item.raw} -> ${item.normalized}`
            : item.normalized,
      }))
    : [];

  if (
    !workflow &&
    !snapshot &&
    !evidenceIds.length &&
    !candidateCount &&
    !savedCount &&
    !normalizedIntentRows.length
  ) {
    return null;
  }

  return (
    <Section title="演示闭环" icon={<ShieldCheck className="text-cyan-500" />}>
      <MetadataRows
        items={[
          {
            label: '工作流阶段',
            value: formatWorkflowValue(workflow?.current_stage),
          },
          {
            label: '证据边界',
            value: evidenceIds.length
              ? '已限制到允许证据'
              : '未限制证据白名单',
          },
          {
            label: '上下文快照',
            value: snapshot ? '已生成' : '未生成',
          },
          { label: '候选记忆', value: `${candidateCount} 条` },
          { label: '已确认记忆', value: `${savedCount} 条` },
          {
            label: '回答保存',
            value: formatYesNo(snapshot?.persists_user_answer),
          },
          { label: '状态', value: demoClosureStatus(payload) },
          ...normalizedIntentRows,
        ]}
      />
    </Section>
  );
}

function BoundarySummarySection({ payload }: { payload: GitHubRepoInterviewWorkflowPayload }) {
  const facts = buildWorkflowBoundaryFacts(payload);
  if (!facts.length) return null;

  return (
    <Section title="边界摘要" icon={<ShieldCheck className="text-emerald-500" />}>
      <div className="grid gap-2 sm:grid-cols-2">
        {facts.map((fact) => (
          <div
            key={fact.id}
            className={`min-w-0 border px-3 py-2 text-sm ${boundaryToneClass(fact.tone)}`}
          >
            <div className="text-xs font-medium uppercase text-current opacity-70">
              {formatWorkflowFactLabel(fact.id, fact.label)}
            </div>
            <div className="min-w-0 break-words font-medium">
              {formatWorkflowFactValue(fact.id, fact.value)}
            </div>
          </div>
        ))}
      </div>
    </Section>
  );
}

function AgentStatusBadge({ status }: { status?: GitHubRepoInterviewAgentNode['status'] }) {
  const normalized = status || 'pending';
  const isError = normalized === 'error';
  const isPartial = normalized === 'partial';
  const isPending = normalized === 'pending' || normalized === 'skipped';
  return (
    <Badge
      variant="outline"
      className={
        isError
          ? 'h-5 border-rose-200 bg-rose-50 px-1.5 py-0 text-[11px] text-rose-700 dark:border-rose-900 dark:bg-rose-950/30 dark:text-rose-300'
          : isPartial
            ? 'h-5 border-amber-200 bg-amber-50 px-1.5 py-0 text-[11px] text-amber-700 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-300'
            : isPending
              ? 'h-5 border-zinc-200 bg-zinc-50 px-1.5 py-0 text-[11px] text-zinc-600 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-300'
              : 'h-5 border-emerald-200 bg-emerald-50 px-1.5 py-0 text-[11px] text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-300'
      }
    >
      {formatWorkflowValue(normalized)}
    </Badge>
  );
}

function TraceBooleanPill({
  label,
  value,
  icon,
}: {
  label: string;
  value?: boolean;
  icon: React.ReactNode;
}) {
  return (
    <div
      className={
        value
          ? 'flex min-h-9 min-w-0 items-center gap-2 rounded-md border border-emerald-200 bg-emerald-50 px-2.5 py-1.5 text-xs text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950/25 dark:text-emerald-300'
          : 'flex min-h-9 min-w-0 items-center gap-2 rounded-md border border-zinc-200 bg-white px-2.5 py-1.5 text-xs text-zinc-600 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-300'
      }
    >
      <span className="shrink-0 [&>svg]:h-3.5 [&>svg]:w-3.5">{icon}</span>
      <span className="min-w-0 break-words">{label}</span>
      <span className="ml-auto shrink-0 font-medium">{formatYesNo(value) || '未知'}</span>
    </div>
  );
}

function TraceSignalTile({
  label,
  value,
}: {
  label: string;
  value: string | undefined;
}) {
  if (!hasText(value)) return null;
  return (
    <div className="min-w-0 rounded-md border border-cyan-100 bg-white px-3 py-2 text-sm dark:border-cyan-950 dark:bg-zinc-950">
      <div className="text-xs font-medium text-cyan-700 dark:text-cyan-300">
        {label}
      </div>
      <div className="mt-1 min-w-0 break-words font-medium text-zinc-800 dark:text-zinc-100">
        {value}
      </div>
    </div>
  );
}

function traceFlowNodeClass(node: GitHubRepoInterviewMultiAgentTraceFlowNode): string {
  if (node.kind === 'orchestrator') {
    return 'border-cyan-200 bg-cyan-50 text-cyan-800 dark:border-cyan-900 dark:bg-cyan-950/35 dark:text-cyan-200';
  }
  if (node.status === 'success') {
    return 'border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-200';
  }
  if (node.status === 'partial') {
    return 'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-200';
  }
  if (node.status === 'error') {
    return 'border-rose-200 bg-rose-50 text-rose-800 dark:border-rose-900 dark:bg-rose-950/30 dark:text-rose-200';
  }
  return 'border-zinc-200 bg-zinc-50 text-zinc-700 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-200';
}

function traceFlowDotClass(node: GitHubRepoInterviewMultiAgentTraceFlowNode): string {
  if (node.kind === 'orchestrator') return 'bg-cyan-500';
  if (node.status === 'success') return 'bg-emerald-500';
  if (node.status === 'partial') return 'bg-amber-500';
  if (node.status === 'error') return 'bg-rose-500';
  return 'bg-zinc-400';
}

function TraceFlow({
  nodes,
  compact = false,
}: {
  nodes: GitHubRepoInterviewMultiAgentTraceFlowNode[];
  compact?: boolean;
}) {
  if (!nodes.length) return null;
  return (
    <div className="flex min-w-0 flex-wrap items-center gap-2">
      {nodes.map((node, index) => (
        <div key={`${node.id}-${index}`} className="flex min-w-0 items-center gap-2">
          <div
            className={`flex min-h-8 min-w-0 items-center gap-2 rounded-md border px-2.5 py-1.5 text-xs font-medium ${traceFlowNodeClass(node)} ${compact ? 'max-w-40' : ''}`}
          >
            {node.kind === 'orchestrator' ? (
              <Bot className="h-3.5 w-3.5 shrink-0" />
            ) : (
              <span className={`h-2 w-2 shrink-0 rounded-full ${traceFlowDotClass(node)}`} />
            )}
            <span className={compact ? 'min-w-0 truncate' : 'min-w-0 break-words'}>
              {node.label}
            </span>
          </div>
          {index < nodes.length - 1 ? (
            <span className="shrink-0 text-cyan-500">-&gt;</span>
          ) : null}
        </div>
      ))}
    </div>
  );
}

function MultiAgentTraceSection({
  payload,
}: {
  payload: GitHubRepoInterviewWorkflowPayload;
}) {
  const trace = payload.data?.multi_agent_trace;
  const agents = trace?.agents || [];
  if (!trace || !agents.length) return null;
  const summary = buildMultiAgentTraceSummary(trace);
  const flowNodes = buildMultiAgentTraceFlowNodes(trace);

  return (
    <Section title="多智能体" icon={<GitBranch className="text-cyan-500" />}>
      <div className="rounded-md border border-cyan-200 bg-cyan-50/60 p-3 dark:border-cyan-900 dark:bg-cyan-950/20">
        <div className="flex min-w-0 flex-wrap items-start gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-cyan-200 bg-white text-cyan-600 dark:border-cyan-900 dark:bg-zinc-950 dark:text-cyan-300">
            <Bot className="h-4 w-4" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex min-w-0 flex-wrap items-center gap-2">
              <div className="min-w-0 break-words text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                受控多智能体链路
              </div>
              <AgentStatusBadge status={trace.orchestrator?.status} />
            </div>
            <div className="mt-1 min-w-0 break-words text-xs text-zinc-600 dark:text-zinc-300">
              {summary?.statusLabel || `${agents.length} 个智能体`} · {summary?.modeLabel || '受控本地链路'}
            </div>
          </div>
          <Dialog>
            <DialogTrigger asChild>
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="h-8 rounded-md border-cyan-200 bg-white text-cyan-700 hover:bg-cyan-50 dark:border-cyan-900 dark:bg-zinc-950 dark:text-cyan-300 dark:hover:bg-cyan-950/30"
              >
                <Eye className="h-3.5 w-3.5" />
                查看详情
              </Button>
            </DialogTrigger>
            <DialogContent className="flex h-[85vh] max-h-[85vh] w-[min(1120px,calc(100vw-2rem))] max-w-none flex-col gap-0 overflow-hidden p-0">
              <DialogHeader className="border-b border-zinc-200 px-5 py-4 text-left dark:border-zinc-800">
                <DialogTitle className="flex min-w-0 flex-wrap items-center gap-2 text-lg">
                  <GitBranch className="h-5 w-5 text-cyan-500" />
                  受控多智能体链路
                </DialogTitle>
                <DialogDescription>
                  主控调度员按固定契约编排本地链路，详情仅展示本次工作流数据中的边界信息。
                </DialogDescription>
              </DialogHeader>
              <ScrollArea className="min-h-0 flex-1">
                <MultiAgentTraceDetail trace={trace} />
              </ScrollArea>
            </DialogContent>
          </Dialog>
        </div>

        {flowNodes.length ? (
          <div className="mt-3 flex min-w-0 flex-wrap items-center gap-1.5">
            <TraceFlow nodes={flowNodes} compact />
          </div>
        ) : null}

        <div className="mt-3 grid gap-2 sm:grid-cols-3">
          <div className="rounded-md border border-cyan-100 bg-white px-2.5 py-2 text-xs dark:border-cyan-950 dark:bg-zinc-950">
            <span className="text-zinc-500 dark:text-zinc-400">仓库证据</span>
            <span className="ml-2 font-medium text-zinc-900 dark:text-zinc-100">
              {formatYesNo(summary?.usesRepoEvidence) || '未知'}
            </span>
          </div>
          <div className="rounded-md border border-cyan-100 bg-white px-2.5 py-2 text-xs dark:border-cyan-950 dark:bg-zinc-950">
            <span className="text-zinc-500 dark:text-zinc-400">读取回答</span>
            <span className="ml-2 font-medium text-zinc-900 dark:text-zinc-100">
              {formatYesNo(summary?.readsUserAnswer) || '未知'}
            </span>
          </div>
          <div className="rounded-md border border-cyan-100 bg-white px-2.5 py-2 text-xs dark:border-cyan-950 dark:bg-zinc-950">
            <span className="text-zinc-500 dark:text-zinc-400">保存记忆</span>
            <span className="ml-2 font-medium text-zinc-900 dark:text-zinc-100">
              {formatYesNo(summary?.persistsMemory) || '未知'}
            </span>
          </div>
        </div>
      </div>
    </Section>
  );
}

function MultiAgentTraceDetail({
  trace,
}: {
  trace: GitHubRepoInterviewMultiAgentTrace;
}) {
  const agents = trace.agents || [];
  const signals = trace.quality_signals;
  const flowNodes = buildMultiAgentTraceFlowNodes(trace);
  const summary = buildMultiAgentTraceSummary(trace);

  return (
    <div className="space-y-4 bg-cyan-50/35 p-5 dark:bg-cyan-950/10">
      <div className="mb-4 flex min-w-0 flex-wrap items-start gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-cyan-200 bg-white text-cyan-600 dark:border-cyan-900 dark:bg-zinc-950 dark:text-cyan-300">
          <GitBranch className="h-5 w-5" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <h3 className="min-w-0 break-words text-base font-semibold text-zinc-950 dark:text-zinc-50">
              受控多智能体链路
            </h3>
            <Badge className="h-6 bg-cyan-600 text-xs text-white hover:bg-cyan-600">
              本地链路
            </Badge>
          </div>
          <div className="mt-1 min-w-0 break-words text-sm text-zinc-600 dark:text-zinc-300">
            主控调度员编排，各智能体之间不自由聊天，只按固定契约串联输入输出。
          </div>
        </div>
        <AgentStatusBadge status={trace.orchestrator?.status} />
      </div>

      {flowNodes.length ? (
        <div className="mb-4 rounded-md border border-cyan-200 bg-white p-3 dark:border-cyan-900 dark:bg-zinc-950">
          <TraceFlow nodes={flowNodes} />
        </div>
      ) : null}

      <div className="mb-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        <TraceSignalTile label="模式" value={formatWorkflowValue(trace.mode)} />
        <TraceSignalTile label="范围" value={summary?.scopeLabel || formatWorkflowValue(trace.scope)} />
        <TraceSignalTile label="智能体完成度" value={summary?.statusLabel} />
        <TraceSignalTile
          label="主控输出"
          value={formatWorkflowSentence(trace.orchestrator?.output_summary)}
        />
      </div>

      <div className="grid gap-3 xl:grid-cols-2">
        {agents.map((agent, index) => (
          <div
            key={`${agent.id || 'agent'}-${index}`}
            className="min-w-0 rounded-md border border-zinc-200 bg-white p-3 text-sm shadow-sm shadow-cyan-900/5 dark:border-zinc-800 dark:bg-zinc-950"
          >
            <div className="mb-3 flex min-w-0 flex-wrap items-start gap-2">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-cyan-100 bg-cyan-50 text-cyan-600 dark:border-cyan-950 dark:bg-cyan-950/25 dark:text-cyan-300">
                <Bot className="h-4 w-4" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="min-w-0 break-words font-semibold text-zinc-900 dark:text-zinc-100">
                  {formatAgentDisplayName(agent)}
                </div>
                <div className="mt-0.5 min-w-0 break-words text-xs text-zinc-500 dark:text-zinc-400">
                  {formatWorkflowValue(agent.stage)}
                </div>
              </div>
              <AgentStatusBadge status={agent.status} />
            </div>

            <div className="mb-3 grid gap-2">
              <TraceBooleanPill
                label="使用仓库证据"
                value={agent.uses_repo_evidence}
                icon={<Database />}
              />
              <TraceBooleanPill
                label="读取用户回答"
                value={agent.reads_user_answer}
                icon={<Eye />}
              />
              <TraceBooleanPill
                label="保存记忆"
                value={agent.persists_memory}
                icon={<Save />}
              />
            </div>

            <TextBlock>{formatWorkflowSentence(agent.output_summary)}</TextBlock>

            <div className="mt-3 grid gap-3 lg:grid-cols-3">
              <div>
                <div className="mb-2 text-xs font-medium text-zinc-400">
                  输入来源
                </div>
                <BulletList
                  items={agent.input_sources}
                  formatItem={(item) => formatWorkflowValue(item) || item}
                />
              </div>
              <div>
                <div className="mb-2 text-xs font-medium text-zinc-400">
                  可见上下文
                </div>
                <BulletList
                  items={agent.visible_context}
                  formatItem={(item) => formatWorkflowValue(item) || item}
                />
              </div>
              <div>
                <div className="mb-2 text-xs font-medium text-zinc-400">
                  禁止访问范围
                </div>
                <BulletList
                  items={agent.forbidden_scope}
                  formatItem={(item) => formatWorkflowValue(item) || item}
                />
              </div>
            </div>
          </div>
        ))}
      </div>

      {signals ? (
        <div className="mt-4">
          <div className="mb-2 text-xs font-medium text-cyan-700 dark:text-cyan-300">
            质量审阅员的质量信号
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            <TraceSignalTile
              label="覆盖度"
              value={formatWorkflowValue(signals.coverage)}
            />
            <TraceSignalTile
              label="证据支撑"
              value={formatWorkflowValue(signals.evidence_grounding)}
            />
            <TraceSignalTile
              label="边界健康"
              value={formatWorkflowValue(signals.boundary_health)}
            />
            <TraceSignalTile
              label="建议下一步"
              value={formatWorkflowValue(signals.recommended_next_step)}
            />
          </div>
        </div>
      ) : null}
    </div>
  );
}

function BoundaryDetailsSection({
  payload,
}: {
  payload: GitHubRepoInterviewWorkflowPayload;
}) {
  return (
    <Section title="边界与证据详情" icon={<ShieldCheck className="text-teal-500" />}>
      <div className="rounded-md border border-teal-200 bg-teal-50/60 p-3 dark:border-teal-900 dark:bg-teal-950/20">
        <div className="flex min-w-0 flex-wrap items-start gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-teal-200 bg-white text-teal-600 dark:border-teal-900 dark:bg-zinc-950 dark:text-teal-300">
            <ShieldCheck className="h-4 w-4" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="min-w-0 break-words text-sm font-semibold text-zinc-900 dark:text-zinc-100">
              证据、上下文和记忆边界已收起
            </div>
            <div className="mt-1 min-w-0 break-words text-xs text-zinc-600 dark:text-zinc-300">
              主面板只保留面试主线；需要核对证据、上下文快照、角色链路和已确认记忆时可查看详情。
            </div>
          </div>
          <Dialog>
            <DialogTrigger asChild>
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="h-8 rounded-md border-teal-200 bg-white text-teal-700 hover:bg-teal-50 dark:border-teal-900 dark:bg-zinc-950 dark:text-teal-300 dark:hover:bg-teal-950/30"
              >
                <Eye className="h-3.5 w-3.5" />
                查看详情
              </Button>
            </DialogTrigger>
            <DialogContent className="flex h-[85vh] max-h-[85vh] w-[min(1040px,calc(100vw-2rem))] max-w-none flex-col gap-0 overflow-hidden p-0">
              <DialogHeader className="border-b border-zinc-200 px-5 py-4 text-left dark:border-zinc-800">
                <DialogTitle className="flex min-w-0 flex-wrap items-center gap-2 text-lg">
                  <ShieldCheck className="h-5 w-5 text-teal-500" />
                  边界与证据详情
                </DialogTitle>
                <DialogDescription>
                  这里集中展示本次工作流数据里的证据策略、上下文快照、角色链路和记忆边界。
                </DialogDescription>
              </DialogHeader>
              <ScrollArea className="min-h-0 flex-1">
                <div className="bg-teal-50/30 dark:bg-teal-950/10">
                  <DemoClosureSection payload={payload} />
                  <BoundarySummarySection payload={payload} />
                  <RoleTraceSection payload={payload} />
                  <EvidenceSection payload={payload} />
                  <ContextPolicySection payload={payload} />
                  <ContextSnapshotSection payload={payload} />
                  <SavedMemorySection payload={payload} />
                </div>
              </ScrollArea>
            </DialogContent>
          </Dialog>
        </div>
      </div>
    </Section>
  );
}

function RoleTraceSection({ payload }: { payload: GitHubRepoInterviewWorkflowPayload }) {
  const workflow = payload.data?.workflow;
  const roles = workflow?.roles || [];
  const groups = groupWorkflowRoles(roles);
  const activeRole = workflow?.active_role;
  if (!activeRole && !roles.length) return null;

  return (
    <Section title="角色链路" icon={<GitBranch className="text-emerald-500" />}>
      <div className="space-y-3">
        <MetadataRows
          items={[
            { label: '当前角色', value: activeRole },
            {
              label: '角色数量',
              value: roles.length || undefined,
            },
          ]}
        />
        <div className="space-y-3">
          {groups.map((group) => (
            <div key={group.id} className="space-y-2">
              <div className="text-xs font-medium uppercase text-zinc-400">
                {formatWorkflowValue(group.id) || group.label}
              </div>
              <div className="space-y-2">
                {group.roles.map((role, index) => {
                  const isActive = role.id === activeRole;
                  return (
                    <div
                      key={`${group.id}-${role.id || 'role'}-${index}`}
                      className={
                        isActive
                          ? 'border-l border-emerald-300 bg-emerald-50/60 px-3 py-2 text-sm dark:border-emerald-900 dark:bg-emerald-950/20'
                          : 'border-l border-zinc-200 px-3 py-2 text-sm dark:border-zinc-800'
                      }
                    >
                      <div className="flex min-w-0 flex-wrap items-center gap-2">
                        <span className="min-w-0 break-words font-medium text-zinc-800 dark:text-zinc-100">
                          {role.id || `role-${index + 1}`}
                        </span>
                        {hasText(role.kind) && (
                          <Badge variant="outline" className="h-5 px-1.5 py-0 text-[11px]">
                            {formatWorkflowValue(role.kind)}
                          </Badge>
                        )}
                        {isActive && (
                          <Badge className="h-5 bg-emerald-600 px-1.5 py-0 text-[11px] text-white">
                            当前
                          </Badge>
                        )}
                      </div>
                      <MetadataRows
                        items={[
                          { label: '阶段', value: formatWorkflowValue(role.stage) },
                          { label: '证据范围', value: formatWorkflowValue(role.evidence_scope) },
                          { label: '仓库访问', value: formatWorkflowValue(role.repository_access) },
                        ]}
                      />
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </div>
    </Section>
  );
}

function QuestionSection({ payload }: { payload: GitHubRepoInterviewWorkflowPayload }) {
  const question = payload.data?.selected_question;
  if (!question) return null;
  return (
    <Section title="面试题" icon={<HelpCircle className="text-sky-500" />}>
      <div className="space-y-3">
        <MetadataRows
          items={[
            { label: 'ID', value: question.id || payload.input?.question_id },
            { label: '分类', value: formatGitHubInterviewCategory(question.category) },
            { label: '方向', value: getGitHubInterviewCategoryDescription(question.category) },
            { label: '难度', value: formatGitHubInterviewDifficulty(question.difficulty) },
            { label: '置信度', value: question.confidence },
          ]}
        />
        <TextBlock>{question.question}</TextBlock>
        <TextBlock>{question.answer_direction}</TextBlock>
      </div>
    </Section>
  );
}

function EvidenceSection({ payload }: { payload: GitHubRepoInterviewWorkflowPayload }) {
  const details = payload.data?.evidence_details || [];
  const policy = payload.data?.evidence_policy;
  if (!details.length && !policy) return null;
  return (
    <Section title="证据策略" icon={<ShieldCheck className="text-cyan-500" />}>
      <div className="space-y-3">
        <MetadataRows
          items={[
            { label: '来源', value: formatWorkflowValue(policy?.source) },
            { label: '仓库访问', value: formatWorkflowValue(policy?.repository_access) },
            { label: '最大证据数', value: policy?.max_evidence_details },
          ]}
        />
        <BulletList items={policy?.allowed_evidence_ids} />
        <div className="space-y-2">
          {details.map((detail, index) => (
            <div
              key={`${detail.evidence_id || detail.source_path || 'evidence'}-${index}`}
              className="border-l border-cyan-200 pl-3 text-sm leading-relaxed dark:border-cyan-900"
            >
              <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
                <span className="min-w-0 break-words font-medium text-zinc-800 dark:text-zinc-100">
                  {detail.source_path || detail.evidence_id}
                </span>
                {hasText(detail.evidence_type) && (
                  <span className="text-xs uppercase tracking-wide text-cyan-600 dark:text-cyan-400">
                    {detail.evidence_type}
                  </span>
                )}
              </div>
              <TextBlock>{detail.summary || detail.snippet}</TextBlock>
              <TextBlock>{detail.why_it_matters}</TextBlock>
            </div>
          ))}
        </div>
      </div>
    </Section>
  );
}

function ContextPolicySection({ payload }: { payload: GitHubRepoInterviewWorkflowPayload }) {
  const policy = payload.data?.context_policy;
  if (!policy) return null;
  return (
    <Section title="上下文策略" icon={<ShieldCheck className="text-teal-500" />}>
      <div className="space-y-3">
        <MetadataRows
          items={[
            { label: '模式', value: formatWorkflowValue(policy.mode) },
            { label: '当前角色', value: policy.active_role },
            { label: '角色类型', value: formatWorkflowValue(policy.role_kind) },
            { label: '来源', value: formatWorkflowValue(policy.source) },
            { label: '仓库访问', value: formatWorkflowValue(policy.repository_access) },
            { label: '工具访问', value: formatWorkflowValue(policy.tool_access) },
            {
              label: '是否保存回答',
              value:
                typeof policy.persists_user_answer === 'boolean'
                  ? formatWorkflowFactValue(
                      'persists_user_answer',
                      String(policy.persists_user_answer),
                    )
                  : undefined,
            },
          ]}
        />
        <div>
          <div className="mb-2 text-xs font-medium uppercase text-zinc-400">
            可见来源
          </div>
          <BulletList
            items={policy.visible_sources}
            formatItem={(item) => formatWorkflowValue(item) || item}
          />
        </div>
        <div>
          <div className="mb-2 text-xs font-medium uppercase text-zinc-400">
            隐藏来源
          </div>
          <BulletList
            items={policy.hidden_sources}
            formatItem={(item) => formatWorkflowValue(item) || item}
          />
        </div>
        <div>
          <div className="mb-2 text-xs font-medium uppercase text-zinc-400">
            可用证据
          </div>
          <BulletList items={policy.allowed_evidence_ids} />
        </div>
        <div>
          <div className="mb-2 text-xs font-medium uppercase text-zinc-400">
            可用路径
          </div>
          <BulletList items={policy.allowed_source_paths} />
        </div>
      </div>
    </Section>
  );
}

function ContextSnapshotSection({
  payload,
}: {
  payload: GitHubRepoInterviewWorkflowPayload;
}) {
  const snapshot = payload.data?.context_snapshot;
  if (!snapshot) return null;
  const answerState = snapshot.answer_state;
  const redaction = snapshot.redaction_policy;

  return (
    <Section title="上下文快照" icon={<ShieldCheck className="text-emerald-500" />}>
      <div className="space-y-3">
        <MetadataRows
          items={[
            { label: '范围', value: formatWorkflowValue(snapshot.scope) },
            { label: '持久化', value: formatWorkflowValue(snapshot.persistence) },
            { label: '当前阶段', value: formatWorkflowValue(snapshot.current_stage) },
            { label: '当前角色', value: snapshot.active_role },
            { label: '角色类型', value: formatWorkflowValue(snapshot.role_kind) },
            { label: '仓库访问', value: formatWorkflowValue(snapshot.repository_access) },
            { label: '工具访问', value: formatWorkflowValue(snapshot.tool_access) },
            {
              label: '是否保存回答',
              value:
                typeof snapshot.persists_user_answer === 'boolean'
                  ? formatWorkflowFactValue(
                      'persists_user_answer',
                      String(snapshot.persists_user_answer),
                    )
                  : undefined,
            },
            {
              label: '回答反馈',
              value:
                typeof answerState?.has_answer_feedback === 'boolean'
                  ? answerState.has_answer_feedback
                    ? '已有结构化反馈'
                    : '未生成结构化反馈'
                  : undefined,
            },
            {
              label: '追问反馈',
              value:
                typeof answerState?.has_follow_up_feedback === 'boolean'
                  ? answerState.has_follow_up_feedback
                    ? '已有追问反馈'
                    : '未保存追问反馈'
                  : undefined,
            },
            {
              label: '追问模式',
              value: formatWorkflowValue(answerState?.follow_up_mode),
            },
            { label: '追问次数', value: answerState?.follow_up_count },
            { label: '已确认记忆数', value: snapshot.saved_memory_count },
          ]}
        />
        <div>
          <div className="mb-2 text-xs font-medium uppercase text-zinc-400">
            可见来源
          </div>
          <BulletList
            items={snapshot.visible_sources}
            formatItem={(item) => formatWorkflowValue(item) || item}
          />
        </div>
        <div>
          <div className="mb-2 text-xs font-medium uppercase text-zinc-400">
            隐藏来源
          </div>
          <BulletList
            items={snapshot.hidden_sources}
            formatItem={(item) => formatWorkflowValue(item) || item}
          />
        </div>
        <div>
          <div className="mb-2 text-xs font-medium uppercase text-zinc-400">
            可用 evidence
          </div>
          <BulletList items={snapshot.allowed_evidence_ids} />
        </div>
        <div>
          <div className="mb-2 text-xs font-medium uppercase text-zinc-400">
            可用路径
          </div>
          <BulletList items={snapshot.allowed_source_paths} />
        </div>
        <div>
          <div className="mb-2 text-xs font-medium uppercase text-zinc-400">
            隐私边界
          </div>
          <MetadataRows
            items={[
              {
                label: '包含用户回答',
                value:
                  typeof redaction?.includes_user_answer === 'boolean'
                    ? redaction.includes_user_answer
                      ? '是'
                      : '否'
                    : undefined,
              },
              {
                label: '包含追问回答',
                value:
                  typeof redaction?.includes_follow_up_answer === 'boolean'
                    ? redaction.includes_follow_up_answer
                      ? '是'
                      : '否'
                    : undefined,
              },
              {
                label: '包含隐藏来源内容',
                value:
                  typeof redaction?.includes_hidden_source_content === 'boolean'
                    ? redaction.includes_hidden_source_content
                      ? '是'
                      : '否'
                    : undefined,
              },
              {
                label: '包含仓库证据原文',
                value:
                  typeof redaction?.includes_repo_evidence_text === 'boolean'
                    ? redaction.includes_repo_evidence_text
                      ? '是'
                      : '否'
                    : undefined,
              },
            ]}
          />
        </div>
      </div>
    </Section>
  );
}

function SavedMemorySection({
  payload,
}: {
  payload: GitHubRepoInterviewWorkflowPayload;
}) {
  const saved = payload.data?.saved_memory_context || [];
  if (!saved.length) return null;

  return (
    <Section title="已确认记忆上下文" icon={<ShieldCheck className="text-emerald-500" />}>
      <div className="space-y-3">
        <TextBlock>
          这些记忆已由用户确认保存；本次只是作为显式传入的请求级上下文展示。
        </TextBlock>
        <div className="space-y-2">
          {saved.map((memory, index) => (
            <div
              key={`${memory.id || `${memory.type}:${memory.value}` || 'saved-memory'}-${index}`}
              className="border-l border-emerald-200 px-3 py-2 text-sm dark:border-emerald-900"
            >
              <div className="flex min-w-0 flex-wrap items-center gap-2">
                <span className="min-w-0 break-words font-medium text-zinc-800 dark:text-zinc-100">
                  {formatWorkflowValue(memory.value) || memory.value || memory.id}
                </span>
                {hasText(memory.type) && (
                  <Badge variant="outline" className="h-5 px-1.5 py-0 text-[11px]">
                    {formatWorkflowValue(memory.type)}
                  </Badge>
                )}
                <Badge
                  variant="outline"
                  className="h-5 border-emerald-200 bg-emerald-50 px-1.5 py-0 text-[11px] text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-300"
                >
                  已确认
                </Badge>
              </div>
              <TextBlock>{formatWorkflowValue(memory.label) || memory.label}</TextBlock>
              <MetadataRows
                items={[
                  { label: '状态', value: formatWorkflowValue(memory.status) || '已保存' },
                  { label: '来源阶段', value: formatWorkflowValue(memory.source_stage) },
                ]}
              />
              <BulletList items={memory.source_fields} />
            </div>
          ))}
        </div>
      </div>
    </Section>
  );
}

function SessionMemorySection({
  payload,
}: {
  payload: GitHubRepoInterviewWorkflowPayload;
}) {
  const hasSessionMemory = Boolean(
    payload.data?.session_memory_context || payload.data?.session_memory_patch,
  );
  const sessionMemory: GitHubRepoInterviewSessionMemory =
    payload.data?.session_memory_context ||
    payload.data?.session_memory_patch ||
    {};
  if (!hasSessionMemory) return null;

  return (
    <Section title="本会话记忆" icon={<Database className="text-cyan-500" />}>
      <MetadataRows
        items={[
          { label: '面试岗位', value: sessionMemory.target_role || '未设置' },
          { label: '已练习', value: `${sessionMemory.answered_question_ids?.length || 0} 题` },
          {
            label: '当前方向',
            value:
              formatWorkflowDisplayTerm(sessionMemory.current_practice_category || '') ||
              '-',
          },
          {
            label: '最近遗漏证据',
            value: sessionMemory.missed_evidence_ids?.slice(0, 3).join('、') || '-',
          },
          {
            label: '下一步建议',
            value: sessionMemory.next_practice_suggestion || '继续选择下一题练习。',
          },
        ]}
      />
    </Section>
  );
}

function VectorMemoryCandidateSection({
  payload,
}: {
  payload: GitHubRepoInterviewWorkflowPayload;
}) {
  const payloadCandidate = payload.data?.vector_memory_candidate;
  const [candidate, setCandidate] = useState(payloadCandidate);
  const [errorMessage, setErrorMessage] = useState('');
  const memories = useGitHubRepoInterviewVectorMemories();
  const confirmMemory = useConfirmGitHubRepoInterviewVectorMemory();
  const deleteMemory = useDeleteGitHubRepoInterviewVectorMemory();

  const confirmable = toConfirmableVectorMemoryCandidate(candidate);
  const persisted = (memories.data || []).find(
    (memory) => memory.text === confirmable?.text && memory.status === 'active',
  );
  if (!candidate) return null;

  const save = async () => {
    if (!confirmable) return;
    setErrorMessage('');
    try {
      await confirmMemory.mutateAsync({
        candidate: confirmable,
        source_thread_id: confirmable.source_thread_id,
      });
    } catch (rawError) {
      const error = rawError as GitHubRepoInterviewVectorMemoryApiError;
      if (error.status === 409 && error.detail?.code === 'vector_memory_candidate_stale') {
        const refreshed = toConfirmableVectorMemoryCandidate(
          error.detail.candidate as GitHubRepoInterviewVectorMemoryCandidate,
        );
        if (refreshed) setCandidate(refreshed);
        setErrorMessage('候选内容已更新，请确认新内容后再次保存。');
      } else if (error.status === 503) {
        setErrorMessage('向量服务暂时不可用，可稍后重试；本次对话不受影响。');
      } else {
        setErrorMessage('保存失败，请稍后重试；本次对话不受影响。');
      }
    }
  };

  return (
    <Section title="长期文本记忆候选" icon={<Database className="text-teal-500" />}>
      <div className="space-y-3">
        <TextBlock>{candidate.text}</TextBlock>
        <MetadataRows
          items={[
            { label: '目标岗位', value: candidate.target_role || '通用' },
            {
              label: '练习分类',
              value: formatWorkflowDisplayTerm(candidate.category || '') || candidate.category,
            },
            { label: '状态', value: persisted ? '已确认保存' : '候选未保存' },
          ]}
        />
        <div className="flex flex-wrap gap-2 text-xs text-zinc-500 dark:text-zinc-400">
          <Badge variant="outline">未保存回答原文</Badge>
          <Badge variant="outline">未保存追问原文</Badge>
          <Badge variant="outline">未保存仓库证据原文</Badge>
        </div>
        {errorMessage ? (
          <div className="border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-900 dark:bg-amber-950/20 dark:text-amber-200">
            {errorMessage}
          </div>
        ) : null}
        <div className="flex gap-2">
          {persisted ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={deleteMemory.isPending}
              onClick={() => deleteMemory.mutate(persisted.id)}
            >
              <Trash2 className="mr-2 h-4 w-4" />
              删除记忆
            </Button>
          ) : (
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={!confirmable || memories.isError || confirmMemory.isPending}
              onClick={save}
            >
              <Save className="mr-2 h-4 w-4" />
              保存候选记忆
            </Button>
          )}
        </div>
      </div>
    </Section>
  );
}

function VectorMemoryRetrievalSection({
  payload,
}: {
  payload: GitHubRepoInterviewWorkflowPayload;
}) {
  const retrieval = payload.data?.vector_memory_retrieval;
  const context = payload.data?.vector_memory_context || [];
  if (!retrieval) return null;
  const statusLabel = {
    matched: '已召回',
    no_match: '无匹配',
    disabled: '已关闭',
    embedding_error: '已降级',
    retrieval_error: '已降级',
  }[retrieval.status || 'disabled'];

  return (
    <Section title="长期记忆召回" icon={<Database className="text-cyan-500" />}>
      <div className="space-y-3">
        <MetadataRows
          items={[
            { label: '检索状态', value: statusLabel },
            { label: 'Embedding 模型', value: retrieval.model || '-' },
            { label: '相关度阈值', value: retrieval.threshold },
            { label: '候选 / 采用', value: `${retrieval.candidate_count || 0} / ${retrieval.applied_count || 0}` },
            { label: '过滤数量', value: retrieval.filtered_count || 0 },
          ]}
        />
        {retrieval.status === 'embedding_error' || retrieval.status === 'retrieval_error' ? (
          <TextBlock>向量记忆暂时不可用，本轮已继续使用运行上下文、会话记忆和结构化长期记忆。</TextBlock>
        ) : null}
        {retrieval.status === 'no_match' ? (
          <TextBlock>本轮没有达到阈值的历史记忆，Agent 未注入无关内容。</TextBlock>
        ) : null}
        {context.map((memory, index) => (
          <div
            key={`${memory.id || 'vector-memory'}-${index}`}
            className="border-l border-cyan-200 px-3 py-2 dark:border-cyan-900"
          >
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline">相关度 {Math.round((memory.similarity || 0) * 100)}%</Badge>
              {memory.provenance?.kind === 'demo_fixture' ? (
                <Badge variant="outline" className="text-amber-600">演示记忆</Badge>
              ) : null}
            </div>
            <div className="mt-2"><TextBlock>{memory.text}</TextBlock></div>
          </div>
        ))}
      </div>
    </Section>
  );
}

function MemoryCandidatesSection({
  payload,
}: {
  payload: GitHubRepoInterviewWorkflowPayload;
}) {
  const candidates = payload.data?.memory_candidates || [];
  const memories = useGitHubRepoInterviewMemories();
  const confirmMemory = useConfirmGitHubRepoInterviewMemory();
  const deleteMemory = useDeleteGitHubRepoInterviewMemory();
  const memoryListUnavailable = memories.isError;
  const persistedByKey = new Map(
    (memories.data || []).map((memory) => [`${memory.type}:${memory.value}`, memory]),
  );
  if (!candidates.length) return null;

  return (
    <Section title="记忆候选" icon={<ListChecks className="text-amber-500" />}>
      <div className="space-y-3">
        <TextBlock>
          这些只是候选记忆；点击保存后，才会作为用户确认的轻量记忆进入数据库。
        </TextBlock>
        {memoryListUnavailable && (
          <div className="flex items-start gap-2 border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-900 dark:bg-amber-950/20 dark:text-amber-200">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>
              无法读取已保存记忆，暂时不能判断候选是否已保存。请稍后重试后再保存。
            </span>
          </div>
        )}
        <div className="space-y-2">
          {candidates.map((candidate, index) => {
            const key = `${candidate.type}:${candidate.value}`;
            const persisted = persistedByKey.get(key);
            const confirmableCandidate = toConfirmableMemoryCandidate(candidate);
            const cannotSave = memoryListUnavailable || !confirmableCandidate;
            return (
              <div
                key={`${candidate.id || 'memory-candidate'}-${index}`}
                className="border-l border-amber-200 px-3 py-2 text-sm dark:border-amber-900"
              >
                <div className="flex min-w-0 flex-wrap items-center gap-2">
                  <span className="min-w-0 break-words font-medium text-zinc-800 dark:text-zinc-100">
                    {formatWorkflowValue(candidate.value) || candidate.value || candidate.id}
                  </span>
                  {hasText(candidate.type) && (
                    <Badge variant="outline" className="h-5 px-1.5 py-0 text-[11px]">
                      {formatWorkflowValue(candidate.type)}
                    </Badge>
                  )}
                  <Badge
                    variant="outline"
                    className={
                      persisted
                        ? 'h-5 border-emerald-200 bg-emerald-50 px-1.5 py-0 text-[11px] text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-300'
                        : 'h-5 border-amber-200 bg-amber-50 px-1.5 py-0 text-[11px] text-amber-700 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-300'
                    }
                  >
                    {persisted ? '已保存' : '候选未保存'}
                  </Badge>
                </div>
                <TextBlock>{formatWorkflowValue(candidate.label) || candidate.label}</TextBlock>
                <MetadataRows
                  items={[
                    { label: '状态', value: formatWorkflowValue(candidate.status) },
                    { label: '来源阶段', value: formatWorkflowValue(candidate.source_stage) },
                    {
                      label: '需要确认',
                      value:
                        typeof candidate.requires_user_confirmation === 'boolean'
                          ? candidate.requires_user_confirmation
                            ? '是'
                            : '否'
                          : undefined,
                    },
                    {
                      label: '包含用户回答',
                      value:
                        typeof candidate.privacy?.includes_user_answer === 'boolean'
                          ? candidate.privacy.includes_user_answer
                            ? '是'
                            : '否'
                          : undefined,
                    },
                    {
                      label: '包含仓库证据原文',
                      value:
                        typeof candidate.privacy?.includes_repo_evidence_text === 'boolean'
                          ? candidate.privacy.includes_repo_evidence_text
                            ? '是'
                            : '否'
                          : undefined,
                    },
                  ]}
                />
                <BulletList items={candidate.source_fields} />
                <div className="mt-2 flex flex-wrap gap-2">
                  {persisted ? (
                    <button
                      type="button"
                      disabled={deleteMemory.isPending}
                      onClick={() => persisted.id && deleteMemory.mutate(persisted.id)}
                      className="inline-flex h-8 items-center gap-1.5 border border-zinc-200 px-2.5 text-xs font-medium text-zinc-600 transition-colors hover:bg-zinc-50 disabled:cursor-not-allowed disabled:opacity-60 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-900"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                      {deleteMemory.isPending ? '删除中...' : '删除记忆'}
                    </button>
                  ) : (
                    <button
                      type="button"
                      disabled={confirmMemory.isPending || cannotSave}
                      onClick={() => confirmableCandidate && confirmMemory.mutate(confirmableCandidate)}
                      className="inline-flex h-8 items-center gap-1.5 border border-emerald-200 bg-emerald-50 px-2.5 text-xs font-medium text-emerald-700 transition-colors hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-60 dark:border-emerald-800 dark:bg-emerald-950/20 dark:text-emerald-300 dark:hover:bg-emerald-950/40"
                    >
                      <Save className="h-3.5 w-3.5" />
                      {memoryListUnavailable
                        ? '读取失败，暂不可保存'
                        : confirmMemory.isPending
                          ? '保存中...'
                          : confirmableCandidate
                            ? '保存候选记忆'
                            : '候选不完整'}
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </Section>
  );
}

function FeedbackSection({ payload }: { payload: GitHubRepoInterviewWorkflowPayload }) {
  const feedback = payload.data?.answer_feedback;
  if (!feedback) return null;
  return (
    <Section title="回答教练" icon={<MessageSquare className="text-violet-500" />}>
      <div className="space-y-3">
        <TextBlock>{feedback.summary}</TextBlock>
        <BulletList items={feedback.strengths} />
        <BulletList items={feedback.gaps} />
        <BulletList items={feedback.suggested_answer_outline} />
        <BulletList items={feedback.follow_up_questions} />
        <BulletList items={feedback.grounding_notes} />
      </div>
    </Section>
  );
}

function FollowUpSection({ payload }: { payload: GitHubRepoInterviewWorkflowPayload }) {
  const followUp = payload.data?.follow_up;
  if (!followUp) return null;
  return (
    <Section title="追问" icon={<MessageSquare className="text-sky-500" />}>
      <div className="space-y-3">
        <MetadataRows
          items={[
            {
              label: '生成方式',
              value: formatWorkflowValue(followUp.mode),
            },
            {
              label: '追问次数',
              value: payload.data?.workflow?.follow_up_count,
            },
          ]}
        />
        <BulletList items={followUp.questions} />
        <BulletList items={followUp.feedback} />
        <BulletList items={followUp.grounding_notes} />
      </div>
    </Section>
  );
}

function OtherQuestionsSection({ payload }: { payload: GitHubRepoInterviewWorkflowPayload }) {
  const questions = payload.data?.other_questions || [];
  if (!questions.length) return null;
  return (
    <Section title="回答其他问题" icon={<ListChecks className="text-emerald-500" />}>
      <div className="space-y-3">
        {questions.map((question) => (
          <div
            key={question.id}
            className="space-y-2 border-b border-zinc-100 pb-3 last:border-b-0 last:pb-0 dark:border-zinc-800"
          >
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="outline" className="bg-zinc-50 dark:bg-zinc-900">
                {question.id}
              </Badge>
              {hasText(question.category) && (
                <Badge variant="outline" className="bg-zinc-50 dark:bg-zinc-900">
                  {formatGitHubInterviewCategory(question.category)}
                </Badge>
              )}
              {hasText(question.difficulty) && (
                <Badge variant="outline" className="bg-zinc-50 dark:bg-zinc-900">
                  {formatGitHubInterviewDifficulty(question.difficulty)}
                </Badge>
              )}
            </div>
            <TextBlock>{question.question}</TextBlock>
          </div>
        ))}
      </div>
    </Section>
  );
}

function SummarySection({ payload }: { payload: GitHubRepoInterviewWorkflowPayload }) {
  const summary = payload.data?.session_summary;
  if (!summary) return null;
  const conversationSummary = payload.data?.conversation_summary;
  const isConversationSummary = payload.data?.summary_kind === 'conversation_summary';
  const completion = summary.workflow_completion;
  if (isConversationSummary) {
    const practiceOverview = conversationSummary?.practice_overview;
    return (
      <Section title="总结" icon={<FileText className="text-amber-500" />}>
        <div className="space-y-3">
          <MetadataRows
            items={[
              {
                label: '总结范围',
                value: formatWorkflowValue(completion?.summary_scope),
              },
              {
                label: '对话轮次',
                value: payload.data?.conversation_turn_count,
              },
              { label: '下一步练习', value: summary.next_practice_suggestion },
            ]}
          />
          <TextBlock>{conversationSummary?.raw_report}</TextBlock>
          <TextBlock>{conversationSummary?.overview}</TextBlock>
          <SummarySubsection title="练习概况">
            <MetadataRows
              items={[
                { label: '仓库', value: practiceOverview?.repository },
                { label: '角色', value: practiceOverview?.role },
                { label: '难度', value: practiceOverview?.difficulty },
                {
                  label: '完成题目',
                  value: practiceOverview?.completed_items?.join('；'),
                },
                {
                  label: '未答 / 待补',
                  value: practiceOverview?.unfinished_items?.join('；'),
                },
              ]}
            />
          </SummarySubsection>
          <SummarySubsection title="讨论过的问题">
            <BulletList items={conversationSummary?.discussed_questions} />
          </SummarySubsection>
          <SummarySubsection title="表现亮点">
            <DetailList items={conversationSummary?.performance_highlights} />
          </SummarySubsection>
          <SummarySubsection title="需要打磨">
            <ImprovementList items={conversationSummary?.improvement_areas} />
          </SummarySubsection>
          <SummarySubsection title="能力画像">
            <AbilityProfileList items={conversationSummary?.ability_profile} />
          </SummarySubsection>
          <SummarySubsection title="Agent 提供的帮助">
            <BulletList items={conversationSummary?.agent_help} />
          </SummarySubsection>
          <SummarySubsection title="仍可继续">
            <BulletList items={conversationSummary?.open_items} />
          </SummarySubsection>
          <SummarySubsection title="后续练习建议">
            <BulletList items={conversationSummary?.next_practice_steps} />
          </SummarySubsection>
          <BulletList items={summary.practice_notes} />
        </div>
      </Section>
    );
  }
  return (
    <Section title="总结" icon={<FileText className="text-amber-500" />}>
      <div className="space-y-3">
        <MetadataRows
          items={[
            { label: '下一步练习', value: summary.next_practice_suggestion },
            {
              label: '已完成回答教练',
              value:
                typeof completion?.answer_coached === 'boolean'
                  ? formatWorkflowValue(String(completion.answer_coached))
                  : undefined,
            },
            {
              label: '已完成追问',
              value:
                typeof completion?.follow_up_completed === 'boolean'
                  ? formatWorkflowValue(String(completion.follow_up_completed))
                  : undefined,
            },
            {
              label: '总结范围',
              value: formatWorkflowValue(completion?.summary_scope),
            },
          ]}
        />
        <BulletList items={summary.covered_evidence} />
        <BulletList items={summary.missed_evidence} />
        <BulletList items={summary.practice_notes} />
      </div>
    </Section>
  );
}

function NoticesSection({ payload }: { payload: GitHubRepoInterviewWorkflowPayload }) {
  const notices = [
    ...(payload.errors || []).map((notice) => ({ ...notice, severity: 'error' as const })),
    ...(payload.warnings || []).map((notice) => ({ ...notice, severity: 'warning' as const })),
  ];
  if (!notices.length) return null;
  return (
    <Section title="警告 / 错误" icon={<AlertTriangle className="text-rose-500" />}>
      <div className="space-y-2">
        {notices.map((notice, index) => (
          <div
            key={`${notice.code || 'notice'}-${index}`}
            className={
              notice.severity === 'error'
                ? 'border border-rose-100 bg-rose-50 px-3 py-2 text-sm text-rose-800 dark:border-rose-900/60 dark:bg-rose-950/30 dark:text-rose-300'
                : 'border border-amber-100 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-300'
            }
          >
            <div className="font-medium">{notice.code || 'notice'}</div>
            <TextBlock>{notice.message}</TextBlock>
          </div>
        ))}
      </div>
    </Section>
  );
}

function NextStepSection({ payload }: { payload: GitHubRepoInterviewWorkflowPayload }) {
  if (!hasText(payload.next_step)) return null;
  return (
    <Section title="下一步" icon={<Info className="text-teal-500" />}>
      <TextBlock>{payload.next_step}</TextBlock>
    </Section>
  );
}

function hasMeaningfulPayload(payload: GitHubRepoInterviewWorkflowPayload): boolean {
  return Boolean(
    payload.data?.workflow ||
      payload.data?.selected_question ||
      payload.data?.evidence_policy ||
      payload.data?.context_policy ||
      payload.data?.context_snapshot ||
      payload.data?.multi_agent_trace ||
      payload.data?.memory_candidates?.length ||
      payload.data?.saved_memory_context?.length ||
      payload.data?.session_memory_context ||
      payload.data?.session_memory_patch ||
      payload.data?.vector_memory_candidate ||
      payload.data?.vector_memory_retrieval ||
      payload.data?.answer_quality_signals?.length ||
      payload.data?.evidence_details?.length ||
      payload.data?.answer_feedback ||
      payload.data?.follow_up ||
      payload.data?.other_questions?.length ||
      payload.data?.session_summary ||
      payload.warnings?.length ||
      payload.errors?.length ||
      payload.next_step,
  );
}

export const GitHubRepoInterviewWorkflowToolView: React.FC<ToolViewProps> = ({
  name = 'github-repo-interview-workflow',
  assistantContent,
  toolContent,
  assistantTimestamp,
  toolTimestamp,
  isSuccess = true,
  isStreaming = false,
  ...props
}) => {
  const payload = extractGitHubRepoInterviewWorkflowData(
    toolContent,
    assistantContent,
  );

  if (!payload || !hasMeaningfulPayload(payload)) {
    return (
      <GenericToolView
        name={name}
        assistantContent={assistantContent}
        toolContent={toolContent}
        assistantTimestamp={assistantTimestamp}
        toolTimestamp={toolTimestamp}
        isSuccess={isSuccess}
        isStreaming={isStreaming}
        {...props}
      />
    );
  }

  const title = getToolTitle(name);
  const status = isStreaming
    ? 'running'
    : payload.status || (isSuccess ? 'success' : 'error');
  const primarySectionIds = new Set(
    buildGitHubRepoInterviewPrimaryPanelSectionIds(payload),
  );

  return (
    <Card className="gap-0 flex border shadow-none border-t border-b-0 border-x-0 p-0 rounded-none flex-col h-full overflow-hidden bg-card">
      <CardHeader className="flex h-16 items-center border-b bg-zinc-50/80 px-4 py-0 !pb-0 backdrop-blur-sm dark:bg-zinc-900/80">
        <div className="relative flex h-full w-full min-w-0 items-center justify-center">
          <div className="absolute left-0 flex items-center">
            <div className="relative flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-cyan-500/20 bg-gradient-to-br from-cyan-500/20 to-emerald-500/10">
              <Github className="h-6 w-6 text-cyan-600 dark:text-cyan-400" />
            </div>
          </div>
          <CardTitle className="mx-14 min-w-0 truncate text-center text-base font-medium text-zinc-900 dark:text-zinc-100">
            {title}
          </CardTitle>
          <div className="absolute right-0 flex items-center">
            <StatusBadge status={status} isStreaming={isStreaming} />
          </div>
        </div>
      </CardHeader>

      <CardContent className="relative h-full flex-1 overflow-hidden p-0">
        <ScrollArea className="h-full w-full">
          {primarySectionIds.has('workflow_steps') ? (
            <WorkflowSteps steps={payload.data?.workflow?.steps} payload={payload} />
          ) : null}
          {primarySectionIds.has('multi_agent_trace') ? (
            <MultiAgentTraceSection payload={payload} />
          ) : null}
          {primarySectionIds.has('boundary_details') ? (
            <BoundaryDetailsSection payload={payload} />
          ) : null}
          {primarySectionIds.has('selected_question') ? (
            <QuestionSection payload={payload} />
          ) : null}
          {primarySectionIds.has('answer_feedback') ? (
            <FeedbackSection payload={payload} />
          ) : null}
          {primarySectionIds.has('follow_up') ? (
            <FollowUpSection payload={payload} />
          ) : null}
          {primarySectionIds.has('other_questions') ? (
            <OtherQuestionsSection payload={payload} />
          ) : null}
          {primarySectionIds.has('session_summary') ? (
            <SummarySection payload={payload} />
          ) : null}
          {primarySectionIds.has('session_memory') ? (
            <SessionMemorySection payload={payload} />
          ) : null}
          {primarySectionIds.has('memory_candidates') ? (
            <MemoryCandidatesSection payload={payload} />
          ) : null}
          {primarySectionIds.has('vector_memory_candidate') ? (
            <VectorMemoryCandidateSection payload={payload} />
          ) : null}
          {primarySectionIds.has('vector_memory_retrieval') ? (
            <VectorMemoryRetrievalSection payload={payload} />
          ) : null}
          {primarySectionIds.has('notices') ? (
            <NoticesSection payload={payload} />
          ) : null}
          {primarySectionIds.has('next_step') ? (
            <NextStepSection payload={payload} />
          ) : null}
        </ScrollArea>
      </CardContent>

      <div className="flex h-10 items-center justify-between gap-4 border-t border-zinc-200 bg-gradient-to-r from-zinc-50/90 to-zinc-100/90 px-4 py-2 backdrop-blur-sm dark:border-zinc-800 dark:from-zinc-900/90 dark:to-zinc-800/90">
        <div className="flex h-full min-w-0 items-center gap-2 text-sm text-zinc-500 dark:text-zinc-400">
          {hasText(payload.input?.question_id) && (
            <Badge
              variant="outline"
              className="h-6 max-w-[12rem] truncate bg-zinc-50 py-0.5 dark:bg-zinc-900"
            >
              {payload.input.question_id}
            </Badge>
          )}
        </div>
        <div className="flex min-w-0 items-center gap-2 truncate text-xs text-zinc-500 dark:text-zinc-400">
          <Clock className="h-3.5 w-3.5 shrink-0" />
          <span className="truncate">
            {toolTimestamp && !isStreaming
              ? formatTimestamp(toolTimestamp)
              : assistantTimestamp
                ? formatTimestamp(assistantTimestamp)
                : ''}
          </span>
        </div>
      </div>
    </Card>
  );
};
