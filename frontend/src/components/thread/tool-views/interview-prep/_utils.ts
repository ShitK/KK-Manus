type JsonObject = Record<string, unknown>;

export type InterviewPrepPayload =
  | InterviewPlanPayload
  | ProjectStoryPayload
  | MockQuestionsPayload;

export interface InterviewPlanPayload {
  tool: "interview_prep";
  type: "interview_plan";
  input?: JsonObject;
  daily_schedule?: unknown[];
  suggested_task_sections?: unknown[];
  schedule_note?: string;
  [key: string]: unknown;
}

export interface ProjectStoryPayload {
  tool: "interview_prep";
  type: "project_story";
  input?: JsonObject;
  star?: JsonObject;
  two_minute_script?: string;
  highlights?: unknown[];
  [key: string]: unknown;
}

export interface MockQuestionsPayload {
  tool: "interview_prep";
  type: "mock_questions";
  input?: JsonObject;
  questions?: unknown[];
  [key: string]: unknown;
}

const validTypes = new Set([
  "interview_plan",
  "project_story",
  "mock_questions",
]);

function parseJsonSafely(content: unknown): unknown {
  if (typeof content !== "string") {
    return content;
  }

  try {
    return JSON.parse(content);
  } catch {
    return null;
  }
}

function isJsonObject(value: unknown): value is JsonObject {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function isInterviewPrepPayload(value: unknown): value is InterviewPrepPayload {
  if (!isJsonObject(value)) {
    return false;
  }

  return value.tool === "interview_prep"
    && typeof value.type === "string"
    && validTypes.has(value.type);
}

function extractFromContent(content: unknown): InterviewPrepPayload | null {
  const parsedContent = parseJsonSafely(content);

  if (!isJsonObject(parsedContent)) {
    return null;
  }

  if (isInterviewPrepPayload(parsedContent)) {
    return parsedContent;
  }

  const nestedCandidates = [
    parsedContent.result,
    isJsonObject(parsedContent.result) ? parsedContent.result.output : undefined,
    parsedContent.output,
    parsedContent.content,
    isJsonObject(parsedContent.tool_execution)
      && isJsonObject(parsedContent.tool_execution.result)
      ? parsedContent.tool_execution.result.output
      : undefined,
  ];

  for (const candidate of nestedCandidates) {
    const payload = extractFromContent(candidate);
    if (payload) {
      return payload;
    }
  }

  return null;
}

export function extractInterviewPrepData(
  assistantContent?: string,
  toolContent?: string,
): InterviewPrepPayload | null {
  return extractFromContent(toolContent) || extractFromContent(assistantContent);
}
