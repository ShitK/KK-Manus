import { createQueryKeys } from '@/hooks/use-query';

export const agentEvalKeys = createQueryKeys({
  runs: (limit: number, status: string) =>
    ['agent-evals', 'runs', limit, status] as const,
  report: (agentRunId: string) =>
    ['agent-evals', 'runs', agentRunId, 'report'] as const,
});
