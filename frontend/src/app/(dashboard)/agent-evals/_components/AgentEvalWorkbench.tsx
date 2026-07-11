'use client';

import { useEffect, useMemo, useState } from 'react';
import { Activity } from 'lucide-react';
import {
  useAgentEvalRunsQuery,
  useAgentRunEvalReportQuery,
} from '@/hooks/react-query/agent-evals/use-agent-evals';
import { sortAgentEvalRuns } from '../_utils';
import { AgentRunEvalReport } from './AgentRunEvalReport';
import { AgentRunList } from './AgentRunList';

export function AgentEvalWorkbench() {
  const runsQuery = useAgentEvalRunsQuery({ limit: 20, status: 'all' });
  const runs = useMemo(
    () => sortAgentEvalRuns(runsQuery.data?.runs || []),
    [runsQuery.data?.runs],
  );
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);

  useEffect(() => {
    if (!selectedRunId && runs[0]) {
      setSelectedRunId(runs[0].agent_run_id);
    }
  }, [runs, selectedRunId]);

  const reportQuery = useAgentRunEvalReportQuery(selectedRunId, !!selectedRunId);

  return (
    <main className="flex h-screen flex-col overflow-hidden bg-background">
      <header className="border-b px-4 py-4 sm:px-6">
        <div className="flex items-center gap-2">
          <Activity className="h-5 w-5 text-primary" />
          <h1 className="text-lg font-semibold">Agent 运行评估</h1>
        </div>
        <p className="mt-1 text-sm text-muted-foreground">
          实时观察 Agent Run 的执行质量、工具稳定性、Workflow 推进和上下文边界。
        </p>
      </header>

      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[360px_minmax(0,1fr)]">
        <AgentRunList
          runs={runs}
          selectedRunId={selectedRunId}
          isLoading={runsQuery.isLoading}
          isFetching={runsQuery.isFetching}
          onSelectRun={setSelectedRunId}
          onRefresh={() => {
            void runsQuery.refetch();
          }}
        />
        <AgentRunEvalReport
          report={reportQuery.data}
          isLoading={reportQuery.isLoading}
          isFetching={reportQuery.isFetching}
          isError={reportQuery.isError}
          onRefresh={() => {
            void reportQuery.refetch();
          }}
        />
      </div>
    </main>
  );
}
