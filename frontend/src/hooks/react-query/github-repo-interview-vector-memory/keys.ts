export const githubRepoInterviewVectorMemoryKeys = {
  all: ['github-repo-interview-vector-memory'] as const,
  list: () => [...githubRepoInterviewVectorMemoryKeys.all, 'list'] as const,
};
