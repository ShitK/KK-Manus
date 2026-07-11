'use client';

import { Github } from 'lucide-react';

const TEMPLATES = [
  {
    label: '通用准备',
    value: `这个 GitHub 仓库是我做的项目：<仓库 URL>
请你做我的面试官，根据 README 和代码帮我生成几道面试题。
请用中文展示，优先从架构设计和实现细节开始问。
后面点评我的回答时，请既指出优点，也指出需要补充的地方。`,
  },
  {
    label: '项目亮点',
    value: `这个 GitHub 仓库是我做的项目：<仓库 URL>
请你根据仓库内容帮我准备面试表达，重点关注项目亮点、架构取舍和实现细节。
请用中文展示，点评我的回答时请既指出优点，也指出需要补充的地方。`,
  },
  {
    label: '测试验证',
    value: `这个 GitHub 仓库是我做的项目：<仓库 URL>
请你做我的面试官，重点从测试、自动化和上线前验证角度问我问题。
请用中文展示，并根据仓库证据指出我回答里缺少哪些验证思路。`,
  },
];

export function GitHubInterviewPromptTemplates({
  onSelect,
}: {
  onSelect: (value: string) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2 px-3 pb-2 text-xs text-muted-foreground">
      <span className="inline-flex items-center gap-1">
        <Github className="h-3.5 w-3.5" />
        GitHub 面试模板
      </span>
      {TEMPLATES.map((template) => (
        <button
          key={template.label}
          type="button"
          onClick={() => onSelect(template.value)}
          className="rounded-full border border-border/70 px-2.5 py-1 text-xs text-foreground transition-colors hover:bg-muted"
        >
          {template.label}
        </button>
      ))}
    </div>
  );
}
