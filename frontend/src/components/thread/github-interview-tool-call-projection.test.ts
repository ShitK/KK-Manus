import assert from 'node:assert/strict';
import test from 'node:test';

import { projectGitHubInterviewToolCalls } from './github-interview-tool-call-projection';

test('keeps prep and only the latest workflow in a GitHub interview thread', () => {
  const calls = [
    { assistantCall: { name: 'github-repo-interview-prep' } },
    { assistantCall: { name: 'create-tasks' } },
    { assistantCall: { name: 'github-repo-interview-workflow' } },
    { assistantCall: { name: 'create_tasks' } },
    { assistantCall: { name: 'github_repo_interview_workflow' } },
    { assistantCall: { name: 'github-repo-interview-conversation-summary' } },
  ];

  assert.deepEqual(
    projectGitHubInterviewToolCalls(calls).map((call) => call.assistantCall.name),
    ['github-repo-interview-prep', 'github_repo_interview_workflow'],
  );
});

test('keeps task panels outside a GitHub interview thread', () => {
  const calls = [
    { assistantCall: { name: 'create-tasks' } },
    { assistantCall: { name: 'create_tasks' } },
  ];

  assert.deepEqual(projectGitHubInterviewToolCalls(calls), calls);
});

test('does not enable projection for an unrelated similarly named tool', () => {
  const calls = [
    { assistantCall: { name: 'github-repo-interview-export' } },
    { assistantCall: { name: 'create-tasks' } },
  ];

  assert.deepEqual(projectGitHubInterviewToolCalls(calls), calls);
});
