import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import { createMutationHook, createQueryHook } from '@/hooks/use-query';
import {
  confirmGitHubRepoInterviewMemory,
  deleteGitHubRepoInterviewMemory,
  getGitHubRepoInterviewMemories,
  type GitHubRepoInterviewMemory,
  type GitHubRepoInterviewMemoryCandidatePayload,
} from '@/lib/api';
import { handleApiError } from '@/lib/error-handler';

import { githubRepoInterviewMemoryKeys } from './keys';

export function useGitHubRepoInterviewMemories() {
  return createQueryHook<GitHubRepoInterviewMemory[]>(
    githubRepoInterviewMemoryKeys.list(),
    getGitHubRepoInterviewMemories,
    {
      staleTime: 2 * 60 * 1000,
      refetchOnWindowFocus: false,
    },
  )();
}

export function useConfirmGitHubRepoInterviewMemory() {
  const queryClient = useQueryClient();
  return createMutationHook<
    GitHubRepoInterviewMemory,
    GitHubRepoInterviewMemoryCandidatePayload
  >(confirmGitHubRepoInterviewMemory, {
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: githubRepoInterviewMemoryKeys.all });
      toast.success('记忆候选已保存');
    },
    onError: (error) => {
      handleApiError(error, {
        operation: 'save GitHub interview memory',
        resource: 'memory candidate',
      });
    },
  })();
}

export function useDeleteGitHubRepoInterviewMemory() {
  const queryClient = useQueryClient();
  return createMutationHook<GitHubRepoInterviewMemory, string>(
    deleteGitHubRepoInterviewMemory,
    {
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: githubRepoInterviewMemoryKeys.all });
        toast.success('已删除这条记忆');
      },
      onError: (error) => {
        handleApiError(error, {
          operation: 'delete GitHub interview memory',
          resource: 'saved memory',
        });
      },
    },
  )();
}
