export type GitHubRepoStepStatus =
  | 'pending'
  | 'running'
  | 'success'
  | 'partial'
  | 'error';

export type GitHubRepoStep = {
  id?: string;
  label?: string;
  status?: GitHubRepoStepStatus;
  detail?: string;
};

export type GitHubRepoErrorInfo = {
  code?: string;
  message?: string;
  retryable?: boolean;
};

export type GitHubRepoWarningInfo = GitHubRepoErrorInfo;

export type GitHubRepoInterviewQuestion = {
  id?: string;
  category?: string;
  difficulty?: string;
  question?: string;
  answer_direction?: string;
  evidence_refs?: string[];
  source_paths?: string[];
  evidence_details?: GitHubRepoEvidenceDetail[];
  confidence?: GitHubRepoConfidence;
};

export type GitHubRepoConfidence = 'low' | 'medium' | 'high';

export type GitHubRepoEvidenceDetail = {
  evidence_id?: string;
  source_path?: string;
  evidence_type?: 'readme' | 'manifest' | 'source' | 'directory';
  snippet?: string;
  summary?: string;
  why_it_matters?: string;
  confidence?: GitHubRepoConfidence;
};

export type GitHubRepoQuestionGenerationSummary = {
  requested_count?: number;
  generated_count?: number;
  available_template_count?: number;
  strategy?: string;
  difficulty?: string;
  has_source_evidence?: boolean;
  has_evidence_details?: boolean;
};

export type GitHubRepoInterviewPrepPayload = {
  tool?: string;
  type?: string;
  version?: string;
  status?: 'success' | 'partial' | 'error';
  partial?: boolean;
  steps?: GitHubRepoStep[];
  input?: Record<string, unknown>;
  data?: {
    repo_metadata?: {
      owner?: string;
      repo?: string;
      full_name?: string;
      default_branch?: string;
      description?: string;
      primary_language?: string;
      stars?: number;
      html_url?: string;
    };
    readme?: {
      path?: string;
      size?: number;
      encoding?: string;
      text_excerpt?: string;
      truncated?: boolean;
    } | null;
    project_context_pack?: {
      readme_summary?: {
        summary?: string;
        confidence?: string;
        max_chars?: number;
      };
      manifest_summary?: Array<{
        path?: string;
        ecosystem?: string;
        dependencies?: string[];
        scripts_or_entrypoints?: string[];
        summary?: string;
      }>;
      directory_summary?: {
        top_level_dirs?: string[];
        notable_paths?: string[];
        total_entries?: number;
        truncated?: boolean;
        summary?: string;
      };
      file_summaries?: Array<{
        path?: string;
        role?: string;
        important_symbols?: string[];
        summary?: string;
        evidence_snippets?: Array<{
          id?: string;
          text?: string;
        }>;
        interview_relevance?: string[];
        confidence?: string;
      }>;
      architecture_signals?: Array<{
        claim?: string;
        evidence_refs?: string[];
        confidence?: string;
      }>;
      evidence_map?: Array<{
        id?: string;
        claim?: string;
        source_type?: string;
        source_path?: string;
        snippet?: string;
        confidence?: string;
      }>;
      open_questions?: string[];
    };
    interview_questions?: GitHubRepoInterviewQuestion[];
    question_generation_summary?: GitHubRepoQuestionGenerationSummary;
  };
  errors?: GitHubRepoErrorInfo[];
  warnings?: GitHubRepoWarningInfo[];
  next_step?: string;
};

type GitHubRepoInterviewPrepData = NonNullable<
  GitHubRepoInterviewPrepPayload['data']
>;
type GitHubRepoRepoMetadata = NonNullable<
  GitHubRepoInterviewPrepData['repo_metadata']
>;
type GitHubRepoReadme = GitHubRepoInterviewPrepData['readme'];
type GitHubRepoProjectContextPack =
  GitHubRepoInterviewPrepData['project_context_pack'];

const VALID_STEP_STATUSES = new Set<GitHubRepoStepStatus>([
  'pending',
  'running',
  'success',
  'partial',
  'error',
]);

function isObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function hasText(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0;
}

function parseJsonCandidate(value: unknown): unknown {
  if (typeof value !== 'string') {
    return value;
  }

  const trimmed = value.trim();
  if (!trimmed || (!trimmed.startsWith('{') && !trimmed.startsWith('['))) {
    return value;
  }

  try {
    return JSON.parse(trimmed);
  } catch {
    return value;
  }
}

function collectCandidates(value: unknown): unknown[] {
  const parsed = parseJsonCandidate(value);
  const candidates: unknown[] = [parsed];

  if (isObject(parsed)) {
    candidates.push(parsed.result, parsed.output, parsed.content);

    if (isObject(parsed.result)) {
      candidates.push(parsed.result.output, parsed.result.content);
    }

    if (isObject(parsed.tool_execution)) {
      candidates.push(parsed.tool_execution.result);

      if (isObject(parsed.tool_execution.result)) {
        candidates.push(parsed.tool_execution.result.output);
      }
    }
  }

  return candidates.flatMap((candidate) => {
    const nested = parseJsonCandidate(candidate);
    return nested === candidate ? [candidate] : [nested, candidate];
  });
}

function normalizeString(value: unknown): string | undefined {
  return hasText(value) ? value : undefined;
}

function normalizeNumber(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value)
    ? value
    : undefined;
}

function normalizeBoolean(value: unknown): boolean | undefined {
  return typeof value === 'boolean' ? value : undefined;
}

function normalizeStepStatus(value: unknown): GitHubRepoStepStatus | undefined {
  return typeof value === 'string' &&
    VALID_STEP_STATUSES.has(value as GitHubRepoStepStatus)
    ? (value as GitHubRepoStepStatus)
    : undefined;
}

function normalizeStep(value: unknown): GitHubRepoStep | null {
  if (!isObject(value)) {
    return null;
  }

  const step: GitHubRepoStep = {};
  const id = normalizeString(value.id);
  const label = normalizeString(value.label);
  const status = normalizeStepStatus(value.status);
  const detail = normalizeString(value.detail);

  if (id) step.id = id;
  if (label) step.label = label;
  if (status) step.status = status;
  if (detail) step.detail = detail;

  return id || label || status || detail ? step : null;
}

function normalizeError(value: unknown): GitHubRepoErrorInfo | null {
  if (!isObject(value)) {
    return null;
  }

  const error: GitHubRepoErrorInfo = {};
  const code = normalizeString(value.code);
  const message = normalizeString(value.message);
  const retryable = normalizeBoolean(value.retryable);

  if (code) error.code = code;
  if (message) error.message = message;
  if (typeof retryable === 'boolean') error.retryable = retryable;

  return code || message || typeof retryable === 'boolean' ? error : null;
}

function normalizeStringArray(value: unknown): string[] | undefined {
  if (!Array.isArray(value)) {
    return undefined;
  }

  const items = value.filter((item): item is string => hasText(item));
  return items.length ? items : undefined;
}

function normalizeObjectArray<T>(
  value: unknown,
  normalizeItem: (value: unknown) => T | null,
): T[] | undefined {
  if (!Array.isArray(value)) {
    return undefined;
  }

  const items = value
    .map(normalizeItem)
    .filter((item): item is T => Boolean(item));
  return items.length ? items : undefined;
}

function normalizeManifestSummary(value: unknown) {
  if (!isObject(value)) {
    return null;
  }

  const item = {
    path: normalizeString(value.path),
    ecosystem: normalizeString(value.ecosystem),
    dependencies: normalizeStringArray(value.dependencies),
    scripts_or_entrypoints: normalizeStringArray(value.scripts_or_entrypoints),
    summary: normalizeString(value.summary),
  };

  return Object.values(item).some((entry) => entry !== undefined) ? item : null;
}

function normalizeDirectorySummary(value: unknown) {
  if (!isObject(value)) {
    return undefined;
  }

  const item = {
    top_level_dirs: normalizeStringArray(value.top_level_dirs),
    notable_paths: normalizeStringArray(value.notable_paths),
    total_entries: normalizeNumber(value.total_entries),
    truncated: normalizeBoolean(value.truncated),
    summary: normalizeString(value.summary),
  };

  return Object.values(item).some((entry) => entry !== undefined)
    ? item
    : undefined;
}

function normalizeFileSummary(value: unknown) {
  if (!isObject(value)) {
    return null;
  }

  const evidenceSnippets = normalizeObjectArray(
    value.evidence_snippets,
    (snippet) => {
      if (!isObject(snippet)) return null;
      const item = {
        id: normalizeString(snippet.id),
        text: normalizeString(snippet.text),
      };
      return item.id || item.text ? item : null;
    },
  );

  const item = {
    path: normalizeString(value.path),
    role: normalizeString(value.role),
    important_symbols: normalizeStringArray(value.important_symbols),
    summary: normalizeString(value.summary),
    evidence_snippets: evidenceSnippets,
    interview_relevance: normalizeStringArray(value.interview_relevance),
    confidence: normalizeString(value.confidence),
  };

  return Object.values(item).some((entry) => entry !== undefined) ? item : null;
}

function normalizeArchitectureSignal(value: unknown) {
  if (!isObject(value)) {
    return null;
  }

  const item = {
    claim: normalizeString(value.claim),
    evidence_refs: normalizeStringArray(value.evidence_refs),
    confidence: normalizeString(value.confidence),
  };

  return Object.values(item).some((entry) => entry !== undefined) ? item : null;
}

function normalizeEvidenceMapItem(value: unknown) {
  if (!isObject(value)) {
    return null;
  }

  const item = {
    id: normalizeString(value.id),
    claim: normalizeString(value.claim),
    source_type: normalizeString(value.source_type),
    source_path: normalizeString(value.source_path),
    snippet: normalizeString(value.snippet),
    confidence: normalizeString(value.confidence),
  };

  return Object.values(item).some((entry) => entry !== undefined) ? item : null;
}

function normalizeEvidenceType(
  value: unknown,
): GitHubRepoEvidenceDetail['evidence_type'] | undefined {
  return value === 'readme' ||
    value === 'manifest' ||
    value === 'source' ||
    value === 'directory'
    ? value
    : undefined;
}

function normalizeConfidence(
  value: unknown,
): GitHubRepoConfidence | undefined {
  return value === 'low' || value === 'medium' || value === 'high'
    ? value
    : undefined;
}

function normalizeEvidenceDetail(value: unknown): GitHubRepoEvidenceDetail | null {
  if (!isObject(value)) {
    return null;
  }

  const detail = {
    evidence_id: normalizeString(value.evidence_id),
    source_path: normalizeString(value.source_path),
    evidence_type: normalizeEvidenceType(value.evidence_type),
    snippet: normalizeString(value.snippet),
    summary: normalizeString(value.summary),
    why_it_matters: normalizeString(value.why_it_matters),
    confidence: normalizeConfidence(value.confidence),
  };

  const hasCoreFields =
    detail.evidence_id &&
    detail.source_path &&
    detail.evidence_type &&
    detail.why_it_matters;
  const hasReadableEvidence = detail.snippet || detail.summary;

  return hasCoreFields && hasReadableEvidence ? detail : null;
}

function normalizeInterviewQuestion(
  value: unknown,
): GitHubRepoInterviewQuestion | null {
  if (!isObject(value)) {
    return null;
  }

  const evidenceDetails = normalizeObjectArray(
    value.evidence_details,
    normalizeEvidenceDetail,
  );

  const question = {
    id: normalizeString(value.id),
    category: normalizeString(value.category),
    difficulty: normalizeString(value.difficulty),
    question: normalizeString(value.question),
    answer_direction: normalizeString(value.answer_direction),
    evidence_refs: normalizeStringArray(value.evidence_refs),
    source_paths: normalizeStringArray(value.source_paths),
    evidence_details: evidenceDetails,
    confidence: normalizeConfidence(value.confidence),
  };

  return hasText(question.question) ? question : null;
}

function normalizeQuestionGenerationSummary(
  value: unknown,
): GitHubRepoQuestionGenerationSummary | undefined {
  if (!isObject(value)) {
    return undefined;
  }

  const summary = {
    requested_count: normalizeNumber(value.requested_count),
    generated_count: normalizeNumber(value.generated_count),
    available_template_count: normalizeNumber(value.available_template_count),
    strategy: normalizeString(value.strategy),
    difficulty: normalizeString(value.difficulty),
    has_source_evidence: normalizeBoolean(value.has_source_evidence),
    has_evidence_details: normalizeBoolean(value.has_evidence_details),
  };

  return Object.values(summary).some((entry) => entry !== undefined)
    ? summary
    : undefined;
}

function normalizeInput(value: unknown): Record<string, unknown> | undefined {
  return isObject(value) ? value : undefined;
}

function normalizeRepoMetadata(
  value: unknown,
): GitHubRepoRepoMetadata | undefined {
  if (!isObject(value)) {
    return undefined;
  }

  const metadata = {
    owner: normalizeString(value.owner),
    repo: normalizeString(value.repo),
    full_name: normalizeString(value.full_name),
    default_branch: normalizeString(value.default_branch),
    description: normalizeString(value.description),
    primary_language: normalizeString(value.primary_language),
    stars: normalizeNumber(value.stars),
    html_url: normalizeString(value.html_url),
  };

  return Object.values(metadata).some((item) => item !== undefined)
    ? metadata
    : undefined;
}

function normalizeReadme(value: unknown): GitHubRepoReadme | undefined {
  if (value === null) {
    return null;
  }

  if (!isObject(value)) {
    return undefined;
  }

  const readme = {
    path: normalizeString(value.path),
    size: normalizeNumber(value.size),
    encoding: normalizeString(value.encoding),
    text_excerpt: normalizeString(value.text_excerpt),
    truncated: normalizeBoolean(value.truncated),
  };

  return Object.values(readme).some((item) => item !== undefined)
    ? readme
    : undefined;
}

function normalizeProjectContextPack(
  value: unknown,
): GitHubRepoProjectContextPack {
  if (!isObject(value)) {
    return undefined;
  }

  const readmeSummarySource = value.readme_summary;
  const readmeSummary = isObject(readmeSummarySource)
    ? {
        summary: normalizeString(readmeSummarySource.summary),
        confidence: normalizeString(readmeSummarySource.confidence),
        max_chars: normalizeNumber(readmeSummarySource.max_chars),
      }
    : undefined;
  const normalizedReadmeSummary =
    readmeSummary &&
    Object.values(readmeSummary).some((item) => item !== undefined)
      ? readmeSummary
      : undefined;
  const manifestSummary = normalizeObjectArray(
    value.manifest_summary,
    normalizeManifestSummary,
  );
  const directorySummary = normalizeDirectorySummary(value.directory_summary);
  const fileSummaries = normalizeObjectArray(
    value.file_summaries,
    normalizeFileSummary,
  );
  const architectureSignals = normalizeObjectArray(
    value.architecture_signals,
    normalizeArchitectureSignal,
  );
  const evidenceMap = normalizeObjectArray(
    value.evidence_map,
    normalizeEvidenceMapItem,
  );
  const openQuestions = normalizeStringArray(value.open_questions);

  return normalizedReadmeSummary ||
    manifestSummary ||
    directorySummary ||
    fileSummaries ||
    architectureSignals ||
    evidenceMap ||
    openQuestions
    ? {
        readme_summary: normalizedReadmeSummary,
        manifest_summary: manifestSummary,
        directory_summary: directorySummary,
        file_summaries: fileSummaries,
        architecture_signals: architectureSignals,
        evidence_map: evidenceMap,
        open_questions: openQuestions,
      }
    : undefined;
}

function normalizeData(value: unknown): GitHubRepoInterviewPrepPayload['data'] {
  if (!isObject(value)) {
    return undefined;
  }

  const repoMetadata = normalizeRepoMetadata(value.repo_metadata);
  const readme = normalizeReadme(value.readme);
  const projectContextPack = normalizeProjectContextPack(
    value.project_context_pack,
  );
  const interviewQuestions = normalizeObjectArray(
    value.interview_questions,
    normalizeInterviewQuestion,
  );
  const questionGenerationSummary = normalizeQuestionGenerationSummary(
    value.question_generation_summary,
  );

  return repoMetadata ||
    readme ||
    projectContextPack ||
    interviewQuestions ||
    questionGenerationSummary
    ? {
        repo_metadata: repoMetadata,
        readme,
        project_context_pack: projectContextPack,
        interview_questions: interviewQuestions,
        question_generation_summary: questionGenerationSummary,
      }
    : undefined;
}

function hasMeaningfulNormalizedPayload(
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

function normalizePayload(
  value: Record<string, unknown>,
): GitHubRepoInterviewPrepPayload | null {
  const payload: GitHubRepoInterviewPrepPayload = {
    tool: normalizeString(value.tool),
    type: normalizeString(value.type),
    version: normalizeString(value.version),
    partial: normalizeBoolean(value.partial),
    input: normalizeInput(value.input),
    data: normalizeData(value.data),
    next_step: normalizeString(value.next_step),
  };

  if (
    value.status === 'success' ||
    value.status === 'partial' ||
    value.status === 'error'
  ) {
    payload.status = value.status;
  }

  if (Array.isArray(value.steps)) {
    const steps = value.steps
      .map(normalizeStep)
      .filter((step): step is GitHubRepoStep => Boolean(step));
    if (steps.length) {
      payload.steps = steps;
    }
  }

  if (Array.isArray(value.errors)) {
    const errors = value.errors
      .map(normalizeError)
      .filter((error): error is GitHubRepoErrorInfo => Boolean(error));
    if (errors.length) {
      payload.errors = errors;
    }
  }

  if (Array.isArray(value.warnings)) {
    const warnings = value.warnings
      .map(normalizeError)
      .filter((warning): warning is GitHubRepoWarningInfo => Boolean(warning));
    if (warnings.length) {
      payload.warnings = warnings;
    }
  }

  return hasMeaningfulNormalizedPayload(payload) ? payload : null;
}

export function extractGitHubRepoInterviewPrepData(
  toolContent?: unknown,
  assistantContent?: unknown,
): GitHubRepoInterviewPrepPayload | null {
  const candidates = [
    ...collectCandidates(toolContent),
    ...collectCandidates(assistantContent),
  ];

  for (const candidate of candidates) {
    const parsed = parseJsonCandidate(candidate);
    if (!isObject(parsed)) {
      continue;
    }

    if (
      parsed.tool === 'github_repo_interview_prep' ||
      parsed.type === 'github_repo_interview_prep'
    ) {
      const payload = normalizePayload(parsed);
      if (payload) {
        return payload;
      }
    }
  }

  return null;
}
