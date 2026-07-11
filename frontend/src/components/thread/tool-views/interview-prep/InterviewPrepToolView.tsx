import type React from "react";
import {
  AlertTriangle,
  BadgeCheck,
  BookOpenCheck,
  CalendarDays,
  CheckCircle,
  Clock,
  HelpCircle,
  Layers3,
  MessageSquareText,
  Sparkles,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";

import { GenericToolView } from "../GenericToolView";
import type { ToolViewProps } from "../types";
import { formatTimestamp, getToolTitle } from "../utils";
import {
  extractInterviewPrepData,
  type InterviewPrepPayload,
} from "./_utils";

type JsonObject = Record<string, unknown>;

function isObject(value: unknown): value is JsonObject {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function asString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

function asObjectArray(value: unknown): JsonObject[] {
  return Array.isArray(value) ? value.filter(isObject) : [];
}

function getInput(payload: InterviewPrepPayload): JsonObject {
  return isObject(payload.input) ? payload.input : {};
}

function hasText(value: string): boolean {
  return value.trim().length > 0;
}

function hasAnyText(...values: Array<string | string[]>): boolean {
  return values.some((value) =>
    Array.isArray(value) ? value.some(hasText) : hasText(value),
  );
}

function compactList(values: string[]): string {
  return values.filter(hasText).join(", ");
}

function hasDisplayedInputMetadata(input: JsonObject): boolean {
  return hasAnyText(
    asString(input.target_role),
    asString(input.project_name),
    asStringArray(input.tech_stack),
    asStringArray(input.focus_areas),
  );
}

function isMeaningfulPhase(phase: JsonObject): boolean {
  return hasAnyText(
    asString(phase.title),
    asStringArray(phase.goals),
    asStringArray(phase.deliverables),
  );
}

function isMeaningfulScheduleDay(day: JsonObject): boolean {
  return hasAnyText(
    asString(day.focus),
    asStringArray(day.tasks),
    asString(day.expected_output),
  );
}

function isMeaningfulTaskSection(section: JsonObject): boolean {
  return hasAnyText(asString(section.title), asStringArray(section.tasks));
}

function isMeaningfulHighlight(highlight: JsonObject): boolean {
  return hasAnyText(
    asString(highlight.title),
    asString(highlight.talk_track),
    asStringArray(highlight.interviewer_followups),
  );
}

function getMeaningfulQuestions(payload: InterviewPrepPayload): JsonObject[] {
  return asObjectArray(payload.questions).filter((question) =>
    hasText(asString(question.question)),
  );
}

function hasStarContent(star: JsonObject): boolean {
  return hasAnyText(
    asString(star.situation),
    asString(star.task),
    asStringArray(star.action),
    asStringArray(star.result),
  );
}

function hasMeaningfulPayload(payload: InterviewPrepPayload): boolean {
  if (payload.type === "interview_plan") {
    return (
      hasAnyText(
        asString(payload.summary),
        asString(payload.schedule_note),
        asString(payload.next_step),
      )
      || asObjectArray(payload.phases).some(isMeaningfulPhase)
      || asObjectArray(payload.daily_schedule).some(isMeaningfulScheduleDay)
      || asObjectArray(payload.suggested_task_sections).some(
        isMeaningfulTaskSection,
      )
    );
  }

  if (payload.type === "project_story") {
    const star = isObject(payload.star) ? payload.star : {};

    return (
      hasStarContent(star)
      || asObjectArray(payload.highlights).some(isMeaningfulHighlight)
      || hasAnyText(
        asString(payload.two_minute_script),
        asStringArray(payload.risk_notes),
      )
    );
  }

  return (
    getMeaningfulQuestions(payload).length > 0
    || hasAnyText(
      asStringArray(payload.practice_order),
      asString(payload.next_step),
    )
  );
}

function StatusBadge({ isSuccess }: { isSuccess: boolean }) {
  return (
    <Badge
      variant="outline"
      className={
        isSuccess
          ? "h-6 gap-1.5 bg-green-50 text-green-700 border-green-200 dark:bg-green-900/20 dark:text-green-400 dark:border-green-800"
          : "h-6 gap-1.5 bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-900/20 dark:text-rose-400 dark:border-rose-800"
      }
    >
      {isSuccess ? (
        <CheckCircle className="h-3.5 w-3.5" />
      ) : (
        <AlertTriangle className="h-3.5 w-3.5" />
      )}
      {isSuccess ? "Prepared" : "Failed"}
    </Badge>
  );
}

function MetadataRow({
  items,
}: {
  items: Array<{ label: string; value: string | number | null | undefined }>;
}) {
  const visibleItems = items.filter((item) =>
    typeof item.value === "number" ? true : hasText(String(item.value ?? "")),
  );

  if (visibleItems.length === 0) {
    return null;
  }

  return (
    <div className="divide-y divide-zinc-100 border-y border-zinc-100 dark:divide-zinc-800 dark:border-zinc-800">
      {visibleItems.map((item) => (
        <div
          key={item.label}
          className="grid gap-1 py-2 text-sm sm:grid-cols-[5.5rem_1fr] sm:gap-3"
        >
          <span className="shrink-0 text-zinc-400 dark:text-zinc-500">
            {item.label}
          </span>
          <span className="min-w-0 break-words text-zinc-700 dark:text-zinc-300">
            {item.value}
          </span>
        </div>
      ))}
    </div>
  );
}

function Section({
  title,
  icon,
  children,
}: {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="border-b border-zinc-200 last:border-b-0 dark:border-zinc-800">
      <div className="flex items-center gap-2.5 bg-zinc-50/80 px-4 py-3 text-sm font-medium text-zinc-700 dark:bg-zinc-900/80 dark:text-zinc-300">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950 [&>svg]:h-5 [&>svg]:w-5">
          {icon}
        </span>
        {title}
      </div>
      <div className="px-4 py-3">{children}</div>
    </section>
  );
}

function BulletList({ items }: { items: string[] }) {
  const visibleItems = items.filter(hasText);

  if (visibleItems.length === 0) {
    return null;
  }

  return (
    <ul className="space-y-1.5">
      {visibleItems.map((item, index) => (
        <li
          key={`${item}-${index}`}
          className="flex gap-2 text-sm leading-relaxed text-zinc-600 dark:text-zinc-300"
        >
          <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-zinc-300 dark:bg-zinc-600" />
          <span className="min-w-0 break-words">{item}</span>
        </li>
      ))}
    </ul>
  );
}

function TextBlock({ children }: { children: string }) {
  if (!hasText(children)) {
    return null;
  }

  return (
    <p className="min-w-0 whitespace-pre-wrap break-words text-sm leading-relaxed text-zinc-600 dark:text-zinc-300">
      {children}
    </p>
  );
}

function InterviewPlanView({ payload }: { payload: InterviewPrepPayload }) {
  const input = getInput(payload);
  const summary = asString(payload.summary);
  const phases = asObjectArray(payload.phases).filter(isMeaningfulPhase);
  const dailySchedule = asObjectArray(payload.daily_schedule).filter(
    isMeaningfulScheduleDay,
  );
  const suggestedTaskSections = asObjectArray(payload.suggested_task_sections).filter(
    isMeaningfulTaskSection,
  );
  const scheduleNote = asString(payload.schedule_note);
  const nextStep = asString(payload.next_step);
  const techStack = asStringArray(input.tech_stack);
  const focusAreas = asStringArray(input.focus_areas);
  const dailyMinutes = asNumber(input.daily_minutes);
  const hasOverview = hasText(summary) || hasDisplayedInputMetadata(input);

  return (
    <div>
      {hasOverview && (
        <Section
          title="Overview"
          icon={<BookOpenCheck className="h-4 w-4 text-sky-500" />}
        >
          <div className="space-y-3">
            <TextBlock>{summary}</TextBlock>
            <MetadataRow
              items={[
                { label: "Role", value: asString(input.target_role) },
                { label: "Project", value: asString(input.project_name) },
                { label: "Prep days", value: asNumber(input.prep_days) },
                { label: "Daily time", value: dailyMinutes ? `${dailyMinutes} min/day` : "" },
                { label: "Stack", value: compactList(techStack) },
                { label: "Focus", value: compactList(focusAreas) },
              ]}
            />
          </div>
        </Section>
      )}

      {phases.length > 0 && (
        <Section
          title="Phases"
          icon={<Layers3 className="h-4 w-4 text-violet-500" />}
        >
          <div className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {phases.map((phase, index) => (
              <div key={index} className="space-y-2 py-3 first:pt-0 last:pb-0">
                <h4 className="min-w-0 break-words text-sm font-medium text-zinc-800 dark:text-zinc-100">
                  {asString(phase.title) || `Phase ${index + 1}`}
                </h4>
                <MetadataRow
                  items={[
                    { label: "Goals", value: compactList(asStringArray(phase.goals)) },
                    {
                      label: "Deliverables",
                      value: compactList(asStringArray(phase.deliverables)),
                    },
                  ]}
                />
              </div>
            ))}
          </div>
        </Section>
      )}

      {dailySchedule.length > 0 && (
        <Section
          title="Daily Schedule"
          icon={<CalendarDays className="h-4 w-4 text-emerald-500" />}
        >
          <div className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {dailySchedule.map((day, index) => {
              const dayNumber = asNumber(day.day);
              const tasks = asStringArray(day.tasks);
              const expectedOutput = asString(day.expected_output);

              return (
                  <div key={index} className="space-y-2.5 py-3 first:pt-0 last:pb-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-xs font-medium uppercase text-zinc-400 dark:text-zinc-500">
                        Day {dayNumber ?? index + 1}
                      </span>
                    {hasText(asString(day.focus)) && (
                      <span className="min-w-0 break-words text-sm font-medium text-zinc-800 dark:text-zinc-100">
                        {asString(day.focus)}
                      </span>
                    )}
                  </div>
                  <BulletList items={tasks} />
                  {hasText(expectedOutput) && (
                    <div className="border-l border-zinc-200 pl-3 text-sm leading-relaxed text-zinc-600 dark:border-zinc-700 dark:text-zinc-300">
                      <span className="font-medium text-zinc-700 dark:text-zinc-200">
                        Output:
                      </span>{" "}
                      <span className="break-words">{expectedOutput}</span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </Section>
      )}

      {hasText(scheduleNote) && (
        <Section title="Schedule Note" icon={<Clock className="h-4 w-4 text-amber-500" />}>
          <TextBlock>{scheduleNote}</TextBlock>
        </Section>
      )}

      {suggestedTaskSections.length > 0 && (
        <Section
          title="Suggested Task Sections"
          icon={<Sparkles className="h-4 w-4 text-fuchsia-500" />}
        >
          <div className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {suggestedTaskSections.map((section, index) => (
              <div key={index} className="space-y-2 py-3 first:pt-0 last:pb-0">
                <h4 className="min-w-0 break-words text-sm font-medium text-zinc-800 dark:text-zinc-100">
                  {asString(section.title) || `Section ${index + 1}`}
                </h4>
                <BulletList items={asStringArray(section.tasks)} />
              </div>
            ))}
          </div>
        </Section>
      )}

      {hasText(nextStep) && (
        <Section title="Next Step" icon={<BadgeCheck className="h-4 w-4 text-teal-500" />}>
          <TextBlock>{nextStep}</TextBlock>
        </Section>
      )}
    </div>
  );
}

function StarRow({
  label,
  value,
}: {
  label: string;
  value: string | string[];
}) {
  const values = Array.isArray(value) ? value : [value];

  if (values.filter(hasText).length === 0) {
    return null;
  }

  return (
    <div className="grid gap-2 border-b border-zinc-100 py-3 last:border-b-0 last:pb-0 dark:border-zinc-800 sm:grid-cols-[7rem_1fr]">
      <div className="text-xs font-medium uppercase text-zinc-400 dark:text-zinc-500">
        {label}
      </div>
      {Array.isArray(value) ? <BulletList items={value} /> : <TextBlock>{value}</TextBlock>}
    </div>
  );
}

function ProjectStoryView({ payload }: { payload: InterviewPrepPayload }) {
  const star = isObject(payload.star) ? payload.star : {};
  const highlights = asObjectArray(payload.highlights).filter(isMeaningfulHighlight);
  const riskNotes = asStringArray(payload.risk_notes).filter(hasText);
  const script = asString(payload.two_minute_script);
  const showStar = hasStarContent(star);

  return (
    <div>
      {showStar && (
        <Section
          title="STAR"
          icon={<BookOpenCheck className="h-4 w-4 text-sky-500" />}
        >
          <div>
            <StarRow label="Situation" value={asString(star.situation)} />
            <StarRow label="Task" value={asString(star.task)} />
            <StarRow label="Action" value={asStringArray(star.action)} />
            <StarRow label="Result" value={asStringArray(star.result)} />
          </div>
        </Section>
      )}

      {highlights.length > 0 && (
        <Section
          title="Highlights"
          icon={<Sparkles className="h-4 w-4 text-fuchsia-500" />}
        >
          <div className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {highlights.map((highlight, index) => (
              <div key={index} className="space-y-2.5 py-3 first:pt-0 last:pb-0">
                <h4 className="min-w-0 break-words text-sm font-medium text-zinc-800 dark:text-zinc-100">
                  {asString(highlight.title) || `Highlight ${index + 1}`}
                </h4>
                <TextBlock>{asString(highlight.talk_track)}</TextBlock>
                {asStringArray(highlight.interviewer_followups).length > 0 && (
                  <div className="space-y-1.5">
                    <div className="text-xs font-medium text-zinc-400 dark:text-zinc-500">
                      Follow-ups
                    </div>
                    <BulletList items={asStringArray(highlight.interviewer_followups)} />
                  </div>
                )}
              </div>
            ))}
          </div>
        </Section>
      )}

      {hasText(script) && (
        <Section
          title="Two Minute Script"
          icon={<MessageSquareText className="h-4 w-4 text-emerald-500" />}
        >
          <TextBlock>{script}</TextBlock>
        </Section>
      )}

      {riskNotes.length > 0 && (
        <Section
          title="Risk Notes"
          icon={<AlertTriangle className="h-4 w-4 text-amber-500" />}
        >
          <BulletList items={riskNotes} />
        </Section>
      )}
    </div>
  );
}

function MockQuestionsView({ payload }: { payload: InterviewPrepPayload }) {
  const input = getInput(payload);
  const questions = getMeaningfulQuestions(payload);
  const practiceOrder = asStringArray(payload.practice_order).filter(hasText);
  const nextStep = asString(payload.next_step);
  const techStack = asStringArray(input.tech_stack);
  const focusAreas = asStringArray(input.focus_areas);
  const showInput = hasDisplayedInputMetadata(input);

  return (
    <div>
      {showInput && (
        <Section
          title="Input"
          icon={<BookOpenCheck className="h-4 w-4 text-sky-500" />}
        >
          <MetadataRow
            items={[
              { label: "Role", value: asString(input.target_role) },
              { label: "Project", value: asString(input.project_name) },
              { label: "Stack", value: compactList(techStack) },
              { label: "Focus", value: compactList(focusAreas) },
            ]}
          />
        </Section>
      )}

      {questions.length > 0 && (
        <Section
          title="Questions"
          icon={<HelpCircle className="h-4 w-4 text-violet-500" />}
        >
          <div className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {questions.map((question, index) => {
              const questionId = asString(question.id) || `q${index + 1}`;
              const answerDirection = asString(question.answer_direction);

              return (
                <div
                  key={`${questionId}-${index}`}
                  className="space-y-2.5 py-3 first:pt-0 last:pb-0"
                >
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="inline-flex h-6 items-center rounded-md border border-sky-200 bg-sky-50 px-2 text-xs font-medium uppercase text-sky-700 dark:border-sky-800 dark:bg-sky-900/20 dark:text-sky-300">
                      {questionId}
                    </span>
                    {hasText(asString(question.category)) && (
                      <span className="inline-flex h-6 max-w-[min(14rem,100%)] items-center truncate rounded-md border border-emerald-200 bg-emerald-50 px-2 text-xs font-normal text-emerald-700 dark:border-emerald-800 dark:bg-emerald-900/20 dark:text-emerald-300">
                        {asString(question.category)}
                      </span>
                    )}
                    {hasText(asString(question.difficulty)) && (
                      <span className="inline-flex h-6 max-w-[min(10rem,100%)] items-center truncate rounded-md border border-emerald-200 bg-emerald-50 px-2 text-xs font-normal text-emerald-700 dark:border-emerald-800 dark:bg-emerald-900/20 dark:text-emerald-300">
                        {asString(question.difficulty)}
                      </span>
                    )}
                  </div>
                  <p className="min-w-0 break-words text-sm font-medium leading-relaxed text-zinc-800 dark:text-zinc-100">
                    {asString(question.question)}
                  </p>
                  {hasText(answerDirection) && (
                    <div className="border-l border-zinc-200 pl-3 text-sm leading-relaxed text-zinc-600 dark:border-zinc-700 dark:text-zinc-300">
                      <span className="font-medium text-zinc-700 dark:text-zinc-200">
                        Direction:
                      </span>{" "}
                      <span className="break-words">{answerDirection}</span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </Section>
      )}

      {practiceOrder.length > 0 && (
        <Section
          title="Practice Order"
          icon={<Layers3 className="h-4 w-4 text-emerald-500" />}
        >
          <p className="min-w-0 break-words text-sm leading-relaxed text-zinc-600 dark:text-zinc-300">
            {practiceOrder.join(" -> ")}
          </p>
        </Section>
      )}

      {hasText(nextStep) && (
        <Section title="Next Step" icon={<BadgeCheck className="h-4 w-4 text-teal-500" />}>
          <TextBlock>{nextStep}</TextBlock>
        </Section>
      )}
    </div>
  );
}

function getFooterLabel(payload: InterviewPrepPayload): string {
  if (payload.type === "interview_plan") {
    const input = getInput(payload);
    const prepDays = asNumber(input.prep_days);
    const dailyMinutes = asNumber(input.daily_minutes);

    if (prepDays && dailyMinutes) {
      return `${prepDays} days · ${dailyMinutes} min/day`;
    }

    return `${prepDays || asObjectArray(payload.daily_schedule).filter(
      isMeaningfulScheduleDay,
    ).length} days`;
  }

  if (payload.type === "project_story") {
    return `${asObjectArray(payload.highlights).filter(isMeaningfulHighlight).length} highlights`;
  }

  return `${getMeaningfulQuestions(payload).length} questions`;
}

function getPayloadView(payload: InterviewPrepPayload) {
  if (payload.type === "interview_plan") {
    return <InterviewPlanView payload={payload} />;
  }

  if (payload.type === "project_story") {
    return <ProjectStoryView payload={payload} />;
  }

  return <MockQuestionsView payload={payload} />;
}

export const InterviewPrepToolView: React.FC<ToolViewProps> = ({
  name = "interview-prep",
  assistantContent,
  toolContent,
  assistantTimestamp,
  toolTimestamp,
  isSuccess = true,
  isStreaming = false,
  ...props
}) => {
  const data = extractInterviewPrepData(assistantContent, toolContent);
  const hasMeaningfulData = data ? hasMeaningfulPayload(data) : false;

  if (!isStreaming && !hasMeaningfulData) {
    return (
      <GenericToolView
        name={name}
        assistantContent={assistantContent}
        toolContent={toolContent}
        assistantTimestamp={assistantTimestamp}
        toolTimestamp={toolTimestamp}
        isSuccess={isSuccess}
        isStreaming={isStreaming}
        {...props}
      />
    );
  }

  const toolTitle = getToolTitle(name);

  return (
    <Card className="gap-0 flex border shadow-none border-t border-b-0 border-x-0 p-0 rounded-none flex-col h-full overflow-hidden bg-card">
      <CardHeader className="flex h-16 items-center border-b bg-zinc-50/80 px-4 py-0 !pb-0 backdrop-blur-sm dark:bg-zinc-900/80">
        <div className="relative flex h-full w-full min-w-0 items-center justify-center">
          <div className="absolute left-0 flex items-center">
            <div className="relative flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-sky-500/20 bg-gradient-to-br from-sky-500/20 to-emerald-500/10">
              <BookOpenCheck className="h-6 w-6 text-sky-500 dark:text-sky-400" />
            </div>
          </div>

          <CardTitle className="mx-14 min-w-0 truncate text-center text-base font-medium text-zinc-900 dark:text-zinc-100">
            {toolTitle}
          </CardTitle>

          <div className="absolute right-0 flex items-center">
            {!isStreaming && <StatusBadge isSuccess={isSuccess} />}
          </div>
        </div>
      </CardHeader>

      <CardContent className="relative h-full flex-1 overflow-hidden p-0">
        {isStreaming && (!data || !hasMeaningfulData) ? (
          <div className="flex h-full flex-col items-center justify-center bg-gradient-to-b from-white to-zinc-50 px-6 py-12 dark:from-zinc-950 dark:to-zinc-900">
            <div className="mb-6 flex h-20 w-20 items-center justify-center rounded-full bg-gradient-to-b from-zinc-100 to-zinc-50 shadow-inner dark:from-zinc-800/40 dark:to-zinc-900/60">
              <Clock className="h-10 w-10 animate-spin text-sky-500 dark:text-sky-400" />
            </div>
            <h3 className="mb-2 text-xl font-semibold text-zinc-900 dark:text-zinc-100">
              Preparing Interview Prep
            </h3>
          </div>
        ) : data && hasMeaningfulData ? (
          <ScrollArea className="h-full w-full">{getPayloadView(data)}</ScrollArea>
        ) : null}
      </CardContent>

      <div className="flex h-10 items-center justify-between gap-4 border-t border-zinc-200 bg-gradient-to-r from-zinc-50/90 to-zinc-100/90 px-4 py-2 backdrop-blur-sm dark:border-zinc-800 dark:from-zinc-900/90 dark:to-zinc-800/90">
        <div className="flex h-full min-w-0 items-center gap-2 text-sm text-zinc-500 dark:text-zinc-400">
          {data && hasMeaningfulData && !isStreaming && (
            <Badge variant="outline" className="h-6 gap-1 bg-zinc-50 py-0.5 dark:bg-zinc-900">
              <BookOpenCheck className="h-3 w-3" />
              {getFooterLabel(data)}
            </Badge>
          )}
        </div>

        <div className="flex min-w-0 items-center gap-2 truncate text-xs text-zinc-500 dark:text-zinc-400">
          <Clock className="h-3.5 w-3.5 shrink-0" />
          <span className="truncate">
            {toolTimestamp && !isStreaming
              ? formatTimestamp(toolTimestamp)
              : assistantTimestamp
                ? formatTimestamp(assistantTimestamp)
                : ""}
          </span>
        </div>
      </div>
    </Card>
  );
};
