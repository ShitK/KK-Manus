export const githubRepoInterviewMemoryKeys = {
  all: ['github-repo-interview-memory'] as const,
  list: () => [...githubRepoInterviewMemoryKeys.all, 'list'] as const,
};
