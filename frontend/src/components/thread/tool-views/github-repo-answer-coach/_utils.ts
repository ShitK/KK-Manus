export type GitHubRepoAnswerCoachStatus = 'success' | 'partial' | 'error';

export type GitHubRepoAnswerCoachLanguage = 'zh' | 'en';

export type GitHubRepoAnswerCoachNotice = {
  code?: string;
  message?: string;
  retryable?: boolean;
};

export type GitHubRepoAnswerCoachEvidenceMissed = {
  evidence_id?: string;
  source_path?: string;
  reason?: string;
};

export type GitHubRepoAnswerCoachPayload = {
  tool?: string;
  type?: string;
  version?: string;
  status?: GitHubRepoAnswerCoachStatus;
  partial?: boolean;
  input?: {
    question_id?: string;
    language?: GitHubRepoAnswerCoachLanguage;
    coach_style?: string;
    max_follow_ups?: number;
    user_answer_summary?: string;
    user_answer_excerpt?: string;
    user_answer?: string;
  };
  data?: {
    question?: {
      id?: string;
      category?: string;
      difficulty?: string;
      question?: string;
    };
    user_answer_summary?: string;
    user_answer_excerpt?: string;
    answer_feedback?: {
      summary?: string;
      strengths?: string[];
      gaps?: string[];
      evidence_missed?: GitHubRepoAnswerCoachEvidenceMissed[];
      suggested_answer_outline?: string[];
      follow_up_questions?: string[];
      grounding_notes?: string[];
    };
    markdown?: string;
  };
  warnings?: GitHubRepoAnswerCoachNotice[];
  errors?: GitHubRepoAnswerCoachNotice[];
  next_step?: string;
};

type GitHubRepoAnswerCoachData = NonNullable<
  GitHubRepoAnswerCoachPayload['data']
>;
type GitHubRepoAnswerCoachInput = NonNullable<
  GitHubRepoAnswerCoachPayload['input']
>;

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

function collectCandidates(
  value: unknown,
  depth = 0,
  seen = new WeakSet<object>(),
): unknown[] {
  if (depth > 5) {
    return [];
  }

  const parsed = parseJsonCandidate(value);
  const candidates: unknown[] = [parsed];

  if (Array.isArray(parsed)) {
    for (const item of parsed) {
      candidates.push(...collectCandidates(item, depth + 1, seen));
    }
    return candidates;
  }

  if (!isObject(parsed)) {
    return candidates;
  }

  if (seen.has(parsed)) {
    return candidates;
  }
  seen.add(parsed);

  for (const key of ['result', 'output', 'content', 'data']) {
    if (key in parsed) {
      candidates.push(...collectCandidates(parsed[key], depth + 1, seen));
    }
  }

  if (isObject(parsed.tool_execution)) {
    candidates.push(...collectCandidates(parsed.tool_execution.result, depth + 1, seen));
  }

  return candidates;
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

function normalizeLanguage(
  value: unknown,
): GitHubRepoAnswerCoachLanguage | undefined {
  return value === 'zh' || value === 'en' ? value : undefined;
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

function normalizeNotice(value: unknown): GitHubRepoAnswerCoachNotice | null {
  if (!isObject(value)) {
    return null;
  }

  const notice: GitHubRepoAnswerCoachNotice = {};
  const code = normalizeString(value.code);
  const message = normalizeString(value.message);
  const retryable = normalizeBoolean(value.retryable);

  if (code) notice.code = code;
  if (message) notice.message = message;
  if (typeof retryable === 'boolean') notice.retryable = retryable;

  return code || message || typeof retryable === 'boolean' ? notice : null;
}

function normalizeEvidenceMissed(
  value: unknown,
): GitHubRepoAnswerCoachEvidenceMissed | null {
  if (!isObject(value)) {
    return null;
  }

  const missed = {
    evidence_id: normalizeString(value.evidence_id),
    source_path: normalizeString(value.source_path),
    reason: normalizeString(value.reason),
  };

  return Object.values(missed).some((item) => item !== undefined)
    ? missed
    : null;
}

function normalizeInput(value: unknown): GitHubRepoAnswerCoachInput | undefined {
  if (!isObject(value)) {
    return undefined;
  }

  const input = {
    question_id: normalizeString(value.question_id),
    language: normalizeLanguage(value.language),
    coach_style: normalizeString(value.coach_style),
    max_follow_ups: normalizeNumber(value.max_follow_ups),
    user_answer_summary: normalizeString(value.user_answer_summary),
    user_answer_excerpt: normalizeString(value.user_answer_excerpt),
    user_answer: normalizeString(value.user_answer),
  };

  return Object.values(input).some((item) => item !== undefined)
    ? input
    : undefined;
}

function normalizeQuestion(
  value: unknown,
): NonNullable<GitHubRepoAnswerCoachData['question']> | undefined {
  if (!isObject(value)) {
    return undefined;
  }

  const question = {
    id: normalizeString(value.id),
    category: normalizeString(value.category),
    difficulty: normalizeString(value.difficulty),
    question: normalizeString(value.question),
  };

  return Object.values(question).some((item) => item !== undefined)
    ? question
    : undefined;
}

function normalizeAnswerFeedback(
  value: unknown,
): NonNullable<GitHubRepoAnswerCoachData['answer_feedback']> | undefined {
  if (!isObject(value)) {
    return undefined;
  }

  const feedback = {
    summary: normalizeString(value.summary),
    strengths: normalizeStringArray(value.strengths),
    gaps: normalizeStringArray(value.gaps),
    evidence_missed: normalizeObjectArray(
      value.evidence_missed,
      normalizeEvidenceMissed,
    ),
    suggested_answer_outline: normalizeStringArray(
      value.suggested_answer_outline,
    ),
    follow_up_questions: normalizeStringArray(value.follow_up_questions),
    grounding_notes: normalizeStringArray(value.grounding_notes),
  };

  return Object.values(feedback).some((item) => item !== undefined)
    ? feedback
    : undefined;
}

function normalizeData(value: unknown): GitHubRepoAnswerCoachData | undefined {
  if (!isObject(value)) {
    return undefined;
  }

  const data = {
    question: normalizeQuestion(value.question),
    user_answer_summary: normalizeString(value.user_answer_summary),
    user_answer_excerpt: normalizeString(value.user_answer_excerpt),
    answer_feedback: normalizeAnswerFeedback(value.answer_feedback),
    markdown: normalizeString(value.markdown),
  };

  return Object.values(data).some((item) => item !== undefined)
    ? data
    : undefined;
}

function hasMeaningfulNormalizedPayload(
  payload: GitHubRepoAnswerCoachPayload,
): boolean {
  const feedback = payload.data?.answer_feedback;

  return Boolean(
    payload.data?.question ||
      hasText(payload.input?.question_id) ||
      hasText(payload.input?.user_answer_summary) ||
      hasText(payload.input?.user_answer_excerpt) ||
      hasText(payload.input?.user_answer) ||
      hasText(payload.data?.user_answer_summary) ||
      hasText(payload.data?.user_answer_excerpt) ||
      hasText(feedback?.summary) ||
      feedback?.strengths?.length ||
      feedback?.gaps?.length ||
      feedback?.evidence_missed?.length ||
      feedback?.suggested_answer_outline?.length ||
      feedback?.follow_up_questions?.length ||
      feedback?.grounding_notes?.length ||
      payload.errors?.length ||
      payload.warnings?.length ||
      hasText(payload.next_step),
  );
}

function normalizePayload(
  value: Record<string, unknown>,
): GitHubRepoAnswerCoachPayload | null {
  const payload: GitHubRepoAnswerCoachPayload = {
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

  const warnings = normalizeObjectArray(value.warnings, normalizeNotice);
  if (warnings) {
    payload.warnings = warnings;
  }

  const errors = normalizeObjectArray(value.errors, normalizeNotice);
  if (errors) {
    payload.errors = errors;
  }

  return hasMeaningfulNormalizedPayload(payload) ? payload : null;
}

function isAnswerCoachPayload(value: Record<string, unknown>): boolean {
  return (
    value.tool === 'github_repo_answer_coach' ||
    value.tool === 'github-repo-answer-coach' ||
    value.type === 'github_repo_answer_coach' ||
    value.type === 'github-repo-answer-coach'
  );
}

export function extractGitHubRepoAnswerCoachData(
  toolContent?: unknown,
  assistantContent?: unknown,
): GitHubRepoAnswerCoachPayload | null {
  const candidates = [
    ...collectCandidates(toolContent),
    ...collectCandidates(assistantContent),
  ];

  for (const candidate of candidates) {
    const parsed = parseJsonCandidate(candidate);
    if (!isObject(parsed) || !isAnswerCoachPayload(parsed)) {
      continue;
    }

    const payload = normalizePayload(parsed);
    if (payload) {
      return payload;
    }
  }

  return null;
}
