import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import { createMutationHook, createQueryHook } from '@/hooks/use-query';
import {
  confirmGitHubRepoInterviewVectorMemory,
  deleteGitHubRepoInterviewVectorMemory,
  getGitHubRepoInterviewVectorMemories,
  type GitHubRepoInterviewVectorMemory,
  type GitHubRepoInterviewVectorMemoryCandidate,
} from '@/lib/api';

import { githubRepoInterviewVectorMemoryKeys } from './keys';

export function useGitHubRepoInterviewVectorMemories() {
  return createQueryHook<GitHubRepoInterviewVectorMemory[]>(
    githubRepoInterviewVectorMemoryKeys.list(),
    getGitHubRepoInterviewVectorMemories,
    { staleTime: 2 * 60 * 1000, refetchOnWindowFocus: false },
  )();
}

export function useConfirmGitHubRepoInterviewVectorMemory() {
  const queryClient = useQueryClient();
  return createMutationHook<
    GitHubRepoInterviewVectorMemory,
    { candidate: GitHubRepoInterviewVectorMemoryCandidate; source_thread_id: string }
  >(confirmGitHubRepoInterviewVectorMemory, {
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: githubRepoInterviewVectorMemoryKeys.all });
      toast.success('长期文本记忆已保存');
    },
  })();
}

export function useDeleteGitHubRepoInterviewVectorMemory() {
  const queryClient = useQueryClient();
  return createMutationHook<GitHubRepoInterviewVectorMemory, string>(
    deleteGitHubRepoInterviewVectorMemory,
    {
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: githubRepoInterviewVectorMemoryKeys.all });
        toast.success('长期文本记忆已删除');
      },
    },
  )();
}
