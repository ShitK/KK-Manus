import { createQueryHook } from '@/hooks/use-query';
import { getAgentEvalRuns, getAgentRunEvalReport } from '@/lib/api';
import { agentEvalKeys } from './keys';

export const useAgentEvalRunsQuery = (
  params: { limit?: number; status?: string } = {},
) => {
  const limit = params.limit ?? 20;
  const status = params.status ?? 'all';

  return createQueryHook(
    agentEvalKeys.runs(limit, status),
    () => getAgentEvalRuns({ limit, status }),
    {
      retry: 1,
      refetchInterval: 2000,
      refetchIntervalInBackground: false,
      refetchOnMount: 'always',
      refetchOnWindowFocus: true,
      staleTime: 0,
    },
  )();
};

export const useAgentRunEvalReportQuery = (
  agentRunId: string | null,
  enabled = true,
) =>
  createQueryHook(
    agentEvalKeys.report(agentRunId || 'none'),
    () => getAgentRunEvalReport(agentRunId as string),
    {
      enabled: enabled && !!agentRunId,
      retry: 1,
      refetchInterval: (query) => {
        const status = query.state.data?.run?.status;
        return status === 'running' ? 2000 : false;
      },
      refetchIntervalInBackground: false,
      refetchOnMount: 'always',
      refetchOnWindowFocus: true,
      staleTime: 0,
    },
  )();
