const CATEGORY_LABELS: Record<string, string> = {
  architecture: '架构设计',
  'implementation detail': '实现细节',
  'dependency and packaging': '依赖与工程化',
  'testing and automation': '测试与自动化',
};

const CATEGORY_DESCRIPTIONS: Record<string, string> = {
  architecture: '模块边界、数据流、职责划分',
  'implementation detail': '核心函数、工具调用、执行流程',
  'dependency and packaging': '依赖管理、启动方式、配置文件',
  'testing and automation': '测试覆盖、脚本、CI、验证策略',
};

const DIFFICULTY_LABELS: Record<string, string> = {
  junior: '初级',
  mid: '中级',
  medium: '中级',
  senior: '高级',
  high: '高',
  low: '低',
};

function normalizeCategory(category?: string): string {
  return String(category || '').trim().toLowerCase();
}

function normalizeDifficulty(difficulty?: string): string {
  return String(difficulty || '').trim().toLowerCase();
}

export function getGitHubInterviewCategoryLabel(category?: string): string | undefined {
  const normalized = normalizeCategory(category);
  if (!normalized) return undefined;
  return CATEGORY_LABELS[normalized] || category;
}

export function formatGitHubInterviewCategory(category?: string): string | undefined {
  const normalized = normalizeCategory(category);
  const label = getGitHubInterviewCategoryLabel(category);
  if (!normalized || !label) return undefined;
  return label;
}

export function getGitHubInterviewCategoryDescription(category?: string): string | undefined {
  return CATEGORY_DESCRIPTIONS[normalizeCategory(category)];
}

export function formatGitHubInterviewDifficulty(difficulty?: string): string | undefined {
  const normalized = normalizeDifficulty(difficulty);
  if (!normalized) return undefined;
  return DIFFICULTY_LABELS[normalized] || difficulty;
}
