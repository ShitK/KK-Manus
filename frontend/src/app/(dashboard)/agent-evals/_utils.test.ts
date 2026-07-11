import assert from 'node:assert/strict';
import test from 'node:test';
import {
  agentEvalMetricTone,
  agentEvalStatusLabel,
  formatAgentEvalBasis,
  formatAgentEvalTime,
  formatAgentEvalTokenCount,
  sortAgentEvalRuns,
} from './_utils';

test('formats missing eval time as dash', () => {
  assert.equal(formatAgentEvalTime(null), '-');
});

test('maps metric status to known tones', () => {
  assert.equal(agentEvalMetricTone('pass'), 'success');
  assert.equal(agentEvalMetricTone('warn'), 'warning');
  assert.equal(agentEvalMetricTone('fail'), 'danger');
  assert.equal(agentEvalMetricTone('not_applicable'), 'muted');
});

test('labels run statuses in Chinese', () => {
  assert.equal(agentEvalStatusLabel('running'), '运行中');
  assert.equal(agentEvalStatusLabel('completed'), '已完成');
  assert.equal(agentEvalStatusLabel('failed'), '失败');
});

test('labels metric basis fields for display', () => {
  assert.equal(formatAgentEvalBasis('workflow_payload.workflow.stage'), 'Workflow 阶段');
  assert.equal(formatAgentEvalBasis('context_snapshot.redaction_policy'), '上下文脱敏策略');
  assert.equal(formatAgentEvalBasis('messages.content'), '消息内容');
});

test('sorts running runs before completed runs', () => {
  const runs = sortAgentEvalRuns([
    {
      agent_run_id: 'done',
      status: 'completed',
      updated_at: '2026-07-09T10:00:00Z',
    } as any,
    {
      agent_run_id: 'running',
      status: 'running',
      updated_at: '2026-07-09T09:00:00Z',
    } as any,
  ]);

  assert.equal(runs[0].agent_run_id, 'running');
});

test('formats token counts with grouped digits', () => {
  assert.equal(formatAgentEvalTokenCount(0), '0');
  assert.equal(formatAgentEvalTokenCount(1580), '1,580');
});
