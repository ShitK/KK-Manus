type NamedToolCall = {
  assistantCall: {
    name?: string;
  };
};

const normalizeToolName = (value?: string) =>
  String(value || '').trim().replace(/_/g, '-').toLowerCase();

const INTERVIEW_TOOL_NAMES = new Set([
  'github-repo-interview-prep',
  'github-repo-interview-workflow',
  'github-repo-interview-conversation-summary',
]);

const HIDDEN_INTERVIEW_TOOL_NAMES = new Set([
  'create-tasks',
  'github-repo-interview-conversation-summary',
]);

export function projectGitHubInterviewToolCalls<T extends NamedToolCall>(
  toolCalls: T[],
): T[] {
  const isInterviewThread = toolCalls.some((toolCall) =>
    INTERVIEW_TOOL_NAMES.has(normalizeToolName(toolCall.assistantCall.name)),
  );
  if (!isInterviewThread) return toolCalls;

  let latestWorkflowIndex = -1;
  toolCalls.forEach((toolCall, index) => {
    if (normalizeToolName(toolCall.assistantCall.name) === 'github-repo-interview-workflow') {
      latestWorkflowIndex = index;
    }
  });

  return toolCalls.filter((toolCall, index) => {
    const toolName = normalizeToolName(toolCall.assistantCall.name);
    if (HIDDEN_INTERVIEW_TOOL_NAMES.has(toolName)) return false;
    if (toolName === 'github-repo-interview-workflow') {
      return index === latestWorkflowIndex;
    }
    return true;
  });
}
