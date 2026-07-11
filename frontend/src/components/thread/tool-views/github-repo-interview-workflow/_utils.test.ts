import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildGitHubRepoInterviewPrimaryPanelSectionIds,
  buildMultiAgentTraceFlowLabels,
  buildMultiAgentTraceFlowNodes,
  buildMultiAgentTraceSummary,
  buildWorkflowBoundaryFacts,
  extractGitHubRepoInterviewWorkflowData,
  formatWorkflowDisplayTerm,
  formatWorkflowFactLabel,
  formatWorkflowFactValue,
  formatWorkflowStepStatusLabel,
  groupWorkflowRoles,
  type GitHubRepoInterviewWorkflowPayload,
  type GitHubRepoInterviewWorkflowRole,
} from './_utils';
import {
  formatGitHubInterviewCategory,
  formatGitHubInterviewDifficulty,
} from '../github-repo-interview-categories';

test('buildWorkflowBoundaryFacts falls back to workflow active_role', () => {
  const payload: GitHubRepoInterviewWorkflowPayload = {
    data: {
      workflow: {
        active_role: 'answer_coach',
      },
    },
  };

  assert.deepEqual(buildWorkflowBoundaryFacts(payload), [
    {
      id: 'active_role',
      label: 'Active role',
      value: 'answer_coach',
      tone: 'neutral',
    },
  ]);
});

test('buildWorkflowBoundaryFacts marks unsafe boundary values as warning', () => {
  const payload: GitHubRepoInterviewWorkflowPayload = {
    data: {
      context_policy: {
        active_role: 'answer_coach',
        role_kind: 'llm',
        repository_access: 'new_repository_access',
        tool_access: 'sandbox',
        persists_user_answer: true,
        allowed_evidence_ids: ['manifest:pyproject.toml'],
      },
    },
  };

  const facts = buildWorkflowBoundaryFacts(payload);

  assert.equal(facts.find((fact) => fact.id === 'role_kind')?.tone, 'neutral');
  assert.equal(facts.find((fact) => fact.id === 'repository_access')?.tone, 'warning');
  assert.equal(facts.find((fact) => fact.id === 'tool_access')?.tone, 'warning');
  assert.equal(facts.find((fact) => fact.id === 'persists_user_answer')?.tone, 'warning');
  assert.deepEqual(facts.find((fact) => fact.id === 'allowed_evidence'), {
    id: 'allowed_evidence',
    label: 'Allowed evidence',
    value: '1',
    tone: 'neutral',
  });
});

test('buildWorkflowBoundaryFacts omits allowed evidence count when list is empty', () => {
  const payload: GitHubRepoInterviewWorkflowPayload = {
    data: {
      context_policy: {
        active_role: 'answer_coach',
        allowed_evidence_ids: [],
      },
    },
  };

  assert.equal(
    buildWorkflowBoundaryFacts(payload).some((fact) => fact.id === 'allowed_evidence'),
    false,
  );
});

test('groupWorkflowRoles separates deterministic, llm, and other roles', () => {
  const roles: GitHubRepoInterviewWorkflowRole[] = [
    { id: 'question_selector', kind: 'deterministic' },
    { id: 'answer_coach', kind: 'llm' },
    { id: 'missing_kind' },
    { id: 'custom_agent', kind: 'custom' },
  ];

  const groups = groupWorkflowRoles(roles);

  assert.deepEqual(
    groups.map((group) => ({
      id: group.id,
      roleIds: group.roles.map((role) => role.id),
    })),
    [
      { id: 'deterministic', roleIds: ['question_selector'] },
      { id: 'llm', roleIds: ['answer_coach'] },
      { id: 'other', roleIds: ['missing_kind', 'custom_agent'] },
    ],
  );
});

test('workflow display helpers translate known protocol terms and preserve raw values', () => {
  assert.equal(formatWorkflowDisplayTerm('deterministic'), '确定性角色');
  assert.equal(formatWorkflowDisplayTerm('llm'), 'LLM 角色');
  assert.equal(formatWorkflowDisplayTerm('no_new_repository_access'), '无新仓库访问');
  assert.equal(
    formatWorkflowDisplayTerm('workflow_orchestrator'),
    'workflow_orchestrator',
  );
});

test('workflow display helpers show localized interview labels without protocol echoes', () => {
  assert.equal(formatGitHubInterviewCategory('implementation detail'), '实现细节');
  assert.equal(formatGitHubInterviewCategory('dependency and packaging'), '依赖与工程化');
  assert.equal(formatGitHubInterviewCategory('testing and automation'), '测试与自动化');
  assert.equal(formatGitHubInterviewDifficulty('mid'), '中级');
  assert.equal(formatGitHubInterviewDifficulty('senior'), '高级');
  assert.equal(formatWorkflowDisplayTerm('mid'), '中级');
  assert.equal(formatWorkflowDisplayTerm('senior'), '高级');
  assert.equal(formatWorkflowDisplayTerm('unknown_protocol_value'), 'unknown_protocol_value');
});

test('workflow fact display helpers translate labels and safe boundary values', () => {
  assert.equal(formatWorkflowFactLabel('active_role', 'Active role'), '当前角色');
  assert.equal(formatWorkflowFactLabel('repository_access', 'Repository access'), '仓库访问');
  assert.equal(
    formatWorkflowFactValue('tool_access', 'none'),
    '无工具访问',
  );
  assert.equal(
    formatWorkflowFactValue('persists_user_answer', 'false'),
    '不保存用户回答',
  );
  assert.equal(
    formatWorkflowFactValue('persists_user_answer', 'true'),
    '会保存用户回答',
  );
});

test('normalizes follow up mode, follow up count, and workflow completion', () => {
  const payload = extractGitHubRepoInterviewWorkflowData(
    JSON.stringify({
      tool: 'github_repo_interview_workflow',
      status: 'success',
      data: {
        workflow: {
          current_stage: 'follow_up_ready',
          follow_up_count: 1,
        },
        follow_up: {
          mode: 'question_prompt',
          questions: ['你会如何验证这个边界？'],
        },
        session_summary: {
          workflow_completion: {
            answer_coached: true,
            follow_up_completed: false,
            summary_scope: 'summary_without_follow_up_feedback',
          },
        },
      },
    }),
  );

  assert.equal(payload?.data?.workflow?.follow_up_count, 1);
  assert.equal(payload?.data?.follow_up?.mode, 'question_prompt');
  assert.deepEqual(payload?.data?.session_summary?.workflow_completion, {
    answer_coached: true,
    follow_up_completed: false,
    summary_scope: 'summary_without_follow_up_feedback',
  });
});

test('normalizes other questions after follow up without leaking unknown fields', () => {
  const payload = extractGitHubRepoInterviewWorkflowData(
    JSON.stringify({
      tool: 'github_repo_interview_workflow',
      status: 'success',
      data: {
        other_questions: [
          {
            id: 'Q2',
            category: 'testing and automation',
            difficulty: 'senior',
            question: '你会如何评估测试自动化准备度？',
            raw_user_answer: 'SHOULD_NOT_SURFACE',
          },
          {
            id: '',
            question: 'invalid',
          },
        ],
      },
    }),
  );

  assert.deepEqual(payload?.data?.other_questions, [
    {
      id: 'Q2',
      category: 'testing and automation',
      difficulty: 'senior',
      question: '你会如何评估测试自动化准备度？',
    },
  ]);
  assert.doesNotMatch(JSON.stringify(payload), /SHOULD_NOT_SURFACE/);
});

test('normalizes context snapshot and memory candidates without answer text', () => {
  const payload = extractGitHubRepoInterviewWorkflowData(
    JSON.stringify({
      tool: 'github_repo_interview_workflow',
      status: 'success',
      input: {
        user_answer_excerpt: 'SECRET_ANSWER',
      },
      data: {
        context_snapshot: {
          version: 'v1',
          scope: 'request',
          persistence: 'not_persisted',
          current_stage: 'answer_coached',
          active_role: 'answer_coach',
          role_kind: 'llm',
          visible_sources: ['selected_question', 'evidence_details'],
          hidden_sources: ['repo_metadata', 'readme', 'local_files'],
          allowed_evidence_ids: ['manifest:pyproject.toml'],
          allowed_source_paths: ['pyproject.toml'],
          repository_access: 'no_new_repository_access',
          tool_access: 'none',
          persists_user_answer: false,
          user_answer_excerpt: 'SECRET_ANSWER',
          answer_state: {
            has_answer_feedback: true,
            has_follow_up_feedback: false,
            follow_up_mode: 'question_prompt',
            follow_up_count: 0,
          },
          redaction_policy: {
            includes_user_answer: false,
            includes_follow_up_answer: false,
            includes_hidden_source_content: false,
            includes_repo_evidence_text: false,
          },
        },
        memory_candidates: [
          {
            id: 'practice_weakness_tag:missing_evidence',
            type: 'practice_weakness_tag',
            value: 'missing_evidence',
            label: '本轮练习缺少可用 evidence 支撑。',
            source_stage: 'summarize',
            source_fields: ['session_summary.missed_evidence'],
            requires_user_confirmation: true,
            status: 'candidate_only',
            persisted: false,
            privacy: {
              includes_user_answer: false,
              includes_follow_up_answer: false,
              includes_repo_evidence_text: false,
            },
          },
        ],
      },
    }),
  );

  assert.equal(payload?.data?.context_snapshot?.scope, 'request');
  assert.equal(payload?.data?.context_snapshot?.persistence, 'not_persisted');
  assert.equal(payload?.data?.context_snapshot?.persists_user_answer, false);
  assert.deepEqual(payload?.data?.context_snapshot?.allowed_source_paths, [
    'pyproject.toml',
  ]);
  assert.equal(
    payload?.data?.context_snapshot?.answer_state?.has_answer_feedback,
    true,
  );
  assert.equal(
    payload?.data?.context_snapshot?.answer_state?.follow_up_count,
    0,
  );
  assert.equal(
    payload?.data?.context_snapshot?.redaction_policy?.includes_user_answer,
    false,
  );
  assert.deepEqual(payload?.data?.memory_candidates?.[0], {
    id: 'practice_weakness_tag:missing_evidence',
    type: 'practice_weakness_tag',
    value: 'missing_evidence',
    label: '本轮练习缺少可用 evidence 支撑。',
    source_stage: 'summarize',
    source_fields: ['session_summary.missed_evidence'],
    requires_user_confirmation: true,
    status: 'candidate_only',
    persisted: false,
    privacy: {
      includes_user_answer: false,
      includes_follow_up_answer: false,
      includes_repo_evidence_text: false,
    },
  });
  assert.equal(payload?.data?.memory_candidates?.[0]?.status, 'candidate_only');
  assert.equal(payload?.data?.memory_candidates?.[0]?.persisted, false);
  assert.equal(
    payload?.data?.memory_candidates?.[0]?.requires_user_confirmation,
    true,
  );
  assert.equal(
    'user_answer_excerpt' in (payload?.data?.context_snapshot || {}),
    false,
  );
  assert.doesNotMatch(
    JSON.stringify({
      context_snapshot: payload?.data?.context_snapshot,
      memory_candidates: payload?.data?.memory_candidates,
    }),
    /SECRET_ANSWER/,
  );
});

test('normalizes saved memory context and persisted memory candidates', () => {
  const payload = extractGitHubRepoInterviewWorkflowData({
    tool: 'github_repo_interview_workflow',
    status: 'success',
    data: {
      context_snapshot: {
        visible_sources: ['selected_question', 'saved_memories'],
        saved_memory_count: 1,
      },
      saved_memory_context: [
        {
          id: 'm1',
          type: 'language_preference_hint',
          value: 'zh',
          label: '本次请求的候选语言偏好。',
          source_stage: 'coach_answer',
          source_fields: ['input.language'],
          status: 'active',
          persisted: true,
        },
      ],
      memory_candidates: [
        {
          id: 'language_preference_hint:zh',
          type: 'language_preference_hint',
          value: 'zh',
          label: '本次请求的候选语言偏好。',
          source_stage: 'coach_answer',
          source_fields: ['input.language'],
          requires_user_confirmation: true,
          status: 'candidate_only',
          persisted: false,
          privacy: {
            includes_user_answer: false,
            includes_follow_up_answer: false,
            includes_repo_evidence_text: false,
          },
        },
      ],
    },
  });

  assert.equal(payload?.data?.context_snapshot?.saved_memory_count, 1);
  assert.equal(payload?.data?.saved_memory_context?.[0]?.persisted, true);
  assert.equal(payload?.data?.saved_memory_context?.[0]?.status, 'active');
  assert.equal(payload?.data?.memory_candidates?.[0]?.persisted, false);
});

test('normalizes session memory context without raw text fields', () => {
  const payload = extractGitHubRepoInterviewWorkflowData({
    tool: 'github_repo_interview_workflow',
    type: 'github_repo_interview_workflow',
    data: {
      session_memory_context: {
        target_role: 'AI Agent 工程师',
        answered_question_ids: ['Q1'],
        missed_evidence_ids: ['manifest:pyproject.toml'],
        user_answer: 'RAW ANSWER SHOULD NOT SURVIVE',
      },
      session_memory_patch: {
        next_practice_suggestion: '继续练习证据引用。',
      },
    },
  });

  const text = JSON.stringify(payload);
  assert.equal(payload?.data?.session_memory_context?.target_role, 'AI Agent 工程师');
  assert.equal(payload?.data?.session_memory_context?.answered_question_ids?.[0], 'Q1');
  assert.equal(payload?.data?.session_memory_patch?.next_practice_suggestion, '继续练习证据引用。');
  assert.deepEqual(buildGitHubRepoInterviewPrimaryPanelSectionIds(payload), [
    'session_memory',
  ]);
  assert.ok(!text.includes('RAW ANSWER SHOULD NOT SURVIVE'));
});

test('normalizes Chinese intent metadata', () => {
  const payload = extractGitHubRepoInterviewWorkflowData({
    tool: 'github_repo_interview_workflow',
    status: 'success',
    input: {
      preferred_question_category: 'architecture',
    },
    data: {
      workflow: { current_stage: 'question_selected' },
      normalized_intent: {
        coach_style: { raw: '平衡一点', normalized: 'balanced' },
        preferred_question_category: { raw: '架构设计', normalized: 'architecture' },
      },
    },
  });

  assert.equal(payload?.input?.preferred_question_category, 'architecture');
  assert.equal(payload?.data?.normalized_intent?.coach_style?.raw, '平衡一点');
  assert.equal(payload?.data?.normalized_intent?.coach_style?.normalized, 'balanced');
  assert.equal(
    payload?.data?.normalized_intent?.preferred_question_category?.normalized,
    'architecture',
  );
});

test('normalizes answer quality signals without answer text', () => {
  const payload = extractGitHubRepoInterviewWorkflowData({
    tool: 'github_repo_interview_workflow',
    status: 'success',
    data: {
      answer_quality_signals: [
        {
          id: 'score',
          label: '候选人评分',
          status: 'pass',
          severity: 'rating',
          notes: ['SHOULD_NOT_RENDER'],
        },
        {
          id: 'evidence_grounding',
          label: '证据支撑',
          status: 'needs_attention',
          severity: 'warning',
          basis_fields: ['answer_feedback.evidence_missed'],
          evidence_refs: ['manifest:pyproject.toml'],
          notes: ['存在遗漏 evidence。'],
          user_answer_excerpt: 'SECRET_ANSWER',
        },
      ],
    },
  });

  assert.equal(payload?.data?.answer_quality_signals?.length, 1);
  assert.deepEqual(payload?.data?.answer_quality_signals?.[0], {
    id: 'evidence_grounding',
    label: '证据支撑',
    status: 'needs_attention',
    severity: 'warning',
    basis_fields: ['answer_feedback.evidence_missed'],
    evidence_refs: ['manifest:pyproject.toml'],
    notes: ['存在遗漏 evidence。'],
  });
  assert.equal(
    JSON.stringify(payload?.data?.answer_quality_signals).includes('SECRET_ANSWER'),
    false,
  );
  assert.equal(
    JSON.stringify(payload?.data?.answer_quality_signals).includes('SHOULD_NOT_RENDER'),
    false,
  );
});

test('omits empty context snapshot and empty memory candidate list', () => {
  const payload = extractGitHubRepoInterviewWorkflowData(
    JSON.stringify({
      tool: 'github_repo_interview_workflow',
      status: 'success',
      data: {
        context_snapshot: {},
        memory_candidates: [],
        workflow: {
          current_stage: 'question_selected',
        },
      },
    }),
  );

  assert.equal(payload?.data?.context_snapshot, undefined);
  assert.equal(payload?.data?.memory_candidates, undefined);
  assert.equal(payload?.data?.workflow?.current_stage, 'question_selected');
});

test('formats English memory candidate labels for Chinese display', () => {
  assert.equal(
    formatWorkflowDisplayTerm('Candidate language preference from this request.'),
    '本次请求的候选语言偏好。',
  );
});

test('normalizes controlled multi-agent trace without unsafe fields', () => {
  const payload = extractGitHubRepoInterviewWorkflowData({
    tool: 'github_repo_interview_workflow',
    status: 'success',
    data: {
      multi_agent_trace: {
        version: 'v1',
        mode: 'controlled_local_trace',
        scope: 'request',
        orchestrator: {
          name: 'MainAgent',
          status: 'success',
          output_summary: '按固定 stage 调度 GitHub 面试工作流。',
          raw_user_answer: 'SECRET_ANSWER',
        },
        agents: [
          {
            id: 'answer_coach',
            role_name: 'AnswerCoachAgent',
            status: 'success',
            stage: 'coach_answer',
            input_sources: ['selected_question', 'current_user_answer'],
            visible_context: ['selected_question', 'manifest:pyproject.toml'],
            forbidden_scope: ['new_github_reads', 'local_files'],
            uses_repo_evidence: true,
            reads_user_answer: true,
            persists_memory: false,
            output_summary: '基于当前题目和 allowlisted evidence 生成结构化辅导反馈。',
            user_answer_excerpt: 'SECRET_ANSWER',
          },
          {
            id: 'unknown_agent',
            role_name: 'UnknownAgent',
            status: 'success',
            stage: 'coach_answer',
            output_summary: 'SHOULD_NOT_SURFACE',
          },
        ],
        quality_signals: {
          coverage: 'partial',
          evidence_grounding: 'grounded',
          boundary_health: 'clean',
          recommended_next_step: 'revise_with_evidence',
          score: 99,
          pass: true,
        },
      },
    },
  });

  const trace = payload?.data?.multi_agent_trace;

  assert.equal(trace?.version, 'v1');
  assert.equal(trace?.mode, 'controlled_local_trace');
  assert.equal(trace?.orchestrator?.name, 'MainAgent');
  assert.deepEqual(trace?.agents?.map((agent) => agent.id), ['answer_coach']);
  assert.equal(trace?.agents?.[0]?.reads_user_answer, true);
  assert.equal(trace?.agents?.[0]?.persists_memory, false);
  assert.deepEqual(trace?.quality_signals, {
    coverage: 'partial',
    evidence_grounding: 'grounded',
    boundary_health: 'clean',
    recommended_next_step: 'revise_with_evidence',
  });
  assert.doesNotMatch(JSON.stringify(trace), /SECRET_ANSWER|SHOULD_NOT_SURFACE|score|pass/);
});

test('workflow display helpers translate controlled multi-agent trace terms', () => {
  assert.equal(formatWorkflowDisplayTerm('controlled_local_trace'), '受控本地链路');
  assert.equal(formatWorkflowDisplayTerm('repository_analyst'), '仓库分析员');
  assert.equal(formatWorkflowDisplayTerm('interview_question'), '题目设计师');
  assert.equal(formatWorkflowDisplayTerm('answer_coach'), '回答教练');
  assert.equal(formatWorkflowDisplayTerm('quality_reviewer'), '质量审阅员');
  assert.equal(formatWorkflowDisplayTerm('MainAgent'), '主控调度员');
  assert.equal(formatWorkflowDisplayTerm('RepositoryAnalystAgent'), '仓库分析员');
  assert.equal(
    formatWorkflowDisplayTerm('prep_questions_pack.question_generation_summary'),
    '题目生成摘要',
  );
  assert.equal(
    formatWorkflowDisplayTerm('selected_question.evidence_details'),
    '当前题目的证据详情',
  );
  assert.equal(
    formatWorkflowDisplayTerm('repository_analyst.output_summary'),
    '仓库分析摘要',
  );
  assert.equal(formatWorkflowDisplayTerm('context_snapshot'), '上下文快照');
  assert.equal(formatWorkflowDisplayTerm('follow_up'), '追问内容');
  assert.equal(formatWorkflowDisplayTerm('session_summary'), '练习总结');
  assert.equal(formatWorkflowDisplayTerm('warnings'), '警告');
  assert.equal(formatWorkflowDisplayTerm('errors'), '错误');
  assert.equal(formatWorkflowDisplayTerm('revise_with_evidence'), '结合证据修订回答');
});

test('buildMultiAgentTraceFlowLabels produces visible orchestrator to agent chain', () => {
  const payload = extractGitHubRepoInterviewWorkflowData({
    tool: 'github_repo_interview_workflow',
    status: 'success',
    data: {
      multi_agent_trace: {
        mode: 'controlled_local_trace',
        orchestrator: { name: 'MainAgent', status: 'success' },
        agents: [
          { id: 'repository_analyst', role_name: 'RepositoryAnalystAgent', status: 'success' },
          { id: 'interview_question', role_name: 'InterviewQuestionAgent', status: 'success' },
          { id: 'answer_coach', role_name: 'AnswerCoachAgent', status: 'success' },
          { id: 'quality_reviewer', role_name: 'QualityReviewerAgent', status: 'success' },
        ],
      },
    },
  });

  assert.deepEqual(buildMultiAgentTraceFlowLabels(payload?.data?.multi_agent_trace), [
    '主控调度员',
    '仓库分析员',
    '题目设计师',
    '回答教练',
    '质量审阅员',
  ]);
});

test('buildMultiAgentTraceFlowNodes keeps labels and statuses for colored chain', () => {
  const payload = extractGitHubRepoInterviewWorkflowData({
    tool: 'github_repo_interview_workflow',
    status: 'success',
    data: {
      multi_agent_trace: {
        mode: 'controlled_local_trace',
        orchestrator: { name: 'MainAgent', status: 'success' },
        agents: [
          { id: 'repository_analyst', role_name: 'RepositoryAnalystAgent', status: 'success' },
          { id: 'interview_question', role_name: 'InterviewQuestionAgent', status: 'success' },
          { id: 'answer_coach', role_name: 'AnswerCoachAgent', status: 'success' },
          { id: 'quality_reviewer', role_name: 'QualityReviewerAgent', status: 'partial' },
        ],
      },
    },
  });

  assert.deepEqual(buildMultiAgentTraceFlowNodes(payload?.data?.multi_agent_trace), [
    { id: 'main_agent', label: '主控调度员', status: 'success', kind: 'orchestrator' },
    { id: 'repository_analyst', label: '仓库分析员', status: 'success', kind: 'agent' },
    { id: 'interview_question', label: '题目设计师', status: 'success', kind: 'agent' },
    { id: 'answer_coach', label: '回答教练', status: 'success', kind: 'agent' },
    { id: 'quality_reviewer', label: '质量审阅员', status: 'partial', kind: 'agent' },
  ]);
});

test('buildMultiAgentTraceSummary produces compact overview signals', () => {
  const payload = extractGitHubRepoInterviewWorkflowData({
    tool: 'github_repo_interview_workflow',
    status: 'success',
    data: {
      multi_agent_trace: {
        mode: 'controlled_local_trace',
        scope: 'request',
        orchestrator: { name: 'MainAgent', status: 'success' },
        agents: [
          {
            id: 'repository_analyst',
            role_name: 'RepositoryAnalystAgent',
            status: 'success',
            uses_repo_evidence: true,
            reads_user_answer: false,
            persists_memory: false,
          },
          {
            id: 'answer_coach',
            role_name: 'AnswerCoachAgent',
            status: 'success',
            uses_repo_evidence: true,
            reads_user_answer: true,
            persists_memory: false,
          },
          {
            id: 'quality_reviewer',
            role_name: 'QualityReviewerAgent',
            status: 'pending',
            uses_repo_evidence: false,
            reads_user_answer: false,
            persists_memory: false,
          },
        ],
      },
    },
  });

  assert.deepEqual(buildMultiAgentTraceSummary(payload?.data?.multi_agent_trace), {
    agentCount: 3,
    completedAgentCount: 2,
    statusLabel: '2/3 已完成',
    modeLabel: '受控本地链路',
    scopeLabel: '请求级',
    usesRepoEvidence: true,
    readsUserAnswer: true,
    persistsMemory: false,
  });
});

test('buildGitHubRepoInterviewPrimaryPanelSectionIds keeps the main panel focused on the demo path', () => {
  const payload = extractGitHubRepoInterviewWorkflowData({
    tool: 'github_repo_interview_workflow',
    status: 'success',
    next_step: '继续回答下一题',
    warnings: [{ code: 'debug_notice', message: 'debug warning' }],
    data: {
      workflow: {
        current_stage: 'coach_answer',
        active_role: 'answer_coach',
        steps: [{ id: 'prep', label: 'Prep', status: 'success' }],
        roles: [{ id: 'workflow_orchestrator', kind: 'deterministic' }],
      },
      selected_question: { id: 'Q1', question: 'Explain the architecture.' },
      evidence_policy: {
        allowed_evidence_ids: ['src:src/index.ts#snippet-1'],
        repository_access: 'no_new_repository_access',
      },
      evidence_details: [
        { evidence_id: 'src:src/index.ts#snippet-1', source_path: 'src/index.ts' },
      ],
      context_policy: {
        mode: 'request_level_context_policy',
        active_role: 'answer_coach',
      },
      context_snapshot: {
        scope: 'request',
        persistence: 'none',
        active_role: 'answer_coach',
      },
      multi_agent_trace: {
        mode: 'controlled_local_trace',
        orchestrator: { name: 'MainAgent', status: 'success' },
        agents: [
          { id: 'repository_analyst', role_name: 'RepositoryAnalystAgent', status: 'success' },
        ],
      },
      saved_memory_context: [
        {
          type: 'repo',
          value: 'ShitK/miniclawd',
          source_stage: 'prep',
          source_fields: ['repo'],
        },
      ],
      memory_candidates: [
        {
          type: 'repo',
          value: 'ShitK/miniclawd',
          source_stage: 'prep',
          source_fields: ['repo'],
          requires_user_confirmation: true,
          status: 'candidate_only',
          persisted: false,
          privacy: {
            includes_user_answer: false,
            includes_follow_up_answer: false,
            includes_repo_evidence_text: false,
          },
        },
      ],
      answer_quality_signals: [
        {
          id: 'evidence_grounding',
          status: 'supported',
          severity: 'positive',
          basis_fields: ['answer_feedback.grounding_notes'],
        },
      ],
      answer_feedback: { summary: '回答反馈' },
      follow_up: { questions: ['追问'] },
      other_questions: [{ id: 'Q2', question: 'Second question?' }],
      session_summary: { next_practice_suggestion: '继续练习' },
    },
  });

  assert.deepEqual(buildGitHubRepoInterviewPrimaryPanelSectionIds(payload), [
    'workflow_steps',
    'multi_agent_trace',
    'boundary_details',
    'selected_question',
    'answer_feedback',
    'follow_up',
    'other_questions',
    'session_summary',
    'memory_candidates',
    'notices',
    'next_step',
  ]);
});

test('conversation summary payload reuses workflow card sections without becoming workflow eval data', () => {
  const payload = extractGitHubRepoInterviewWorkflowData({
    tool: 'github_repo_interview_conversation_summary',
    type: 'github_repo_interview_conversation_summary',
    status: 'success',
    input: { summary_scope: 'thread_dialogue', language: 'zh' },
    data: {
      summary_kind: 'conversation_summary',
      conversation_turn_count: 3,
      workflow: {
        current_stage: 'summary_ready',
        steps: [
          { id: 'prep', label: 'Prep', status: 'success' },
          { id: 'summary', label: 'Summary', status: 'success' },
        ],
      },
      conversation_summary: {
        overview: '本轮主要围绕 Q4 测试策略回答展开。',
        discussed_questions: ['Q4'],
        agent_help: ['给出测试策略回答框架'],
        open_items: ['继续验证 summary 展示'],
        practice_overview: {
          repository: 'ShitK/miniclawd',
          role: '后端开发工程师',
          difficulty: 'Senior',
          completed_items: ['Q4 测试策略简述'],
          unfinished_items: ['Q4 自动化测试细节'],
        },
        performance_highlights: [
          { title: '测试分层意识', detail: '能区分单测、集成测试和 smoke 测试。' },
        ],
        improvement_areas: [
          {
            weakness: 'CI 运行策略不足',
            evidence: '回答中没有说明不同测试在 CI 中的运行频率。',
            suggestion: '补充 PR 必跑和 nightly 回归的区分。',
          },
        ],
        ability_profile: [
          {
            dimension: '测试策略',
            score: 80,
            rationale: '分层意识清晰，但 CI 和 mock 策略还可补充。',
          },
        ],
        next_practice_steps: ['把 Q4 按完整 senior 面试表达重答一遍。'],
      },
      session_summary: {
        practice_notes: ['本次总结来自 thread 可见对话。'],
        next_practice_suggestion: '继续用 Q4 做一次完整回答。',
        workflow_completion: { summary_scope: 'thread_dialogue' },
      },
    },
  });

  assert.equal(payload?.data?.summary_kind, 'conversation_summary');
  assert.equal(payload?.data?.conversation_turn_count, 3);
  assert.equal(payload?.data?.conversation_summary?.overview, '本轮主要围绕 Q4 测试策略回答展开。');
  assert.deepEqual(payload?.data?.conversation_summary?.discussed_questions, ['Q4']);
  assert.equal(payload?.data?.conversation_summary?.practice_overview?.repository, 'ShitK/miniclawd');
  assert.equal(payload?.data?.conversation_summary?.performance_highlights?.[0]?.title, '测试分层意识');
  assert.equal(payload?.data?.conversation_summary?.improvement_areas?.[0]?.weakness, 'CI 运行策略不足');
  assert.equal(payload?.data?.conversation_summary?.ability_profile?.[0]?.score, 80);
  assert.deepEqual(payload?.data?.conversation_summary?.next_practice_steps, [
    '把 Q4 按完整 senior 面试表达重答一遍。',
  ]);
  assert.deepEqual(buildGitHubRepoInterviewPrimaryPanelSectionIds(payload), [
    'workflow_steps',
    'boundary_details',
    'session_summary',
  ]);
  assert.equal(formatWorkflowDisplayTerm('thread_dialogue'), '本轮对话');
});

test('conversation summary extractor accepts type and kebab-case tool variants', () => {
  const fromType = extractGitHubRepoInterviewWorkflowData({
    type: 'github_repo_interview_conversation_summary',
    status: 'success',
    data: {
      summary_kind: 'conversation_summary',
      session_summary: { next_practice_suggestion: '继续练习' },
    },
  });
  const fromKebab = extractGitHubRepoInterviewWorkflowData({
    tool: 'github-repo-interview-conversation-summary',
    status: 'success',
    data: {
      summary_kind: 'conversation_summary',
      session_summary: { next_practice_suggestion: '继续练习' },
    },
  });

  assert.equal(fromType?.data?.summary_kind, 'conversation_summary');
  assert.equal(fromKebab?.data?.summary_kind, 'conversation_summary');
});

test('formatWorkflowStepStatusLabel clarifies pending follow-up and summary states', () => {
  const payload: GitHubRepoInterviewWorkflowPayload = {
    data: {
      answer_feedback: {
        follow_up_questions: ['你会如何验证这个架构判断？'],
      },
    },
  };

  assert.equal(
    formatWorkflowStepStatusLabel({ id: 'follow_up', status: 'pending' }, payload),
    '已生成，待回答',
  );
  assert.equal(
    formatWorkflowStepStatusLabel({ id: 'follow_up', status: 'pending' }, { data: {} }),
    '未进入',
  );
  assert.equal(
    formatWorkflowStepStatusLabel({ id: 'summary', status: 'pending' }, payload),
    '未生成',
  );
  assert.equal(
    formatWorkflowStepStatusLabel({ id: 'follow_up', status: 'ready' }, payload),
    '已就绪',
  );
  assert.equal(
    formatWorkflowStepStatusLabel({ id: 'follow_up', status: 'success' }, payload),
    '已完成',
  );
});

test('vector memory payload is normalized without embeddings or unsafe text', () => {
  const payload = extractGitHubRepoInterviewWorkflowData({
    tool: 'github_repo_interview_workflow',
    status: 'success',
    data: {
      vector_memory_candidate: {
        id: 'text-memory-candidate:abc',
        type: 'practice_experience_summary',
        text: '本轮重点练习 AgentLoop 架构边界和失败恢复，后续继续补充测试断言与源码符号级证据。',
        content_hash: 'abc',
        source_thread_id: 'thread-1',
        source_stage: 'summarize',
        requires_user_confirmation: true,
        persisted: false,
        status: 'candidate_only',
        provenance: { kind: 'user_confirmed', secret: 'drop' },
        privacy: {
          includes_user_answer: false,
          includes_follow_up_answer: false,
          includes_repo_evidence_text: false,
        },
      },
      vector_memory_context: [
        {
          id: 'memory-1',
          text: '此前练习中已识别 AgentLoop 的消息循环边界，需要补充失败恢复与测试验证。',
          similarity: 1.2,
          persisted: true,
          embedding: [0.1, 0.2],
          provenance: { kind: 'demo_fixture', secret: 'drop' },
        },
        {
          id: 'unsafe',
          text: 'https://example.com/private',
          similarity: 0.9,
          persisted: true,
        },
      ],
      vector_memory_retrieval: {
        status: 'matched',
        model: 'openai/text-embedding-3-small',
        threshold: 0.72,
        candidate_count: 2,
        matched_count: 1,
        applied_count: 1,
        filtered_count: 1,
      },
    },
  });

  assert.equal(payload?.data?.vector_memory_context?.length, 1);
  assert.equal(payload?.data?.vector_memory_context?.[0]?.similarity, 1);
  assert.equal('embedding' in (payload?.data?.vector_memory_context?.[0] || {}), false);
  assert.deepEqual(payload?.data?.vector_memory_context?.[0]?.provenance, {
    kind: 'demo_fixture',
  });
  assert.deepEqual(buildGitHubRepoInterviewPrimaryPanelSectionIds(payload), [
    'vector_memory_candidate',
    'vector_memory_retrieval',
  ]);
});
