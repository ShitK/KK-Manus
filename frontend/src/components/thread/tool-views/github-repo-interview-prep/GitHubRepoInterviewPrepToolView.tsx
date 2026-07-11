import type React from 'react';
import {
  AlertTriangle,
  BookOpenCheck,
  CheckCircle,
  Clock,
  FileCode2,
  FolderTree,
  Github,
  HelpCircle,
  Info,
  Loader2,
  PackageSearch,
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
  getGitHubInterviewCategoryLabel,
} from '../github-repo-interview-categories';
import {
  extractGitHubRepoInterviewPrepData,
  type GitHubRepoEvidenceDetail,
  type GitHubRepoInterviewPrepPayload,
  type GitHubRepoStep,
} from './_utils';

function hasText(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0;
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => hasText(item))
    : [];
}

function formatStatusLabel(status?: string): string {
  if (status === 'error') return '失败';
  if (status === 'partial') return '部分完成';
  if (status === 'running') return '运行中';
  if (status === 'pending') return '等待中';
  return '已准备';
}

const STEP_LABELS_ZH: Record<string, string> = {
  'Parse GitHub URL': '解析 GitHub URL',
  'Fetch repository metadata': '获取仓库 metadata',
  'Inspect repository tree': '检查仓库目录树',
  'Select interview-relevant files': '选择面试相关文件',
  'Read selected files': '读取已选文件',
  'Read README': '读取 README',
  'Build context pack': '构建上下文包',
  'Generate interview questions': '生成面试问题',
  'Enforce public repository boundary': '检查公开仓库边界',
};

function formatStepLabel(label?: string, fallback?: string): string {
  const value = label || fallback;
  if (!hasText(value)) return '步骤';
  return STEP_LABELS_ZH[value] || value;
}

function formatStepDetail(detail?: string): string | undefined {
  if (!hasText(detail)) return undefined;
  const entriesMatch = detail.match(/^(\d+) entr(?:y|ies)$/);
  if (entriesMatch) return `${entriesMatch[1]} 个条目`;
  const filesReadMatch = detail.match(/^(\d+) files? read$/);
  if (filesReadMatch) return `已读取 ${filesReadMatch[1]} 个文件`;
  const selectedMatch = detail.match(/^(\d+) manifests?, (\d+) source files?$/);
  if (selectedMatch) {
    return `${selectedMatch[1]} 个 manifest 文件，${selectedMatch[2]} 个 source file`;
  }
  if (detail.startsWith('default branch: ')) {
    return detail.replace('default branch: ', '默认分支: ');
  }
  if (detail === 'manifest, directory, source evidence ready') {
    return 'manifest、目录、source evidence 已就绪';
  }
  if (detail === 'tree unavailable') return '目录树不可用';
  return detail;
}

function formatBoolean(value?: boolean): string {
  return value ? '是' : '否';
}

function formatEvidenceAvailability(value?: boolean): string | undefined {
  if (typeof value !== 'boolean') return undefined;
  return value ? '可用' : '有限';
}

const DISPLAY_TERMS_ZH: Record<string, string> = {
  'application or package entrypoint': '应用或包入口',
  'source file': 'source file',
  'configuration or manifest': '配置或 manifest',
  junior: '初级',
  mid: '中级',
  senior: '高级',
  high: '高',
  medium: '中',
  low: '低',
};

function formatDisplayTerm(value?: string): string | undefined {
  if (!hasText(value)) return value;
  return DISPLAY_TERMS_ZH[value] || value;
}

function formatSummaryText(value?: string): string | undefined {
  if (!hasText(value)) return value;

  const fileSummaryMatch = value.match(
    /^([^ ]+) is (?:an|a) (.+) \((\d+ bytes|unknown size)\) with (.+?)\.( The fetched excerpt was truncated\.)?$/,
  );
  if (fileSummaryMatch) {
    const [, path, role, size, symbols, truncated] = fileSummaryMatch;
    const sizeText = size === 'unknown size' ? '大小未知' : size.replace(' bytes', ' 字节');
    const symbolText =
      symbols === 'no top-level symbols detected'
        ? '未检测到顶层符号'
        : symbols.replace(/, /g, '、');
    return `${path} 是${formatDisplayTerm(role)}（${sizeText}），识别到 ${symbolText}。${truncated ? ' 获取到的 excerpt 已截断。' : ''}`;
  }

  const manifestSummaryMatch = value.match(/^(.+) manifest with (\d+) detected dependencies\.$/);
  if (manifestSummaryMatch) {
    return `${manifestSummaryMatch[1]} manifest，检测到 ${manifestSummaryMatch[2]} 个依赖。`;
  }

  const directorySummaryMatch = value.match(
    /^Repository tree includes (\d+) entries and (\d+) top-level source\/documentation areas\.$/,
  );
  if (directorySummaryMatch) {
    return `仓库目录树包含 ${directorySummaryMatch[1]} 个条目和 ${directorySummaryMatch[2]} 个顶层源码/文档区域。`;
  }

  return value;
}

function StatusBadge({ status }: { status?: string }) {
  const isError = status === 'error';
  const isPartial = status === 'partial';
  const isRunning = status === 'running';
  const isPending = status === 'pending';

  return (
    <Badge
      variant="outline"
      className={
        isError
          ? 'h-6 gap-1.5 border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-800 dark:bg-rose-900/20 dark:text-rose-400'
          : isPartial
            ? 'h-6 gap-1.5 border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-400'
            : isRunning || isPending
              ? 'h-6 gap-1.5 border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-800 dark:bg-sky-900/20 dark:text-sky-400'
              : 'h-6 gap-1.5 border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-900/20 dark:text-emerald-400'
      }
    >
      {isError ? (
        <AlertTriangle className="h-3.5 w-3.5" />
      ) : isPartial ? (
        <Info className="h-3.5 w-3.5" />
      ) : isRunning ? (
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
      ) : isPending ? (
        <Clock className="h-3.5 w-3.5" />
      ) : (
        <CheckCircle className="h-3.5 w-3.5" />
      )}
      {formatStatusLabel(status)}
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

function InlineList({
  items,
  limit = 6,
}: {
  items?: string[];
  limit?: number;
}) {
  const visible = asStringArray(items).slice(0, limit);
  if (!visible.length) {
    return null;
  }

  return (
    <div className="flex min-w-0 flex-wrap gap-x-3 gap-y-1 text-sm text-zinc-500 dark:text-zinc-400">
      {visible.map((item, index) => (
        <span
          key={`${item}-${index}`}
          className="min-w-0 max-w-full break-words"
        >
          {item}
        </span>
      ))}
    </div>
  );
}

function EvidenceDetails({
  details,
  language,
}: {
  details?: GitHubRepoEvidenceDetail[];
  language?: unknown;
}) {
  const visible = Array.isArray(details) ? details.slice(0, 3) : [];
  if (!visible.length) {
    return null;
  }
  const isZh = language === 'zh';
  const title = isZh ? '证据详情' : 'Evidence details';
  const whyLabel = isZh ? '为什么相关:' : 'Why it matters:';

  return (
    <div className="space-y-2">
      <div className="text-xs font-medium uppercase tracking-wide text-zinc-400">
        {title}
      </div>
      <div className="space-y-2">
        {visible.map((detail, index) => {
          const readable = formatSummaryText(detail.summary) || detail.snippet;
          return (
            <div
              key={`${detail.evidence_id || detail.source_path || 'detail'}-${index}`}
              className="min-w-0 border-l border-cyan-200 pl-3 text-sm leading-relaxed dark:border-cyan-900"
            >
              <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
                <span className="min-w-0 max-w-full break-words font-medium text-zinc-800 dark:text-zinc-100">
                  {detail.source_path || (isZh ? '仓库证据' : 'repository evidence')}
                </span>
                {hasText(detail.evidence_type) && (
                  <span className="text-xs uppercase tracking-wide text-cyan-600 dark:text-cyan-400">
                    {detail.evidence_type}
                  </span>
                )}
                {hasText(detail.confidence) && (
                  <span className="text-xs text-zinc-400 dark:text-zinc-500">
                    {detail.confidence}
                  </span>
                )}
              </div>
              {hasText(readable) && (
                <div className="mt-1 whitespace-pre-wrap break-words text-zinc-600 dark:text-zinc-300">
                  {readable}
                </div>
              )}
              {hasText(detail.why_it_matters) && (
                <div className="mt-1 break-words text-zinc-500 dark:text-zinc-400">
                  <span className="font-medium text-zinc-600 dark:text-zinc-300">
                    {whyLabel}
                  </span>{' '}
                  {detail.why_it_matters}
                </div>
              )}
            </div>
          );
        })}
      </div>
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

function StepList({ steps }: { steps: GitHubRepoStep[] }) {
  if (!steps.length) {
    return null;
  }

  return (
    <Section title="执行步骤" icon={<CheckCircle className="text-emerald-500" />}>
      <div className="divide-y divide-zinc-100 dark:divide-zinc-800">
        {steps.map((step, index) => (
          <div
            key={`${step.id || 'step'}-${index}`}
            className="flex gap-3 py-3 first:pt-0 last:pb-0"
          >
            <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-zinc-200 bg-white text-zinc-500 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-400">
              {step.status === 'error' ? (
                <AlertTriangle className="h-3.5 w-3.5 text-rose-500" />
              ) : step.status === 'partial' ? (
                <Info className="h-3.5 w-3.5 text-amber-500" />
              ) : step.status === 'running' ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin text-sky-500" />
              ) : step.status === 'pending' ? (
                <Clock className="h-3.5 w-3.5 text-zinc-400" />
              ) : (
                <CheckCircle className="h-3.5 w-3.5 text-emerald-500" />
              )}
            </div>
            <div className="min-w-0">
              <div className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
                {formatStepLabel(step.label, step.id || `步骤 ${index + 1}`)}
              </div>
              {hasText(step.detail) && (
                <div className="mt-1 break-words text-sm leading-relaxed text-zinc-500 dark:text-zinc-400">
                  {formatStepDetail(step.detail)}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </Section>
  );
}

function ErrorList({ payload }: { payload: GitHubRepoInterviewPrepPayload }) {
  const errors = payload.errors || [];

  if (!errors.length) {
    return null;
  }

  return (
    <Section title="错误" icon={<AlertTriangle className="text-rose-500" />}>
      <div className="space-y-2">
        {errors.map((error, index) => (
          <div
            key={`${error.code || 'error'}-${index}`}
            className="border border-rose-100 bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:border-rose-900/60 dark:bg-rose-950/30 dark:text-rose-300"
          >
            <div className="font-medium">{error.code || 'error'}</div>
            {hasText(error.message) && (
              <div className="mt-1 break-words">{error.message}</div>
            )}
            {error.retryable === true && (
              <div className="mt-1 text-xs text-rose-500 dark:text-rose-400">
                可重试
              </div>
            )}
          </div>
        ))}
      </div>
    </Section>
  );
}

function WarningList({ payload }: { payload: GitHubRepoInterviewPrepPayload }) {
  const warnings = payload.warnings || [];

  if (!warnings.length) {
    return null;
  }

  return (
    <Section title="警告" icon={<Info className="text-amber-500" />}>
      <div className="space-y-2">
        {warnings.map((warning, index) => (
          <div
            key={`${warning.code || 'warning'}-${index}`}
            className="border border-amber-100 bg-amber-50 px-3 py-2 text-sm text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-300"
          >
            <div className="font-medium">{warning.code || 'warning'}</div>
            {hasText(warning.message) && (
              <div className="mt-1 break-words">{warning.message}</div>
            )}
            {warning.retryable === true && (
              <div className="mt-1 text-xs text-amber-600 dark:text-amber-400">
                可重试
              </div>
            )}
          </div>
        ))}
      </div>
    </Section>
  );
}

function RepositoryMetadata({
  payload,
}: {
  payload: GitHubRepoInterviewPrepPayload;
}) {
  const metadata = payload.data?.repo_metadata;

  if (!metadata) {
    return null;
  }

  return (
    <Section title="仓库信息" icon={<Github className="text-sky-500" />}>
      <MetadataRows
        items={[
          { label: '仓库', value: metadata.full_name },
          { label: '默认分支', value: metadata.default_branch },
          { label: '主要语言', value: metadata.primary_language },
          {
            label: 'Stars',
            value:
              typeof metadata.stars === 'number'
                ? metadata.stars.toLocaleString()
                : '',
          },
          { label: 'URL', value: metadata.html_url },
          { label: '描述', value: metadata.description },
        ]}
      />
    </Section>
  );
}

function ReadmePreview({
  payload,
}: {
  payload: GitHubRepoInterviewPrepPayload;
}) {
  const readme = payload.data?.readme;
  const summary = payload.data?.project_context_pack?.readme_summary?.summary;
  const excerpt = readme?.text_excerpt;

  if (!readme && !hasText(summary) && !hasText(excerpt)) {
    return null;
  }

  return (
    <Section title="README" icon={<BookOpenCheck className="text-sky-500" />}>
      <div className="space-y-3">
        {readme && (
          <div className="text-sm text-zinc-500 dark:text-zinc-400">
            {readme.path || 'README'} · {readme.size || 0} 字节
            {readme.truncated ? ' · 显示 excerpt' : ''}
          </div>
        )}
        {hasText(summary) && (
          <blockquote className="border-l-2 border-sky-200 pl-4 text-sm leading-6 text-zinc-700 dark:border-sky-900 dark:text-zinc-300">
            {summary}
          </blockquote>
        )}
        {hasText(excerpt) && (
          <div className="rounded-md border border-zinc-100 bg-zinc-50 px-3 py-2 dark:border-zinc-800 dark:bg-zinc-900/60">
            <TextBlock>{excerpt}</TextBlock>
          </div>
        )}
      </div>
    </Section>
  );
}

function ProjectStructure({
  payload,
}: {
  payload: GitHubRepoInterviewPrepPayload;
}) {
  const directory = payload.data?.project_context_pack?.directory_summary;

  if (!directory) {
    return null;
  }

  return (
    <Section
      title="项目结构"
      icon={<FolderTree className="text-sky-500" />}
    >
      <div className="space-y-3">
        <MetadataRows
          items={[
            { label: '条目数', value: directory.total_entries },
            { label: '是否截断', value: formatBoolean(directory.truncated) },
          ]}
        />
        <TextBlock>{formatSummaryText(directory.summary)}</TextBlock>
        <div className="space-y-1">
          <div className="text-xs font-medium uppercase tracking-wide text-zinc-400">
            顶层目录
          </div>
          <InlineList items={directory.top_level_dirs} />
        </div>
        <div className="space-y-1">
          <div className="text-xs font-medium uppercase tracking-wide text-zinc-400">
            关键路径
          </div>
          <InlineList items={directory.notable_paths} limit={10} />
        </div>
      </div>
    </Section>
  );
}

function ManifestFiles({
  payload,
}: {
  payload: GitHubRepoInterviewPrepPayload;
}) {
  const manifests = payload.data?.project_context_pack?.manifest_summary || [];

  if (!manifests.length) {
    return null;
  }

  return (
    <Section
      title="Manifest 文件"
      icon={<PackageSearch className="text-emerald-500" />}
    >
      <div className="divide-y divide-zinc-100 dark:divide-zinc-800">
        {manifests.map((manifest, index) => (
          <div
            key={manifest.path || manifest.ecosystem || `manifest-${index}`}
            className="py-3 first:pt-0 last:pb-0"
          >
            <div className="flex min-w-0 flex-wrap items-baseline gap-x-3 gap-y-1">
              <span className="min-w-0 max-w-full break-words font-medium text-zinc-900 dark:text-zinc-100">
                {manifest.path || 'manifest'}
              </span>
              {hasText(manifest.ecosystem) && (
                <span className="min-w-0 max-w-full break-words text-sm text-emerald-600 dark:text-emerald-400">
                  {manifest.ecosystem}
                </span>
              )}
            </div>
            <TextBlock>{formatSummaryText(manifest.summary)}</TextBlock>
            <InlineList items={manifest.dependencies} limit={12} />
          </div>
        ))}
      </div>
    </Section>
  );
}

function SourceEvidence({
  payload,
}: {
  payload: GitHubRepoInterviewPrepPayload;
}) {
  const files = payload.data?.project_context_pack?.file_summaries || [];

  if (!files.length) {
    return null;
  }

  return (
    <Section
      title="源码证据"
      icon={<FileCode2 className="text-cyan-500" />}
    >
      <div className="divide-y divide-zinc-100 dark:divide-zinc-800">
        {files.slice(0, 8).map((file, index) => (
          <div
            key={file.path || `${file.role || 'source'}-${index}`}
            className="py-3 first:pt-0 last:pb-0"
          >
            <div className="min-w-0 break-words font-medium text-zinc-900 dark:text-zinc-100">
              {file.path || 'source file'}
            </div>
            {(hasText(file.role) || hasText(file.confidence)) && (
              <MetadataRows
                items={[
                  { label: '角色', value: formatDisplayTerm(file.role) },
                  { label: '置信度', value: formatDisplayTerm(file.confidence) },
                ]}
              />
            )}
            <TextBlock>{formatSummaryText(file.summary)}</TextBlock>
            {asStringArray(file.important_symbols).length > 0 && (
              <div className="mt-3 space-y-1">
                <div className="text-xs font-medium uppercase tracking-wide text-zinc-400">
                  关键符号
                </div>
                <InlineList items={file.important_symbols} limit={8} />
              </div>
            )}
            {asStringArray(file.interview_relevance).length > 0 && (
              <div className="mt-3 space-y-1">
                <div className="text-xs font-medium uppercase tracking-wide text-zinc-400">
                  面试相关性
                </div>
                <InlineList items={file.interview_relevance} limit={6} />
              </div>
            )}
          </div>
        ))}
      </div>
    </Section>
  );
}

function InterviewQuestions({
  payload,
}: {
  payload: GitHubRepoInterviewPrepPayload;
}) {
  const questions = payload.data?.interview_questions || [];
  const summary = payload.data?.question_generation_summary;
  const language = payload.input?.language;

  if (!questions.length && !summary) {
    return null;
  }

  return (
    <Section
      title="面试问题"
      icon={<HelpCircle className="text-violet-500" />}
    >
      <div className="space-y-3">
        {summary && (
          <MetadataRows
            items={[
              { label: '已生成', value: summary.generated_count },
              { label: '请求数量', value: summary.requested_count },
              { label: '模板数', value: summary.available_template_count },
              { label: '策略', value: summary.strategy },
              { label: '难度', value: formatDisplayTerm(summary.difficulty) },
              {
                label: '证据',
                value: formatEvidenceAvailability(summary.has_source_evidence),
              },
            ]}
          />
        )}
        {questions.length > 0 && (
          <div className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {questions.map((question, index) => (
              <div
                key={`${question.id || 'question'}-${index}`}
                className="space-y-2.5 py-3 first:pt-0 last:pb-0"
              >
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="inline-flex h-6 items-center rounded-md border border-sky-200 bg-sky-50 px-2 text-xs font-medium uppercase text-sky-700 dark:border-sky-800 dark:bg-sky-900/20 dark:text-sky-300">
                    {question.id || `Q${index + 1}`}
                  </span>
                  {hasText(question.category) && (
                    <span
                      title={formatGitHubInterviewCategory(question.category)}
                      className="inline-flex h-6 max-w-[min(14rem,100%)] items-center truncate rounded-md border border-emerald-200 bg-emerald-50 px-2 text-xs font-normal text-emerald-700 dark:border-emerald-800 dark:bg-emerald-900/20 dark:text-emerald-300"
                    >
                      {getGitHubInterviewCategoryLabel(question.category)}
                    </span>
                  )}
                  {hasText(question.difficulty) && (
                    <span className="inline-flex h-6 max-w-[min(10rem,100%)] items-center truncate rounded-md border border-amber-200 bg-amber-50 px-2 text-xs font-normal text-amber-700 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-300">
                      {formatGitHubInterviewDifficulty(question.difficulty)}
                    </span>
                  )}
                  {hasText(question.confidence) && (
                    <span className="inline-flex h-6 max-w-[min(10rem,100%)] items-center truncate rounded-md border border-violet-200 bg-violet-50 px-2 text-xs font-normal text-violet-700 dark:border-violet-800 dark:bg-violet-900/20 dark:text-violet-300">
                      {question.confidence}
                    </span>
                  )}
                </div>
                <p className="min-w-0 break-words text-sm font-medium leading-relaxed text-zinc-800 dark:text-zinc-100">
                  {question.question}
                </p>
                {hasText(question.answer_direction) && (
                  <div className="border-l border-zinc-200 pl-3 text-sm leading-relaxed text-zinc-600 dark:border-zinc-700 dark:text-zinc-300">
                    <span className="font-medium text-zinc-700 dark:text-zinc-200">
                      回答方向:
                    </span>{' '}
                    <span className="break-words">
                      {question.answer_direction}
                    </span>
                  </div>
                )}
                {asStringArray(question.source_paths).length > 0 && (
                  <div className="space-y-1">
                    <div className="text-xs font-medium uppercase tracking-wide text-zinc-400">
                      来源路径
                    </div>
                    <InlineList items={question.source_paths} limit={4} />
                  </div>
                )}
                <EvidenceDetails
                  details={question.evidence_details}
                  language={language}
                />
                {!question.evidence_details?.length &&
                  asStringArray(question.evidence_refs).length > 0 && (
                    <div className="space-y-1">
                      <div className="text-xs font-medium uppercase tracking-wide text-zinc-400">
                        证据引用
                      </div>
                      <InlineList items={question.evidence_refs} limit={4} />
                    </div>
                  )}
              </div>
            ))}
          </div>
        )}
      </div>
    </Section>
  );
}

function NextStep({ payload }: { payload: GitHubRepoInterviewPrepPayload }) {
  const openQuestions = asStringArray(
    payload.data?.project_context_pack?.open_questions,
  );

  if (!hasText(payload.next_step) && !openQuestions.length) {
    return null;
  }

  return (
    <Section title="下一步" icon={<Info className="text-teal-500" />}>
      <div className="space-y-3">
        <TextBlock>{payload.next_step}</TextBlock>
        {openQuestions.length > 0 && (
          <ul className="space-y-1.5">
            {openQuestions.map((question, index) => (
              <li
                key={`${question}-${index}`}
                className="flex gap-2 text-sm leading-relaxed text-zinc-600 dark:text-zinc-300"
              >
                <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-zinc-300 dark:bg-zinc-600" />
                <span className="min-w-0 break-words">{question}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Section>
  );
}

function hasMeaningfulPayload(
  payload: GitHubRepoInterviewPrepPayload,
): boolean {
  return Boolean(
    payload.data?.repo_metadata ||
      payload.data?.readme ||
      hasText(payload.data?.project_context_pack?.readme_summary?.summary) ||
      payload.data?.project_context_pack?.manifest_summary?.length ||
      payload.data?.project_context_pack?.directory_summary ||
      payload.data?.project_context_pack?.file_summaries?.length ||
      payload.data?.project_context_pack?.architecture_signals?.length ||
      payload.data?.project_context_pack?.evidence_map?.length ||
      payload.data?.project_context_pack?.open_questions?.length ||
      payload.data?.interview_questions?.length ||
      payload.data?.question_generation_summary ||
      payload.steps?.length ||
      payload.errors?.length ||
      payload.warnings?.length ||
      hasText(payload.next_step),
  );
}

function getPayloadStatus(
  payload: GitHubRepoInterviewPrepPayload,
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

function getCompletedSteps(steps: GitHubRepoStep[]): number {
  return steps.filter((step) =>
    ['success', 'partial'].includes(step.status || ''),
  ).length;
}

export const GitHubRepoInterviewPrepToolView: React.FC<ToolViewProps> = ({
  name = 'github-repo-interview-prep',
  assistantContent,
  toolContent,
  assistantTimestamp,
  toolTimestamp,
  isSuccess = true,
  isStreaming = false,
  ...props
}) => {
  const payload = extractGitHubRepoInterviewPrepData(
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

  const steps = payload.steps || [];
  const completedSteps = getCompletedSteps(steps);
  const title = getToolTitle(name);
  const status = getPayloadStatus(payload, isSuccess, isStreaming);

  return (
    <Card className="gap-0 flex border shadow-none border-t border-b-0 border-x-0 p-0 rounded-none flex-col h-full overflow-hidden bg-card">
      <CardHeader className="flex h-16 items-center border-b bg-zinc-50/80 px-4 py-0 !pb-0 backdrop-blur-sm dark:bg-zinc-900/80">
        <div className="relative flex h-full w-full min-w-0 items-center justify-center">
          <div className="absolute left-0 flex items-center">
            <div className="relative flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-sky-500/20 bg-gradient-to-br from-sky-500/20 to-emerald-500/10">
              <Github className="h-6 w-6 text-sky-500 dark:text-sky-400" />
            </div>
          </div>

          <CardTitle className="mx-14 min-w-0 truncate text-center text-base font-medium text-zinc-900 dark:text-zinc-100">
            {title}
          </CardTitle>

          <div className="absolute right-0 flex items-center">
            <StatusBadge status={status} />
          </div>
        </div>
      </CardHeader>

      <CardContent className="relative h-full flex-1 overflow-hidden p-0">
        <ScrollArea className="h-full w-full">
          <StepList steps={steps} />
          <WarningList payload={payload} />
          <ErrorList payload={payload} />
          <RepositoryMetadata payload={payload} />
          <ReadmePreview payload={payload} />
          <ProjectStructure payload={payload} />
          <ManifestFiles payload={payload} />
          <SourceEvidence payload={payload} />
          <InterviewQuestions payload={payload} />
          <NextStep payload={payload} />
        </ScrollArea>
      </CardContent>

      <div className="flex h-10 items-center justify-between gap-4 border-t border-zinc-200 bg-gradient-to-r from-zinc-50/90 to-zinc-100/90 px-4 py-2 backdrop-blur-sm dark:border-zinc-800 dark:from-zinc-900/90 dark:to-zinc-800/90">
        <div className="flex h-full min-w-0 items-center gap-2 text-sm text-zinc-500 dark:text-zinc-400">
          {steps.length > 0 && (
            <Badge
              variant="outline"
              className="h-6 gap-1 bg-zinc-50 py-0.5 dark:bg-zinc-900"
            >
              <CheckCircle className="h-3 w-3" />
              {completedSteps}/{steps.length} 步
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
