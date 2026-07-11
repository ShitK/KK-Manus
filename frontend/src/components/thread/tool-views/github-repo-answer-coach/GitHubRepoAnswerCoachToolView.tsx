import type React from 'react';
import {
  AlertTriangle,
  CheckCircle,
  Clock,
  FileText,
  Github,
  HelpCircle,
  Info,
  Lightbulb,
  ListChecks,
  MessageSquare,
  SearchCheck,
  ShieldCheck,
} from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';

import { GenericToolView } from '../GenericToolView';
import type { ToolViewProps } from '../types';
import { formatTimestamp, getToolTitle } from '../utils';
import {
  formatGitHubInterviewCategory,
  formatGitHubInterviewDifficulty,
} from '../github-repo-interview-categories';
import {
  extractGitHubRepoAnswerCoachData,
  type GitHubRepoAnswerCoachPayload,
} from './_utils';

function hasText(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0;
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => hasText(item))
    : [];
}

function isEnglish(payload: GitHubRepoAnswerCoachPayload): boolean {
  return payload.input?.language === 'en';
}

function getLabels(payload: GitHubRepoAnswerCoachPayload) {
  const en = isEnglish(payload);

  return {
    statusFailed: en ? 'Failed' : '失败',
    statusPartial: en ? 'Partial' : '部分完成',
    statusRunning: en ? 'Running' : '运行中',
    statusReady: en ? 'Coached' : '已反馈',
    question: en ? 'Question' : '问题',
    userAnswer: en ? 'User Answer' : '用户回答',
    feedbackSummary: en ? 'Feedback Summary' : '反馈摘要',
    strengths: en ? 'Strengths' : '亮点',
    gaps: en ? 'Gaps' : '缺口',
    evidenceMissed: en ? 'Evidence Missed' : '遗漏证据',
    suggestedAnswerOutline: en
      ? 'Suggested Answer Outline'
      : '建议回答提纲',
    followUpQuestions: en ? 'Follow-up Questions' : '追问',
    groundingNotes: en ? 'Grounding Notes' : '证据约束说明',
    warningsErrors: en ? 'Warnings / Errors' : '警告 / 错误',
    nextStep: en ? 'Next Step' : '下一步',
    id: en ? 'ID' : '编号',
    category: en ? 'Category' : '类别',
    difficulty: en ? 'Difficulty' : '难度',
    coachStyle: en ? 'Coach style' : '反馈风格',
    maxFollowUps: en ? 'Max follow-ups' : '最多追问数',
    retryable: en ? 'Retryable' : '可重试',
    warning: en ? 'warning' : '警告',
    error: en ? 'error' : '错误',
  };
}

function StatusBadge({
  status,
  payload,
}: {
  status?: string;
  payload: GitHubRepoAnswerCoachPayload;
}) {
  const labels = getLabels(payload);
  const isError = status === 'error';
  const isPartial = status === 'partial';
  const isRunning = status === 'running';

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
      ) : isPartial ? (
        <Info className="h-3.5 w-3.5" />
      ) : isRunning ? (
        <Clock className="h-3.5 w-3.5" />
      ) : (
        <CheckCircle className="h-3.5 w-3.5" />
      )}
      {isError
        ? labels.statusFailed
        : isPartial
          ? labels.statusPartial
          : isRunning
            ? labels.statusRunning
            : labels.statusReady}
    </Badge>
  );
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
  if (!hasText(children)) {
    return null;
  }

  return (
    <p className="min-w-0 whitespace-pre-wrap break-words text-sm leading-relaxed text-zinc-600 dark:text-zinc-300">
      {children}
    </p>
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

  if (!visibleItems.length) {
    return null;
  }

  return (
    <div className="divide-y divide-zinc-100 border-y border-zinc-100 dark:divide-zinc-800 dark:border-zinc-800">
      {visibleItems.map((item) => (
        <div
          key={item.label}
          className="grid gap-1 py-2 text-sm sm:grid-cols-[7rem_1fr] sm:gap-3"
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

function BulletList({
  items,
  ordered = false,
}: {
  items?: string[];
  ordered?: boolean;
}) {
  const visible = asStringArray(items);
  if (!visible.length) {
    return null;
  }

  const ListTag = ordered ? 'ol' : 'ul';

  return (
    <ListTag className="space-y-2">
      {visible.map((item, index) => (
        <li
          key={`${item}-${index}`}
          className="flex gap-2 text-sm leading-relaxed text-zinc-600 dark:text-zinc-300"
        >
          <span className="mt-2 flex h-1.5 w-1.5 shrink-0 rounded-full bg-zinc-300 dark:bg-zinc-600" />
          <span className="min-w-0 break-words">{item}</span>
        </li>
      ))}
    </ListTag>
  );
}

function QuestionSection({
  payload,
}: {
  payload: GitHubRepoAnswerCoachPayload;
}) {
  const labels = getLabels(payload);
  const question = payload.data?.question;

  if (!question && !hasText(payload.input?.question_id)) {
    return null;
  }

  return (
    <Section title={labels.question} icon={<HelpCircle className="text-sky-500" />}>
      <div className="space-y-3">
        <MetadataRows
          items={[
            { label: labels.id, value: question?.id || payload.input?.question_id },
            {
              label: labels.category,
              value: isEnglish(payload)
                ? question?.category
                : formatGitHubInterviewCategory(question?.category),
            },
            {
              label: labels.difficulty,
              value: isEnglish(payload)
                ? question?.difficulty
                : formatGitHubInterviewDifficulty(question?.difficulty),
            },
          ]}
        />
        <TextBlock>{question?.question}</TextBlock>
      </div>
    </Section>
  );
}

function UserAnswerSection({
  payload,
}: {
  payload: GitHubRepoAnswerCoachPayload;
}) {
  const labels = getLabels(payload);
  const answer =
    payload.data?.user_answer_summary ||
    payload.data?.user_answer_excerpt ||
    payload.input?.user_answer_summary ||
    payload.input?.user_answer_excerpt ||
    payload.input?.user_answer;

  if (!hasText(answer)) {
    return null;
  }

  return (
    <Section
      title={labels.userAnswer}
      icon={<MessageSquare className="text-cyan-500" />}
    >
      <div className="space-y-3">
        <TextBlock>{answer}</TextBlock>
        <MetadataRows
          items={[
            { label: labels.coachStyle, value: payload.input?.coach_style },
            { label: labels.maxFollowUps, value: payload.input?.max_follow_ups },
          ]}
        />
      </div>
    </Section>
  );
}

function FeedbackSummarySection({
  payload,
}: {
  payload: GitHubRepoAnswerCoachPayload;
}) {
  const labels = getLabels(payload);
  const summary = payload.data?.answer_feedback?.summary;

  if (!hasText(summary)) {
    return null;
  }

  return (
    <Section
      title={labels.feedbackSummary}
      icon={<SearchCheck className="text-emerald-500" />}
    >
      <TextBlock>{summary}</TextBlock>
    </Section>
  );
}

function ListSection({
  title,
  icon,
  items,
  ordered,
}: {
  title: string;
  icon: React.ReactNode;
  items?: string[];
  ordered?: boolean;
}) {
  if (!asStringArray(items).length) {
    return null;
  }

  return (
    <Section title={title} icon={icon}>
      <BulletList items={items} ordered={ordered} />
    </Section>
  );
}

function EvidenceMissedSection({
  payload,
}: {
  payload: GitHubRepoAnswerCoachPayload;
}) {
  const labels = getLabels(payload);
  const missed = payload.data?.answer_feedback?.evidence_missed || [];

  if (!missed.length) {
    return null;
  }

  return (
    <Section
      title={labels.evidenceMissed}
      icon={<FileText className="text-amber-500" />}
    >
      <div className="divide-y divide-zinc-100 dark:divide-zinc-800">
        {missed.map((item, index) => (
          <div
            key={`${item.evidence_id || item.source_path || 'evidence'}-${index}`}
            className="py-3 first:pt-0 last:pb-0"
          >
            <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
              {hasText(item.evidence_id) && (
                <span className="inline-flex h-6 max-w-full items-center truncate rounded-md border border-amber-200 bg-amber-50 px-2 text-xs font-medium text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
                  {item.evidence_id}
                </span>
              )}
              {hasText(item.source_path) && (
                <span className="min-w-0 max-w-full break-words text-sm font-medium text-zinc-800 dark:text-zinc-100">
                  {item.source_path}
                </span>
              )}
            </div>
            <TextBlock>{item.reason}</TextBlock>
          </div>
        ))}
      </div>
    </Section>
  );
}

function NoticesSection({
  payload,
}: {
  payload: GitHubRepoAnswerCoachPayload;
}) {
  const labels = getLabels(payload);
  const warnings = payload.warnings || [];
  const errors = payload.errors || [];

  if (!warnings.length && !errors.length) {
    return null;
  }

  return (
    <Section
      title={labels.warningsErrors}
      icon={<AlertTriangle className="text-rose-500" />}
    >
      <div className="space-y-2">
        {warnings.map((warning, index) => (
          <div
            key={`${warning.code || 'warning'}-${index}`}
            className="border border-amber-100 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-300"
          >
            <div className="font-medium">{warning.code || labels.warning}</div>
            {hasText(warning.message) && (
              <div className="mt-1 break-words">{warning.message}</div>
            )}
            {warning.retryable === true && (
              <div className="mt-1 text-xs text-amber-600 dark:text-amber-400">
                {labels.retryable}
              </div>
            )}
          </div>
        ))}
        {errors.map((error, index) => (
          <div
            key={`${error.code || 'error'}-${index}`}
            className="border border-rose-100 bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:border-rose-900/60 dark:bg-rose-950/30 dark:text-rose-300"
          >
            <div className="font-medium">{error.code || labels.error}</div>
            {hasText(error.message) && (
              <div className="mt-1 break-words">{error.message}</div>
            )}
            {error.retryable === true && (
              <div className="mt-1 text-xs text-rose-500 dark:text-rose-400">
                {labels.retryable}
              </div>
            )}
          </div>
        ))}
      </div>
    </Section>
  );
}

function NextStepSection({
  payload,
}: {
  payload: GitHubRepoAnswerCoachPayload;
}) {
  const labels = getLabels(payload);

  if (!hasText(payload.next_step)) {
    return null;
  }

  return (
    <Section title={labels.nextStep} icon={<Info className="text-teal-500" />}>
      <TextBlock>{payload.next_step}</TextBlock>
    </Section>
  );
}

function hasMeaningfulPayload(payload: GitHubRepoAnswerCoachPayload): boolean {
  const feedback = payload.data?.answer_feedback;

  return Boolean(
    payload.data?.question ||
      payload.input?.question_id ||
      payload.data?.user_answer_summary ||
      payload.data?.user_answer_excerpt ||
      payload.input?.user_answer_summary ||
      payload.input?.user_answer_excerpt ||
      payload.input?.user_answer ||
      feedback?.summary ||
      feedback?.strengths?.length ||
      feedback?.gaps?.length ||
      feedback?.evidence_missed?.length ||
      feedback?.suggested_answer_outline?.length ||
      feedback?.follow_up_questions?.length ||
      feedback?.grounding_notes?.length ||
      payload.errors?.length ||
      payload.warnings?.length ||
      payload.next_step,
  );
}

function getPayloadStatus(
  payload: GitHubRepoAnswerCoachPayload,
  isSuccess: boolean,
  isStreaming: boolean,
): string {
  if (isStreaming) {
    return 'running';
  }

  if (payload.status) {
    return payload.status;
  }

  if (payload.partial) {
    return 'partial';
  }

  return isSuccess ? 'success' : 'error';
}

export const GitHubRepoAnswerCoachToolView: React.FC<ToolViewProps> = ({
  name = 'github-repo-answer-coach',
  assistantContent,
  toolContent,
  assistantTimestamp,
  toolTimestamp,
  isSuccess = true,
  isStreaming = false,
  ...props
}) => {
  const payload = extractGitHubRepoAnswerCoachData(
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

  const labels = getLabels(payload);
  const feedback = payload.data?.answer_feedback;
  const title = getToolTitle(name);
  const status = getPayloadStatus(payload, isSuccess, isStreaming);

  return (
    <Card className="gap-0 flex border shadow-none border-t border-b-0 border-x-0 p-0 rounded-none flex-col h-full overflow-hidden bg-card">
      <CardHeader className="flex h-16 items-center border-b bg-zinc-50/80 px-4 py-0 !pb-0 backdrop-blur-sm dark:bg-zinc-900/80">
        <div className="relative flex h-full w-full min-w-0 items-center justify-center">
          <div className="absolute left-0 flex items-center">
            <div className="relative flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-emerald-500/20 bg-gradient-to-br from-emerald-500/20 to-sky-500/10">
              <Github className="h-6 w-6 text-emerald-600 dark:text-emerald-400" />
            </div>
          </div>

          <CardTitle className="mx-14 min-w-0 truncate text-center text-base font-medium text-zinc-900 dark:text-zinc-100">
            {title}
          </CardTitle>

          <div className="absolute right-0 flex items-center">
            <StatusBadge status={status} payload={payload} />
          </div>
        </div>
      </CardHeader>

      <CardContent className="relative h-full flex-1 overflow-hidden p-0">
        <ScrollArea className="h-full w-full">
          <QuestionSection payload={payload} />
          <UserAnswerSection payload={payload} />
          <FeedbackSummarySection payload={payload} />
          <ListSection
            title={labels.strengths}
            icon={<ShieldCheck className="text-emerald-500" />}
            items={feedback?.strengths}
          />
          <ListSection
            title={labels.gaps}
            icon={<AlertTriangle className="text-rose-500" />}
            items={feedback?.gaps}
          />
          <EvidenceMissedSection payload={payload} />
          <ListSection
            title={labels.suggestedAnswerOutline}
            icon={<ListChecks className="text-violet-500" />}
            items={feedback?.suggested_answer_outline}
            ordered
          />
          <ListSection
            title={labels.followUpQuestions}
            icon={<MessageSquare className="text-sky-500" />}
            items={feedback?.follow_up_questions}
          />
          <ListSection
            title={labels.groundingNotes}
            icon={<Lightbulb className="text-amber-500" />}
            items={feedback?.grounding_notes}
          />
          <NoticesSection payload={payload} />
          <NextStepSection payload={payload} />
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
