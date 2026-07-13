export type GitHubRepoInterviewWorkflowStatus = 'success' | 'partial' | 'error';
export type GitHubRepoInterviewWorkflowStepStatus =
  | 'pending'
  | 'ready'
  | 'running'
  | 'success'
  | 'partial'
  | 'error';

export type GitHubRepoInterviewMultiAgentTraceStatus =
  | 'pending'
  | 'success'
  | 'partial'
  | 'error'
  | 'skipped';

export type GitHubRepoInterviewWorkflowNotice = {
  code?: string;
  message?: string;
  retryable?: boolean;
};

export type GitHubRepoInterviewWorkflowStep = {
  id?: string;
  label?: string;
  status?: GitHubRepoInterviewWorkflowStepStatus;
  detail?: string;
};

export type GitHubRepoInterviewWorkflowEvidenceDetail = {
  evidence_id?: string;
  source_path?: string;
  evidence_type?: string;
  summary?: string;
  snippet?: string;
  why_it_matters?: string;
  confidence?: string;
};

export type GitHubRepoInterviewWorkflowRole = {
  id?: string;
  kind?: 'deterministic' | 'llm' | string;
  stage?: string;
  evidence_scope?: string;
  repository_access?: string;
};

export type GitHubRepoInterviewWorkflowContextPolicy = {
  mode?: string;
  active_role?: string;
  role_kind?: string;
  source?: string;
  visible_sources?: string[];
  hidden_sources?: string[];
  allowed_evidence_ids?: string[];
  allowed_source_paths?: string[];
  max_evidence_details?: number;
  repository_access?: string;
  tool_access?: string;
  persists_user_answer?: boolean;
};

export type GitHubRepoInterviewWorkflowAnswerState = {
  has_answer_feedback?: boolean;
  has_follow_up_feedback?: boolean;
  follow_up_mode?: string;
  follow_up_count?: number;
};

export type GitHubRepoInterviewWorkflowCompletion = {
  answer_coached?: boolean;
  follow_up_completed?: boolean;
  summary_scope?: string;
};

export type GitHubRepoInterviewConversationPracticeOverview = {
  repository?: string;
  role?: string;
  difficulty?: string;
  completed_items?: string[];
  unfinished_items?: string[];
};

export type GitHubRepoInterviewConversationHighlight = {
  title?: string;
  detail?: string;
};

export type GitHubRepoInterviewConversationImprovement = {
  weakness?: string;
  evidence?: string;
  suggestion?: string;
};

export type GitHubRepoInterviewConversationAbility = {
  dimension?: string;
  score?: number;
  rationale?: string;
};

export type GitHubRepoInterviewWorkflowRedactionPolicy = {
  includes_user_answer?: boolean;
  includes_follow_up_answer?: boolean;
  includes_hidden_source_content?: boolean;
  includes_repo_evidence_text?: boolean;
};

export type GitHubRepoInterviewWorkflowContextSnapshot = {
  version?: string;
  scope?: string;
  persistence?: string;
  current_stage?: string;
  active_role?: string;
  role_kind?: string;
  visible_sources?: string[];
  hidden_sources?: string[];
  allowed_evidence_ids?: string[];
  allowed_source_paths?: string[];
  repository_access?: string;
  tool_access?: string;
  persists_user_answer?: boolean;
  answer_state?: GitHubRepoInterviewWorkflowAnswerState;
  workflow_completion?: GitHubRepoInterviewWorkflowCompletion;
  redaction_policy?: GitHubRepoInterviewWorkflowRedactionPolicy;
  saved_memory_count?: number;
  vector_memory?: {
    enabled?: boolean;
    status?: string;
    matched_count?: number;
    threshold?: number;
    model?: string;
  };
};

export type GitHubRepoInterviewWorkflowMemoryCandidate = {
  id?: string;
  type?: string;
  value?: string;
  label?: string;
  source_stage?: string;
  source_fields?: string[];
  requires_user_confirmation?: boolean;
  status?: string;
  persisted?: boolean;
  privacy?: {
    includes_user_answer?: boolean;
    includes_follow_up_answer?: boolean;
    includes_repo_evidence_text?: boolean;
  };
};

export type GitHubRepoInterviewSessionMemory = {
  target_role?: string;
  target_role_source?: string;
  answered_question_ids?: string[];
  last_question_id?: string;
  current_practice_category?: string;
  missed_evidence_ids?: string[];
  next_practice_suggestion?: string;
  summary_completed?: boolean;
};

export function mergeGitHubInterviewSessionMemory(
  context?: GitHubRepoInterviewSessionMemory,
  patch?: GitHubRepoInterviewSessionMemory,
): GitHubRepoInterviewSessionMemory | undefined {
  if (!context && !patch) return undefined;

  const mergeUnique = (left?: string[], right?: string[]) =>
    Array.from(new Set([...(left || []), ...(right || [])]));
  const merged: GitHubRepoInterviewSessionMemory = {
    ...(context || {}),
    ...(patch || {}),
  };

  const answeredQuestionIds = mergeUnique(
    context?.answered_question_ids,
    patch?.answered_question_ids,
  );
  if (answeredQuestionIds.length) {
    merged.answered_question_ids = answeredQuestionIds;
  }

  const missedEvidenceIds = mergeUnique(
    context?.missed_evidence_ids,
    patch?.missed_evidence_ids,
  );
  if (missedEvidenceIds.length) {
    merged.missed_evidence_ids = missedEvidenceIds;
  }

  return merged;
}

export type GitHubRepoInterviewVectorMemoryCandidate = {
  id?: string;
  type?: 'practice_experience_summary';
  text?: string;
  content_hash?: string;
  target_role?: string;
  category?: string;
  source_thread_id?: string;
  source_agent_run_id?: string;
  source_stage?: 'summarize';
  requires_user_confirmation?: boolean;
  status?: 'candidate_only';
  persisted?: boolean;
  provenance?: { kind?: 'user_confirmed' | 'demo_fixture' };
  privacy?: {
    includes_user_answer?: boolean;
    includes_follow_up_answer?: boolean;
    includes_repo_evidence_text?: boolean;
  };
};

export type GitHubRepoInterviewVectorMemoryContext = {
  id?: string;
  text?: string;
  similarity?: number;
  target_role?: string;
  category?: string;
  source_stage?: string;
  persisted?: boolean;
  provenance?: { kind?: 'user_confirmed' | 'demo_fixture' };
};

export type GitHubRepoInterviewVectorMemoryRetrieval = {
  status?: 'disabled' | 'matched' | 'no_match' | 'embedding_error' | 'retrieval_error';
  query_source?: string;
  model?: string;
  threshold?: number;
  top_k?: number;
  candidate_count?: number;
  matched_count?: number;
  applied_count?: number;
  filtered_by_threshold?: number;
  filtered_by_topk?: number;
  filtered_count?: number;
  fallback_used?: boolean;
};

export type GitHubRepoInterviewWorkflowAnswerQualitySignalId =
  | 'evidence_grounding'
  | 'completeness_missing_evidence'
  | 'hallucination_risk'
  | 'architecture_understanding'
  | 'tradeoff_awareness'
  | 'question_relevance'
  | 'privacy_boundary';

export type GitHubRepoInterviewWorkflowAnswerQualitySignalStatus =
  | 'supported'
  | 'needs_attention'
  | 'guarded'
  | 'not_available';

export type GitHubRepoInterviewWorkflowAnswerQualitySignalSeverity =
  | 'positive'
  | 'neutral'
  | 'warning';

export type GitHubRepoInterviewWorkflowAnswerQualitySignal = {
  id?: GitHubRepoInterviewWorkflowAnswerQualitySignalId;
  label?: string;
  status?: GitHubRepoInterviewWorkflowAnswerQualitySignalStatus;
  severity?: GitHubRepoInterviewWorkflowAnswerQualitySignalSeverity;
  basis_fields?: string[];
  evidence_refs?: string[];
  notes?: string[];
};

const ANSWER_QUALITY_SIGNAL_IDS = new Set<string>([
  'evidence_grounding',
  'completeness_missing_evidence',
  'hallucination_risk',
  'architecture_understanding',
  'tradeoff_awareness',
  'question_relevance',
  'privacy_boundary',
]);

const ANSWER_QUALITY_SIGNAL_STATUSES = new Set<string>([
  'supported',
  'needs_attention',
  'guarded',
  'not_available',
]);

const ANSWER_QUALITY_SIGNAL_SEVERITIES = new Set<string>([
  'positive',
  'neutral',
  'warning',
]);

export type GitHubRepoInterviewWorkflowBoundaryTone =
  | 'neutral'
  | 'success'
  | 'warning';

export type GitHubRepoInterviewWorkflowBoundaryFact = {
  id: string;
  label: string;
  value: string;
  tone: GitHubRepoInterviewWorkflowBoundaryTone;
};

export type GitHubRepoInterviewNormalizedIntent = Record<
  string,
  {
    raw?: string;
    normalized?: string;
  }
>;

export type GitHubRepoInterviewQualitySignals = {
  coverage?: 'not_started' | 'partial' | 'grounded';
  evidence_grounding?: 'missing' | 'partial' | 'grounded';
  boundary_health?: 'clean' | 'warning' | 'error';
  recommended_next_step?:
    | 'answer_question'
    | 'answer_follow_up'
    | 'revise_with_evidence'
    | 'summarize'
    | 'select_another_question'
    | 'retry_same_stage';
};

export type GitHubRepoInterviewAgentNode = {
  id?: 'repository_analyst' | 'interview_question' | 'answer_coach' | 'quality_reviewer';
  role_name?: string;
  status?: GitHubRepoInterviewMultiAgentTraceStatus;
  stage?: string;
  input_sources?: string[];
  visible_context?: string[];
  forbidden_scope?: string[];
  uses_repo_evidence?: boolean;
  reads_user_answer?: boolean;
  persists_memory?: boolean;
  output_summary?: string;
};

export type GitHubRepoInterviewMultiAgentTrace = {
  version?: string;
  mode?: 'controlled_local_trace';
  scope?: 'request';
  orchestrator?: {
    name?: 'MainAgent';
    status?: GitHubRepoInterviewMultiAgentTraceStatus;
    output_summary?: string;
  };
  agents?: GitHubRepoInterviewAgentNode[];
  quality_signals?: GitHubRepoInterviewQualitySignals;
};

export type GitHubRepoInterviewMultiAgentTraceFlowNode = {
  id: string;
  label: string;
  status?: GitHubRepoInterviewMultiAgentTraceStatus;
  kind: 'orchestrator' | 'agent';
};

export type GitHubRepoInterviewMultiAgentTraceSummary = {
  agentCount: number;
  completedAgentCount: number;
  statusLabel: string;
  modeLabel?: string;
  scopeLabel?: string;
  usesRepoEvidence: boolean;
  readsUserAnswer: boolean;
  persistsMemory: boolean;
};

export type GitHubRepoInterviewPrimaryPanelSectionId =
  | 'workflow_steps'
  | 'multi_agent_trace'
  | 'answer_quality_signals'
  | 'boundary_details'
  | 'selected_question'
  | 'answer_feedback'
  | 'follow_up'
  | 'other_questions'
  | 'session_summary'
  | 'session_memory'
  | 'memory_candidates'
  | 'vector_memory_candidate'
  | 'vector_memory_retrieval'
  | 'notices'
  | 'next_step';

export type GitHubRepoInterviewWorkflowRoleGroup = {
  id: 'deterministic' | 'llm' | 'other';
  label: string;
  roles: GitHubRepoInterviewWorkflowRole[];
};

export type GitHubRepoInterviewWorkflowPayload = {
  tool?: string;
  type?: string;
  version?: string;
  status?: GitHubRepoInterviewWorkflowStatus;
  partial?: boolean;
  input?: {
    stage?: string;
    question_id?: string;
    language?: 'zh' | 'en';
    coach_style?: string;
    preferred_question_category?: string;
    max_follow_ups?: number;
    user_answer_excerpt?: string;
  };
  data?: {
    workflow?: {
      current_stage?: string;
      steps?: GitHubRepoInterviewWorkflowStep[];
      active_role?: string;
      roles?: GitHubRepoInterviewWorkflowRole[];
      follow_up_count?: number;
    };
    selected_question?: {
      id?: string;
      category?: string;
      difficulty?: string;
      question?: string;
      answer_direction?: string;
      source_paths?: string[];
      evidence_refs?: string[];
      confidence?: string;
    };
    evidence_policy?: {
      source?: string;
      allowed_evidence_ids?: string[];
      max_evidence_details?: number;
      repository_access?: string;
    };
    context_policy?: GitHubRepoInterviewWorkflowContextPolicy;
    context_snapshot?: GitHubRepoInterviewWorkflowContextSnapshot;
    multi_agent_trace?: GitHubRepoInterviewMultiAgentTrace;
    summary_kind?: string;
    conversation_turn_count?: number;
    conversation_summary?: {
      overview?: string;
      raw_report?: string;
      discussed_questions?: string[];
      agent_help?: string[];
      open_items?: string[];
      practice_overview?: GitHubRepoInterviewConversationPracticeOverview;
      performance_highlights?: GitHubRepoInterviewConversationHighlight[];
      improvement_areas?: GitHubRepoInterviewConversationImprovement[];
      ability_profile?: GitHubRepoInterviewConversationAbility[];
      next_practice_steps?: string[];
    };
    memory_candidates?: GitHubRepoInterviewWorkflowMemoryCandidate[];
    saved_memory_context?: GitHubRepoInterviewWorkflowMemoryCandidate[];
    session_memory_context?: GitHubRepoInterviewSessionMemory;
    session_memory_patch?: GitHubRepoInterviewSessionMemory;
    vector_memory_candidate?: GitHubRepoInterviewVectorMemoryCandidate;
    vector_memory_context?: GitHubRepoInterviewVectorMemoryContext[];
    vector_memory_retrieval?: GitHubRepoInterviewVectorMemoryRetrieval;
    answer_quality_signals?: GitHubRepoInterviewWorkflowAnswerQualitySignal[];
    evidence_details?: GitHubRepoInterviewWorkflowEvidenceDetail[];
    normalized_intent?: GitHubRepoInterviewNormalizedIntent;
    answer_feedback?: {
      summary?: string;
      strengths?: string[];
      gaps?: string[];
      evidence_missed?: Array<{
        evidence_id?: string;
        source_path?: string;
        reason?: string;
      }>;
      suggested_answer_outline?: string[];
      follow_up_questions?: string[];
      grounding_notes?: string[];
    };
    follow_up?: {
      mode?: string;
      questions?: string[];
      feedback?: string[];
      grounding_notes?: string[];
    };
    other_questions?: Array<{
      id?: string;
      category?: string;
      difficulty?: string;
      question?: string;
    }>;
    session_summary?: {
      covered_evidence?: string[];
      missed_evidence?: string[];
      practice_notes?: string[];
      next_practice_suggestion?: string;
      workflow_completion?: GitHubRepoInterviewWorkflowCompletion;
    };
  };
  warnings?: GitHubRepoInterviewWorkflowNotice[];
  errors?: GitHubRepoInterviewWorkflowNotice[];
  next_step?: string;
};

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
  if (!isObject(parsed) || seen.has(parsed)) {
    return candidates;
  }
  seen.add(parsed);
  for (const key of ['result', 'output', 'content']) {
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
  return hasText(value) ? value.trim() : undefined;
}

function normalizeNumber(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

function normalizeBoolean(value: unknown): boolean | undefined {
  return typeof value === 'boolean' ? value : undefined;
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

function normalizeNotice(value: unknown): GitHubRepoInterviewWorkflowNotice | null {
  if (!isObject(value)) {
    return null;
  }
  const notice = {
    code: normalizeString(value.code),
    message: normalizeString(value.message),
    retryable: normalizeBoolean(value.retryable),
  };
  return Object.values(notice).some((item) => item !== undefined) ? notice : null;
}

function normalizeStep(value: unknown): GitHubRepoInterviewWorkflowStep | null {
  if (!isObject(value)) {
    return null;
  }
  const status: GitHubRepoInterviewWorkflowStepStatus | undefined =
    value.status === 'pending' ||
    value.status === 'ready' ||
    value.status === 'running' ||
    value.status === 'success' ||
    value.status === 'partial' ||
    value.status === 'error'
      ? value.status
      : undefined;
  const step = {
    id: normalizeString(value.id),
    label: normalizeString(value.label),
    status,
    detail: normalizeString(value.detail),
  };
  return Object.values(step).some((item) => item !== undefined) ? step : null;
}

function normalizeEvidenceDetail(
  value: unknown,
): GitHubRepoInterviewWorkflowEvidenceDetail | null {
  if (!isObject(value)) {
    return null;
  }
  const detail = {
    evidence_id: normalizeString(value.evidence_id),
    source_path: normalizeString(value.source_path),
    evidence_type: normalizeString(value.evidence_type),
    summary: normalizeString(value.summary),
    snippet: normalizeString(value.snippet),
    why_it_matters: normalizeString(value.why_it_matters),
    confidence: normalizeString(value.confidence),
  };
  const hasCore =
    detail.evidence_id &&
    detail.source_path &&
    detail.evidence_type &&
    detail.why_it_matters;
  return hasCore && (detail.summary || detail.snippet) ? detail : null;
}

function normalizeRole(value: unknown): GitHubRepoInterviewWorkflowRole | null {
  if (!isObject(value)) {
    return null;
  }
  const role = {
    id: normalizeString(value.id),
    kind: normalizeString(value.kind),
    stage: normalizeString(value.stage),
    evidence_scope: normalizeString(value.evidence_scope),
    repository_access: normalizeString(value.repository_access),
  };
  return Object.values(role).some((item) => item !== undefined) ? role : null;
}

function normalizeContextPolicy(
  value: unknown,
): GitHubRepoInterviewWorkflowContextPolicy | undefined {
  if (!isObject(value)) {
    return undefined;
  }
  const policy = {
    mode: normalizeString(value.mode),
    active_role: normalizeString(value.active_role),
    role_kind: normalizeString(value.role_kind),
    source: normalizeString(value.source),
    visible_sources: normalizeStringArray(value.visible_sources),
    hidden_sources: normalizeStringArray(value.hidden_sources),
    allowed_evidence_ids: normalizeStringArray(value.allowed_evidence_ids),
    allowed_source_paths: normalizeStringArray(value.allowed_source_paths),
    max_evidence_details: normalizeNumber(value.max_evidence_details),
    repository_access: normalizeString(value.repository_access),
    tool_access: normalizeString(value.tool_access),
    persists_user_answer: normalizeBoolean(value.persists_user_answer),
  };
  return Object.values(policy).some((item) => item !== undefined) ? policy : undefined;
}

function boundaryValue(value: unknown): string | undefined {
  if (typeof value === 'boolean') {
    return String(value);
  }
  if (typeof value === 'number' && Number.isFinite(value)) {
    return String(value);
  }
  return normalizeString(value);
}

// Display-only labels. Payload redaction is handled by the allowlist-based
// normalize functions below, not by this map.
const WORKFLOW_TERM_LABELS: Record<string, string> = {
  deterministic: '确定性角色',
  llm: 'LLM 角色',
  other: '其他角色',
  controlled_local_trace: '受控本地链路',
  repository_analyst: '仓库分析员',
  interview_question: '题目设计师',
  answer_coach: '回答教练',
  quality_reviewer: '质量审阅员',
  MainAgent: '主控调度员',
  RepositoryAnalystAgent: '仓库分析员',
  InterviewQuestionAgent: '题目设计师',
  AnswerCoachAgent: '回答教练',
  QualityReviewerAgent: '质量审阅员',
  no_new_repository_access: '无新仓库访问',
  none: '无工具访问',
  true: '是',
  false: '否',
  pending: '等待中',
  ready: '已就绪',
  running: '运行中',
  success: '已完成',
  partial: '部分完成',
  error: '错误',
  question_prompt: '追问待回答',
  answer_feedback: '追问反馈',
  answer_feedback_fallback: '兜底反馈',
  summary_after_follow_up_feedback: '完整练习总结',
  summary_without_follow_up_feedback: '未完成追问的总结',
  request_level_context_policy: '请求级上下文策略',
  selected_question: '当前面试题',
  'selected_question.evidence_details': '当前题目的证据详情',
  context_snapshot: '上下文快照',
  follow_up: '追问内容',
  session_summary: '练习总结',
  warnings: '警告',
  errors: '错误',
  question_generation_summary: '题目生成摘要',
  'prep_questions_pack.question_generation_summary': '题目生成摘要',
  'repository_analyst.output_summary': '仓库分析摘要',
  unsupported_questions_without_evidence: '缺少证据的问题',
  user_answer: '用户回答',
  raw_user_answer: '用户回答原文',
  repo_metadata: '仓库元数据',
  readme: 'README',
  project_context_pack: '项目上下文包',
  markdown: 'Markdown',
  thread_history: '线程历史',
  local_files: '本地文件',
  workflow_state: '工作流状态',
  interview_questions: '面试题列表',
  evidence_details: '证据详情',
  request: '请求级',
  not_persisted: '未持久化',
  candidate_only: '候选未保存',
  active: '已保存',
  deleted: '已删除',
  saved_memories: '已确认记忆',
  preferred_question_category: '题目方向',
  coach_style: '反馈风格',
  language: '展示语言',
  language_preference_hint: '语言偏好候选',
  feedback_preference_hint: '反馈风格候选',
  recent_practice_category: '最近练习分类候选',
  practice_weakness_tag: '练习弱项候选',
  missing_evidence: '缺少 evidence 支撑',
  weak_architecture_tradeoff: '架构取舍表达不足',
  unclear_testing_story: '测试验证表达不清',
  supported: '已支撑',
  needs_attention: '需关注',
  guarded: '已拦截',
  not_available: '暂无信号',
  positive: '正向',
  neutral: '中性',
  warning: '警告',
  evidence_grounding: '证据支撑',
  completeness_missing_evidence: '完整性 / 遗漏证据',
  hallucination_risk: '幻觉引用风险',
  architecture_understanding: '架构理解',
  tradeoff_awareness: '取舍意识',
  question_relevance: '问题相关性',
  privacy_boundary: '隐私边界',
  thread_dialogue: '本轮对话',
  select_question: '选择题目',
  coach_answer: '回答辅导',
  coach_follow_up: '追问辅导',
  summarize: '总结',
  prep: '准备阶段',
  not_started: '尚未开始',
  grounded: '证据充分',
  missing: '缺少证据',
  clean: '边界正常',
  answer_question: '回答当前题目',
  answer_follow_up: '回答追问',
  revise_with_evidence: '结合证据修订回答',
  select_another_question: '选择另一题',
  retry_same_stage: '重试当前阶段',
  current_user_answer: '当前回答',
  structured_feedback: '结构化反馈',
  context_boundary_metadata: '上下文边界信息',
  new_github_reads: '新的 GitHub 读取',
  new_github_reads_after_prep: '准备后新的 GitHub 读取',
  direct_repo_reads: '直接读取仓库',
  direct_repository_reads: '直接读取仓库',
  direct_github_reads: '直接读取 GitHub',
  non_allowlisted_repo_evidence: '未允许的仓库证据',
  persist_raw_user_answer: '保存用户回答原文',
  candidate_scoring: '候选人评分',
  junior: '初级',
  mid: '中级',
  medium: '中级',
  senior: '高级',
  high: '高',
  low: '低',
  answer_coached: '回答已辅导',
  follow_up_ready: '追问已生成',
  summary_ready: '总结已生成',
  'Candidate language preference from this request.': '本次请求的候选语言偏好。',
  'Candidate feedback style preference from this request.':
    '本次请求的候选反馈风格偏好。',
  'Candidate practice category from this request.': '本次请求的候选练习分类。',
};

const WORKFLOW_FACT_LABELS: Record<string, string> = {
  active_role: '当前角色',
  role_kind: '角色类型',
  repository_access: '仓库访问',
  tool_access: '工具访问',
  persists_user_answer: '是否保存回答',
  allowed_evidence: '可用 evidence 数',
  saved_memory_count: '已确认记忆数',
};

// Use this only for known workflow UI display values. Boolean boundary facts
// should go through formatWorkflowFactValue so true/false keep field-specific meaning.
export function formatWorkflowDisplayTerm(value?: string): string | undefined {
  const normalized = normalizeString(value);
  if (!normalized) return undefined;
  const label = WORKFLOW_TERM_LABELS[normalized];
  return label || normalized;
}

export function buildMultiAgentTraceFlowLabels(
  trace?: GitHubRepoInterviewMultiAgentTrace,
): string[] {
  return buildMultiAgentTraceFlowNodes(trace).map((node) => node.label);
}

export function buildMultiAgentTraceFlowNodes(
  trace?: GitHubRepoInterviewMultiAgentTrace,
): GitHubRepoInterviewMultiAgentTraceFlowNode[] {
  if (!trace) return [];
  const nodes: GitHubRepoInterviewMultiAgentTraceFlowNode[] = [];
  const orchestratorName = formatWorkflowDisplayTerm(trace.orchestrator?.name);
  if (orchestratorName) {
    nodes.push({
      id: 'main_agent',
      label: orchestratorName,
      status: trace.orchestrator?.status,
      kind: 'orchestrator',
    });
  }
  for (const agent of trace.agents || []) {
    const label =
      formatWorkflowDisplayTerm(agent.id) ||
      formatWorkflowDisplayTerm(agent.role_name) ||
      normalizeString(agent.role_name) ||
      normalizeString(agent.id);
    if (label) {
      nodes.push({
        id: agent.id || agent.role_name || label,
        label,
        status: agent.status,
        kind: 'agent',
      });
    }
  }
  return nodes;
}

export function buildMultiAgentTraceSummary(
  trace?: GitHubRepoInterviewMultiAgentTrace,
): GitHubRepoInterviewMultiAgentTraceSummary | undefined {
  if (!trace) return undefined;
  const agents = trace.agents || [];
  const agentCount = agents.length;
  const completedAgentCount = agents.filter((agent) => agent.status === 'success').length;
  return {
    agentCount,
    completedAgentCount,
    statusLabel: `${completedAgentCount}/${agentCount} 已完成`,
    modeLabel: formatWorkflowDisplayTerm(trace.mode),
    scopeLabel: formatWorkflowDisplayTerm(trace.scope),
    usesRepoEvidence: agents.some((agent) => agent.uses_repo_evidence === true),
    readsUserAnswer: agents.some((agent) => agent.reads_user_answer === true),
    persistsMemory: agents.some((agent) => agent.persists_memory === true),
  };
}

export function buildGitHubRepoInterviewPrimaryPanelSectionIds(
  payload?: GitHubRepoInterviewWorkflowPayload,
): GitHubRepoInterviewPrimaryPanelSectionId[] {
  if (!payload) return [];
  const sections: GitHubRepoInterviewPrimaryPanelSectionId[] = [];
  const hasBoundaryDetails = Boolean(
    payload.data?.workflow?.current_stage ||
      payload.data?.workflow?.active_role ||
      payload.data?.workflow?.roles?.length ||
      payload.data?.evidence_policy ||
      payload.data?.evidence_details?.length ||
      payload.data?.context_policy ||
      payload.data?.context_snapshot ||
      payload.data?.saved_memory_context?.length,
  );
  if (payload.data?.workflow?.steps?.length) sections.push('workflow_steps');
  if (payload.data?.multi_agent_trace?.agents?.length) sections.push('multi_agent_trace');
  if (hasBoundaryDetails) sections.push('boundary_details');
  if (payload.data?.selected_question) sections.push('selected_question');
  if (payload.data?.answer_feedback) sections.push('answer_feedback');
  if (payload.data?.follow_up) sections.push('follow_up');
  if (payload.data?.other_questions?.length) sections.push('other_questions');
  if (payload.data?.session_summary) sections.push('session_summary');
  if (payload.data?.session_memory_context || payload.data?.session_memory_patch) {
    sections.push('session_memory');
  }
  if (payload.data?.memory_candidates?.length) sections.push('memory_candidates');
  if (payload.data?.vector_memory_candidate) sections.push('vector_memory_candidate');
  if (payload.data?.vector_memory_retrieval) sections.push('vector_memory_retrieval');
  if (payload.warnings?.length || payload.errors?.length) sections.push('notices');
  if (normalizeString(payload.next_step)) sections.push('next_step');
  return sections;
}

export function formatWorkflowFactLabel(id: string, fallback: string): string {
  return WORKFLOW_FACT_LABELS[id] || fallback;
}

export function formatWorkflowFactValue(id: string, value: string): string {
  if (id === 'persists_user_answer') {
    if (value === 'false') return '不保存用户回答';
    if (value === 'true') return '会保存用户回答';
  }
  return formatWorkflowDisplayTerm(value) || value;
}

export function formatWorkflowStepStatusLabel(
  step: GitHubRepoInterviewWorkflowStep,
  payload?: GitHubRepoInterviewWorkflowPayload,
): string {
  const status = step.status || 'pending';
  const hasGeneratedFollowUpQuestions = Boolean(
    payload?.data?.answer_feedback?.follow_up_questions?.length ||
      payload?.data?.follow_up?.questions?.length,
  );

  if (step.id === 'follow_up' && status === 'pending') {
    return hasGeneratedFollowUpQuestions ? '已生成，待回答' : '未进入';
  }

  if (step.id === 'summary' && status === 'pending') {
    return '未生成';
  }

  return formatWorkflowDisplayTerm(status) || status;
}

function parseJsonObject(value: unknown): Record<string, unknown> | undefined {
  if (typeof value === 'string') {
    if (!value.trim() || value === 'STREAMING') return undefined;
    try {
      const parsed = JSON.parse(value);
      return isObject(parsed) ? parsed : undefined;
    } catch {
      return undefined;
    }
  }
  return isObject(value) ? value : undefined;
}

function hasExplicitSummarySuccess(value: unknown, depth = 0): boolean {
  if (depth > 4) return false;
  const parsed = parseJsonObject(value);
  if (!parsed) return false;

  const status = normalizeString(parsed.status);
  if (status === 'success') return true;
  if (parsed.success === true) return true;
  if (status === 'error' || parsed.success === false) return false;

  return [parsed.result, parsed.output, parsed.tool_execution].some((candidate) =>
    hasExplicitSummarySuccess(candidate, depth + 1),
  );
}

export function hasCompletedConversationSummary(messages: unknown): boolean {
  if (!Array.isArray(messages)) return false;

  return messages.some((message) => {
    if (!isObject(message) || message.type !== 'tool') return false;
    const metadata = parseJsonObject(message.metadata);
    const content = parseJsonObject(message.content);
    const toolName = normalizeString(
      metadata?.tool_name ||
        metadata?.function_name ||
        content?.tool_name ||
        parseJsonObject(content?.tool_execution)?.function_name,
    )?.replace(/-/g, '_');
    if (toolName !== 'github_repo_interview_conversation_summary') return false;
    return hasExplicitSummarySuccess(content);
  });
}

export function buildWorkflowBoundaryFacts(
  payload: GitHubRepoInterviewWorkflowPayload,
): GitHubRepoInterviewWorkflowBoundaryFact[] {
  const policy = payload.data?.context_policy;
  const workflow = payload.data?.workflow;
  const facts: GitHubRepoInterviewWorkflowBoundaryFact[] = [];

  const activeRole = boundaryValue(policy?.active_role || workflow?.active_role);
  if (activeRole) {
    facts.push({
      id: 'active_role',
      label: 'Active role',
      value: activeRole,
      tone: 'neutral',
    });
  }

  const roleKind = boundaryValue(policy?.role_kind);
  if (roleKind) {
    facts.push({
      id: 'role_kind',
      label: 'Role kind',
      value: roleKind,
      tone: 'neutral',
    });
  }

  const repositoryAccess = boundaryValue(policy?.repository_access);
  if (repositoryAccess) {
    facts.push({
      id: 'repository_access',
      label: 'Repository access',
      value: repositoryAccess,
      tone: repositoryAccess === 'no_new_repository_access' ? 'success' : 'warning',
    });
  }

  const toolAccess = boundaryValue(policy?.tool_access);
  if (toolAccess) {
    facts.push({
      id: 'tool_access',
      label: 'Tool access',
      value: toolAccess,
      tone: toolAccess === 'none' ? 'success' : 'warning',
    });
  }

  if (typeof policy?.persists_user_answer === 'boolean') {
    facts.push({
      id: 'persists_user_answer',
      label: 'Persists answer',
      value: String(policy.persists_user_answer),
      tone: policy.persists_user_answer ? 'warning' : 'success',
    });
  }

  const allowedEvidenceCount = policy?.allowed_evidence_ids?.length;
  if (allowedEvidenceCount) {
    facts.push({
      id: 'allowed_evidence',
      label: 'Allowed evidence',
      value: String(allowedEvidenceCount),
      tone: 'neutral',
    });
  }

  return facts;
}

export function groupWorkflowRoles(
  roles?: GitHubRepoInterviewWorkflowRole[],
): GitHubRepoInterviewWorkflowRoleGroup[] {
  const visibleRoles = Array.isArray(roles) ? roles : [];
  const deterministic = visibleRoles.filter((role) => role.kind === 'deterministic');
  const llm = visibleRoles.filter((role) => role.kind === 'llm');
  const other = visibleRoles.filter(
    (role) => role.kind !== 'deterministic' && role.kind !== 'llm',
  );

  const groups: GitHubRepoInterviewWorkflowRoleGroup[] = [
    { id: 'deterministic', label: 'Deterministic', roles: deterministic },
    { id: 'llm', label: 'LLM', roles: llm },
    { id: 'other', label: 'Other', roles: other },
  ];
  return groups.filter((group) => group.roles.length > 0);
}

function normalizeWorkflowCompletion(
  value: unknown,
): GitHubRepoInterviewWorkflowCompletion | undefined {
  if (!isObject(value)) {
    return undefined;
  }
  const completion = {
    answer_coached: normalizeBoolean(value.answer_coached),
    follow_up_completed: normalizeBoolean(value.follow_up_completed),
    summary_scope: normalizeString(value.summary_scope),
  };
  return Object.values(completion).some((item) => item !== undefined)
    ? completion
    : undefined;
}

function normalizeAnswerState(
  value: unknown,
): GitHubRepoInterviewWorkflowAnswerState | undefined {
  if (!isObject(value)) {
    return undefined;
  }
  const state = {
    has_answer_feedback: normalizeBoolean(value.has_answer_feedback),
    has_follow_up_feedback: normalizeBoolean(value.has_follow_up_feedback),
    follow_up_mode: normalizeString(value.follow_up_mode),
    follow_up_count: normalizeNumber(value.follow_up_count),
  };
  return Object.values(state).some((item) => item !== undefined)
    ? state
    : undefined;
}

function normalizeRedactionPolicy(
  value: unknown,
): GitHubRepoInterviewWorkflowRedactionPolicy | undefined {
  if (!isObject(value)) {
    return undefined;
  }
  const policy = {
    includes_user_answer: normalizeBoolean(value.includes_user_answer),
    includes_follow_up_answer: normalizeBoolean(value.includes_follow_up_answer),
    includes_hidden_source_content: normalizeBoolean(
      value.includes_hidden_source_content,
    ),
    includes_repo_evidence_text: normalizeBoolean(value.includes_repo_evidence_text),
  };
  return Object.values(policy).some((item) => item !== undefined)
    ? policy
    : undefined;
}

function normalizeContextSnapshot(
  value: unknown,
): GitHubRepoInterviewWorkflowContextSnapshot | undefined {
  if (!isObject(value)) {
    return undefined;
  }
  const vectorMemorySource = isObject(value.vector_memory) ? value.vector_memory : {};
  const snapshot = {
    version: normalizeString(value.version),
    scope: normalizeString(value.scope),
    persistence: normalizeString(value.persistence),
    current_stage: normalizeString(value.current_stage),
    active_role: normalizeString(value.active_role),
    role_kind: normalizeString(value.role_kind),
    visible_sources: normalizeStringArray(value.visible_sources),
    hidden_sources: normalizeStringArray(value.hidden_sources),
    allowed_evidence_ids: normalizeStringArray(value.allowed_evidence_ids),
    allowed_source_paths: normalizeStringArray(value.allowed_source_paths),
    repository_access: normalizeString(value.repository_access),
    tool_access: normalizeString(value.tool_access),
    persists_user_answer: normalizeBoolean(value.persists_user_answer),
    answer_state: normalizeAnswerState(value.answer_state),
    workflow_completion: normalizeWorkflowCompletion(value.workflow_completion),
    redaction_policy: normalizeRedactionPolicy(value.redaction_policy),
    saved_memory_count: normalizeNumber(value.saved_memory_count),
    vector_memory: Object.keys(vectorMemorySource).length
      ? {
          enabled: normalizeBoolean(vectorMemorySource.enabled),
          status: normalizeString(vectorMemorySource.status),
          matched_count: normalizeNumber(vectorMemorySource.matched_count),
          threshold: normalizeNumber(vectorMemorySource.threshold),
          model: normalizeString(vectorMemorySource.model),
        }
      : undefined,
  };
  return Object.values(snapshot).some((item) => item !== undefined)
    ? snapshot
    : undefined;
}

function normalizeMemoryCandidate(
  value: unknown,
): GitHubRepoInterviewWorkflowMemoryCandidate | null {
  if (!isObject(value)) {
    return null;
  }
  const privacySource = isObject(value.privacy) ? value.privacy : {};
  const privacy = {
    includes_user_answer: normalizeBoolean(privacySource.includes_user_answer),
    includes_follow_up_answer: normalizeBoolean(
      privacySource.includes_follow_up_answer,
    ),
    includes_repo_evidence_text: normalizeBoolean(
      privacySource.includes_repo_evidence_text,
    ),
  };
  const candidate = {
    id: normalizeString(value.id),
    type: normalizeString(value.type),
    value: normalizeString(value.value),
    label: normalizeString(value.label),
    source_stage: normalizeString(value.source_stage),
    source_fields: normalizeStringArray(value.source_fields),
    requires_user_confirmation: normalizeBoolean(value.requires_user_confirmation),
    status: normalizeString(value.status),
    persisted: normalizeBoolean(value.persisted),
    privacy: Object.values(privacy).some((item) => item !== undefined)
      ? privacy
      : undefined,
  };
  return Object.values(candidate).some((item) => item !== undefined)
    ? candidate
    : null;
}

const VECTOR_TEXT_FORBIDDEN_MARKERS = [
  'http://',
  'https://',
  'api_key',
  'authorization:',
  'traceback',
  'user_answer',
  'follow_up_answer',
  'raw_answer',
];

function normalizeVectorText(value: unknown): string | undefined {
  const text = normalizeString(value)?.slice(0, 600);
  if (!text) return undefined;
  const lowered = text.toLowerCase();
  return VECTOR_TEXT_FORBIDDEN_MARKERS.some((marker) => lowered.includes(marker))
    ? undefined
    : text;
}

function normalizeVectorMemoryCandidate(
  value: unknown,
): GitHubRepoInterviewVectorMemoryCandidate | undefined {
  if (!isObject(value)) return undefined;
  const text = normalizeVectorText(value.text);
  const privacySource = isObject(value.privacy) ? value.privacy : {};
  if (
    !text ||
    value.type !== 'practice_experience_summary' ||
    value.requires_user_confirmation !== true ||
    value.persisted !== false ||
    value.status !== 'candidate_only' ||
    privacySource.includes_user_answer !== false ||
    privacySource.includes_follow_up_answer !== false ||
    privacySource.includes_repo_evidence_text !== false
  ) {
    return undefined;
  }
  const provenanceSource = isObject(value.provenance) ? value.provenance : {};
  const kind = provenanceSource.kind === 'demo_fixture' ? 'demo_fixture' : 'user_confirmed';
  return {
    id: normalizeString(value.id),
    type: 'practice_experience_summary',
    text,
    content_hash: normalizeString(value.content_hash),
    target_role: normalizeString(value.target_role),
    category: normalizeString(value.category),
    source_thread_id: normalizeString(value.source_thread_id),
    source_agent_run_id: normalizeString(value.source_agent_run_id),
    source_stage: 'summarize',
    requires_user_confirmation: true,
    status: 'candidate_only',
    persisted: false,
    provenance: { kind },
    privacy: {
      includes_user_answer: false,
      includes_follow_up_answer: false,
      includes_repo_evidence_text: false,
    },
  };
}

function normalizeVectorMemoryContext(
  value: unknown,
): GitHubRepoInterviewVectorMemoryContext | null {
  if (!isObject(value) || value.persisted !== true) return null;
  const text = normalizeVectorText(value.text);
  const similarityValue = normalizeNumber(value.similarity);
  if (!text || similarityValue === undefined) return null;
  const provenanceSource = isObject(value.provenance) ? value.provenance : {};
  return {
    id: normalizeString(value.id),
    text,
    similarity: Math.max(0, Math.min(1, similarityValue)),
    target_role: normalizeString(value.target_role),
    category: normalizeString(value.category),
    source_stage: normalizeString(value.source_stage),
    persisted: true,
    provenance: {
      kind: provenanceSource.kind === 'demo_fixture' ? 'demo_fixture' : 'user_confirmed',
    },
  };
}

function normalizeVectorMemoryRetrieval(
  value: unknown,
): GitHubRepoInterviewVectorMemoryRetrieval | undefined {
  if (!isObject(value)) return undefined;
  const allowed = new Set(['disabled', 'matched', 'no_match', 'embedding_error', 'retrieval_error']);
  const rawStatus = normalizeString(value.status);
  const status = rawStatus && allowed.has(rawStatus)
    ? (rawStatus as GitHubRepoInterviewVectorMemoryRetrieval['status'])
    : 'retrieval_error';
  return {
    status,
    query_source: normalizeString(value.query_source),
    model: normalizeString(value.model),
    threshold: normalizeNumber(value.threshold),
    top_k: normalizeNumber(value.top_k),
    candidate_count: normalizeNumber(value.candidate_count),
    matched_count: normalizeNumber(value.matched_count),
    applied_count: normalizeNumber(value.applied_count),
    filtered_by_threshold: normalizeNumber(value.filtered_by_threshold),
    filtered_by_topk: normalizeNumber(value.filtered_by_topk),
    filtered_count: normalizeNumber(value.filtered_count),
    fallback_used: normalizeBoolean(value.fallback_used),
  };
}

function normalizeSessionMemory(value: unknown): GitHubRepoInterviewSessionMemory | undefined {
  if (!isObject(value)) {
    return undefined;
  }
  const memory: GitHubRepoInterviewSessionMemory = {
    target_role: normalizeString(value.target_role),
    target_role_source: normalizeString(value.target_role_source),
    answered_question_ids: normalizeStringArray(value.answered_question_ids),
    last_question_id: normalizeString(value.last_question_id),
    current_practice_category: normalizeString(value.current_practice_category),
    missed_evidence_ids: normalizeStringArray(value.missed_evidence_ids),
    next_practice_suggestion: normalizeString(value.next_practice_suggestion),
    summary_completed: normalizeBoolean(value.summary_completed),
  };
  return Object.values(memory).some((item) => item !== undefined) ? memory : undefined;
}

const ALLOWED_TRACE_AGENT_IDS = new Set([
  'repository_analyst',
  'interview_question',
  'answer_coach',
  'quality_reviewer',
]);

const ALLOWED_TRACE_STATUSES = new Set([
  'pending',
  'success',
  'partial',
  'error',
  'skipped',
]);

const ALLOWED_COVERAGE_SIGNALS = new Set(['not_started', 'partial', 'grounded']);
const ALLOWED_EVIDENCE_GROUNDING_SIGNALS = new Set(['missing', 'partial', 'grounded']);
const ALLOWED_BOUNDARY_HEALTH_SIGNALS = new Set(['clean', 'warning', 'error']);
const ALLOWED_NEXT_STEP_SIGNALS = new Set([
  'answer_question',
  'answer_follow_up',
  'revise_with_evidence',
  'summarize',
  'select_another_question',
  'retry_same_stage',
]);
function normalizeTraceStatus(
  value: unknown,
): GitHubRepoInterviewMultiAgentTraceStatus | undefined {
  return typeof value === 'string' && ALLOWED_TRACE_STATUSES.has(value)
    ? (value as GitHubRepoInterviewMultiAgentTraceStatus)
    : undefined;
}

function normalizeTraceAgent(value: unknown): GitHubRepoInterviewAgentNode | null {
  if (!isObject(value) || typeof value.id !== 'string' || !ALLOWED_TRACE_AGENT_IDS.has(value.id)) {
    return null;
  }
  const agent: GitHubRepoInterviewAgentNode = {
    id: value.id as GitHubRepoInterviewAgentNode['id'],
    role_name: normalizeString(value.role_name),
    status: normalizeTraceStatus(value.status),
    stage: normalizeString(value.stage),
    input_sources: normalizeStringArray(value.input_sources),
    visible_context: normalizeStringArray(value.visible_context),
    forbidden_scope: normalizeStringArray(value.forbidden_scope),
    uses_repo_evidence: normalizeBoolean(value.uses_repo_evidence),
    reads_user_answer: normalizeBoolean(value.reads_user_answer),
    persists_memory: normalizeBoolean(value.persists_memory),
    output_summary: normalizeString(value.output_summary),
  };
  return Object.values(agent).some((item) => item !== undefined) ? agent : null;
}

function normalizeQualitySignals(value: unknown): GitHubRepoInterviewQualitySignals | undefined {
  if (!isObject(value)) {
    return undefined;
  }
  const coverage =
    typeof value.coverage === 'string' && ALLOWED_COVERAGE_SIGNALS.has(value.coverage)
      ? (value.coverage as GitHubRepoInterviewQualitySignals['coverage'])
      : undefined;
  const evidenceGrounding =
    typeof value.evidence_grounding === 'string' &&
    ALLOWED_EVIDENCE_GROUNDING_SIGNALS.has(value.evidence_grounding)
      ? (value.evidence_grounding as GitHubRepoInterviewQualitySignals['evidence_grounding'])
      : undefined;
  const boundaryHealth =
    typeof value.boundary_health === 'string' &&
    ALLOWED_BOUNDARY_HEALTH_SIGNALS.has(value.boundary_health)
      ? (value.boundary_health as GitHubRepoInterviewQualitySignals['boundary_health'])
      : undefined;
  const recommendedNextStep =
    typeof value.recommended_next_step === 'string' &&
    ALLOWED_NEXT_STEP_SIGNALS.has(value.recommended_next_step)
      ? (value.recommended_next_step as GitHubRepoInterviewQualitySignals['recommended_next_step'])
      : undefined;
  const signals: GitHubRepoInterviewQualitySignals = {
    coverage,
    evidence_grounding: evidenceGrounding,
    boundary_health: boundaryHealth,
    recommended_next_step: recommendedNextStep,
  };
  return Object.values(signals).some((item) => item !== undefined) ? signals : undefined;
}

function normalizeMultiAgentTrace(
  value: unknown,
): GitHubRepoInterviewMultiAgentTrace | undefined {
  if (!isObject(value)) {
    return undefined;
  }
  const orchestratorSource = isObject(value.orchestrator) ? value.orchestrator : {};
  const orchestrator = {
    name: orchestratorSource.name === 'MainAgent' ? 'MainAgent' as const : undefined,
    status: normalizeTraceStatus(orchestratorSource.status),
    output_summary: normalizeString(orchestratorSource.output_summary),
  };
  const trace: GitHubRepoInterviewMultiAgentTrace = {
    version: normalizeString(value.version),
    mode: value.mode === 'controlled_local_trace' ? 'controlled_local_trace' : undefined,
    scope: value.scope === 'request' ? 'request' : undefined,
    orchestrator: Object.values(orchestrator).some((item) => item !== undefined)
      ? orchestrator
      : undefined,
    agents: normalizeObjectArray(value.agents, normalizeTraceAgent),
    quality_signals: normalizeQualitySignals(value.quality_signals),
  };
  return Object.values(trace).some((item) => item !== undefined) ? trace : undefined;
}

function normalizeAnswerQualitySignal(
  value: unknown,
): GitHubRepoInterviewWorkflowAnswerQualitySignal | null {
  if (!isObject(value)) {
    return null;
  }
  const id = normalizeString(value.id);
  const status = normalizeString(value.status);
  const severity = normalizeString(value.severity);
  if (
    !id ||
    !status ||
    !ANSWER_QUALITY_SIGNAL_IDS.has(id) ||
    !ANSWER_QUALITY_SIGNAL_STATUSES.has(status) ||
    (severity && !ANSWER_QUALITY_SIGNAL_SEVERITIES.has(severity))
  ) {
    return null;
  }
  const signal = {
    id: id as GitHubRepoInterviewWorkflowAnswerQualitySignalId,
    label: normalizeString(value.label),
    status: status as GitHubRepoInterviewWorkflowAnswerQualitySignalStatus,
    severity: severity as GitHubRepoInterviewWorkflowAnswerQualitySignalSeverity | undefined,
    basis_fields: normalizeStringArray(value.basis_fields),
    evidence_refs: normalizeStringArray(value.evidence_refs),
    notes: normalizeStringArray(value.notes),
  };
  return signal;
}

function normalizeNormalizedIntent(value: unknown): GitHubRepoInterviewNormalizedIntent | undefined {
  if (!isObject(value)) {
    return undefined;
  }
  const entries = Object.entries(value)
    .map(([key, item]) => {
      const source = isObject(item) ? item : {};
      return [
        key,
        {
          raw: normalizeString(source.raw),
          normalized: normalizeString(source.normalized),
        },
      ] as const;
    })
    .filter(([, item]) => item.raw || item.normalized);

  return entries.length ? Object.fromEntries(entries) : undefined;
}

function normalizeConversationPracticeOverview(
  value: unknown,
): GitHubRepoInterviewConversationPracticeOverview | undefined {
  if (!isObject(value)) {
    return undefined;
  }
  const overview = {
    repository: normalizeString(value.repository),
    role: normalizeString(value.role),
    difficulty: normalizeString(value.difficulty),
    completed_items: normalizeStringArray(value.completed_items),
    unfinished_items: normalizeStringArray(value.unfinished_items),
  };
  return Object.values(overview).some((item) => item !== undefined) ? overview : undefined;
}

function normalizeConversationHighlight(
  value: unknown,
): GitHubRepoInterviewConversationHighlight | null {
  if (!isObject(value)) {
    return null;
  }
  const highlight = {
    title: normalizeString(value.title),
    detail: normalizeString(value.detail),
  };
  return Object.values(highlight).some((item) => item !== undefined) ? highlight : null;
}

function normalizeConversationImprovement(
  value: unknown,
): GitHubRepoInterviewConversationImprovement | null {
  if (!isObject(value)) {
    return null;
  }
  const improvement = {
    weakness: normalizeString(value.weakness),
    evidence: normalizeString(value.evidence),
    suggestion: normalizeString(value.suggestion),
  };
  return Object.values(improvement).some((item) => item !== undefined) ? improvement : null;
}

function normalizeConversationAbility(
  value: unknown,
): GitHubRepoInterviewConversationAbility | null {
  if (!isObject(value)) {
    return null;
  }
  const ability = {
    dimension: normalizeString(value.dimension),
    score: normalizeNumber(value.score),
    rationale: normalizeString(value.rationale),
  };
  return Object.values(ability).some((item) => item !== undefined) ? ability : null;
}

function normalizeConversationSummary(value: unknown) {
  if (!isObject(value)) {
    return undefined;
  }
  const summary = {
    overview: normalizeString(value.overview),
    raw_report: normalizeString(value.raw_report),
    discussed_questions: normalizeStringArray(value.discussed_questions),
    agent_help: normalizeStringArray(value.agent_help),
    open_items: normalizeStringArray(value.open_items),
    practice_overview: normalizeConversationPracticeOverview(value.practice_overview),
    performance_highlights: normalizeObjectArray(
      value.performance_highlights,
      normalizeConversationHighlight,
    ),
    improvement_areas: normalizeObjectArray(
      value.improvement_areas,
      normalizeConversationImprovement,
    ),
    ability_profile: normalizeObjectArray(value.ability_profile, normalizeConversationAbility),
    next_practice_steps: normalizeStringArray(value.next_practice_steps),
  };
  return Object.values(summary).some((item) => item !== undefined) ? summary : undefined;
}

function normalizeData(value: unknown): GitHubRepoInterviewWorkflowPayload['data'] {
  if (!isObject(value)) {
    return undefined;
  }
  const workflowSource = isObject(value.workflow) ? value.workflow : {};
  const questionSource = isObject(value.selected_question) ? value.selected_question : {};
  const policySource = isObject(value.evidence_policy) ? value.evidence_policy : {};
  const feedbackSource = isObject(value.answer_feedback) ? value.answer_feedback : {};
  const followUpSource = isObject(value.follow_up) ? value.follow_up : {};
  const summarySource = isObject(value.session_summary) ? value.session_summary : {};

  const data: GitHubRepoInterviewWorkflowPayload['data'] = {
    workflow: {
      current_stage: normalizeString(workflowSource.current_stage),
      steps: normalizeObjectArray(workflowSource.steps, normalizeStep),
      active_role: normalizeString(workflowSource.active_role),
      roles: normalizeObjectArray(workflowSource.roles, normalizeRole),
      follow_up_count: normalizeNumber(workflowSource.follow_up_count),
    },
    selected_question: {
      id: normalizeString(questionSource.id),
      category: normalizeString(questionSource.category),
      difficulty: normalizeString(questionSource.difficulty),
      question: normalizeString(questionSource.question),
      answer_direction: normalizeString(questionSource.answer_direction),
      source_paths: normalizeStringArray(questionSource.source_paths),
      evidence_refs: normalizeStringArray(questionSource.evidence_refs),
      confidence: normalizeString(questionSource.confidence),
    },
    evidence_policy: {
      source: normalizeString(policySource.source),
      allowed_evidence_ids: normalizeStringArray(policySource.allowed_evidence_ids),
      max_evidence_details: normalizeNumber(policySource.max_evidence_details),
      repository_access: normalizeString(policySource.repository_access),
    },
    context_policy: normalizeContextPolicy(value.context_policy),
    context_snapshot: normalizeContextSnapshot(value.context_snapshot),
    multi_agent_trace: normalizeMultiAgentTrace(value.multi_agent_trace),
    summary_kind: normalizeString(value.summary_kind),
    conversation_turn_count: normalizeNumber(value.conversation_turn_count),
    conversation_summary: normalizeConversationSummary(value.conversation_summary),
    memory_candidates: normalizeObjectArray(value.memory_candidates, normalizeMemoryCandidate),
    saved_memory_context: normalizeObjectArray(value.saved_memory_context, normalizeMemoryCandidate),
    session_memory_context: normalizeSessionMemory(value.session_memory_context),
    session_memory_patch: normalizeSessionMemory(value.session_memory_patch),
    vector_memory_candidate: normalizeVectorMemoryCandidate(value.vector_memory_candidate),
    vector_memory_context: normalizeObjectArray(
      value.vector_memory_context,
      normalizeVectorMemoryContext,
    ),
    vector_memory_retrieval: normalizeVectorMemoryRetrieval(value.vector_memory_retrieval),
    answer_quality_signals: normalizeObjectArray(
      value.answer_quality_signals,
      normalizeAnswerQualitySignal,
    ),
    evidence_details: normalizeObjectArray(value.evidence_details, normalizeEvidenceDetail),
    normalized_intent: normalizeNormalizedIntent(value.normalized_intent),
    answer_feedback: {
      summary: normalizeString(feedbackSource.summary),
      strengths: normalizeStringArray(feedbackSource.strengths),
      gaps: normalizeStringArray(feedbackSource.gaps),
      evidence_missed: normalizeObjectArray(feedbackSource.evidence_missed, (item) => {
        if (!isObject(item)) return null;
        const missed = {
          evidence_id: normalizeString(item.evidence_id),
          source_path: normalizeString(item.source_path),
          reason: normalizeString(item.reason),
        };
        return Object.values(missed).some((entry) => entry !== undefined)
          ? missed
          : null;
      }),
      suggested_answer_outline: normalizeStringArray(feedbackSource.suggested_answer_outline),
      follow_up_questions: normalizeStringArray(feedbackSource.follow_up_questions),
      grounding_notes: normalizeStringArray(feedbackSource.grounding_notes),
    },
    follow_up: {
      mode: normalizeString(followUpSource.mode),
      questions: normalizeStringArray(followUpSource.questions),
      feedback: normalizeStringArray(followUpSource.feedback),
      grounding_notes: normalizeStringArray(followUpSource.grounding_notes),
    },
    other_questions: normalizeObjectArray(value.other_questions, (item) => {
      if (!isObject(item)) return null;
      const question = {
        id: normalizeString(item.id),
        category: normalizeString(item.category),
        difficulty: normalizeString(item.difficulty),
        question: normalizeString(item.question),
      };
      return question.id && question.question ? question : null;
    }),
    session_summary: {
      covered_evidence: normalizeStringArray(summarySource.covered_evidence),
      missed_evidence: normalizeStringArray(summarySource.missed_evidence),
      practice_notes: normalizeStringArray(summarySource.practice_notes),
      next_practice_suggestion: normalizeString(summarySource.next_practice_suggestion),
      workflow_completion: normalizeWorkflowCompletion(summarySource.workflow_completion),
    },
  };

  for (const key of Object.keys(data) as Array<keyof typeof data>) {
    const valueForKey = data[key];
    if (
      valueForKey &&
      typeof valueForKey === 'object' &&
      !Array.isArray(valueForKey) &&
      Object.values(valueForKey).every((entry) => entry === undefined)
    ) {
      delete data[key];
    }
  }

  return Object.values(data).some((item) => item !== undefined) ? data : undefined;
}

function normalizeInput(value: unknown): GitHubRepoInterviewWorkflowPayload['input'] {
  if (!isObject(value)) {
    return undefined;
  }
  const input: GitHubRepoInterviewWorkflowPayload['input'] = {
    stage: normalizeString(value.stage),
    question_id: normalizeString(value.question_id),
    language: value.language === 'zh' || value.language === 'en' ? value.language : undefined,
    coach_style: normalizeString(value.coach_style),
    preferred_question_category: normalizeString(value.preferred_question_category),
    max_follow_ups: normalizeNumber(value.max_follow_ups),
    user_answer_excerpt: normalizeString(value.user_answer_excerpt),
  };
  return Object.values(input).some((item) => item !== undefined) ? input : undefined;
}

function isWorkflowPayload(value: Record<string, unknown>): boolean {
  return (
    value.tool === 'github_repo_interview_workflow' ||
    value.tool === 'github-repo-interview-workflow' ||
    value.tool === 'github_repo_interview_conversation_summary' ||
    value.tool === 'github-repo-interview-conversation-summary' ||
    value.type === 'github_repo_interview_workflow' ||
    value.type === 'github-repo-interview-workflow' ||
    value.type === 'github_repo_interview_conversation_summary' ||
    value.type === 'github-repo-interview-conversation-summary'
  );
}

function normalizePayload(
  value: Record<string, unknown>,
): GitHubRepoInterviewWorkflowPayload | null {
  const payload: GitHubRepoInterviewWorkflowPayload = {
    tool: normalizeString(value.tool),
    type: normalizeString(value.type),
    version: normalizeString(value.version),
    partial: normalizeBoolean(value.partial),
    input: normalizeInput(value.input),
    data: normalizeData(value.data),
    warnings: normalizeObjectArray(value.warnings, normalizeNotice),
    errors: normalizeObjectArray(value.errors, normalizeNotice),
    next_step: normalizeString(value.next_step),
  };
  if (value.status === 'success' || value.status === 'partial' || value.status === 'error') {
    payload.status = value.status;
  }

  const hasMeaningfulPayload = Boolean(
    payload.data?.workflow ||
      payload.data?.selected_question ||
      payload.data?.evidence_policy ||
      payload.data?.context_policy ||
      payload.data?.context_snapshot ||
      payload.data?.multi_agent_trace ||
      payload.data?.summary_kind ||
      payload.data?.conversation_summary ||
      payload.data?.memory_candidates?.length ||
      payload.data?.saved_memory_context?.length ||
      payload.data?.session_memory_context ||
      payload.data?.session_memory_patch ||
      payload.data?.vector_memory_candidate ||
      payload.data?.vector_memory_context?.length ||
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
  return hasMeaningfulPayload ? payload : null;
}

export function extractGitHubRepoInterviewWorkflowData(
  toolContent?: unknown,
  assistantContent?: unknown,
): GitHubRepoInterviewWorkflowPayload | null {
  const candidates = [
    ...collectCandidates(toolContent),
    ...collectCandidates(assistantContent),
  ];
  for (const candidate of candidates) {
    const parsed = parseJsonCandidate(candidate);
    if (!isObject(parsed) || !isWorkflowPayload(parsed)) {
      continue;
    }
    const payload = normalizePayload(parsed);
    if (payload) {
      return payload;
    }
  }
  return null;
}
