import json
from typing import Any, Dict, List, Optional

from agentpress.tool import Tool, ToolResult


class InterviewPrepTool(Tool):
    """Create structured interview-preparation artifacts for project-based technical interviews.

    Use this tool when the user asks for interview preparation plans, project story framing,
    or mock interview questions. This tool is pure backend logic: it does not browse the web,
    execute shell commands, read or write local files, or persist data.
    """

    def __init__(self):
        super().__init__()

    def _success_json(self, payload: Dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, output=json.dumps(payload, ensure_ascii=False, indent=2))

    def _validate_language(self, language: str) -> Optional[ToolResult]:
        if language not in {"zh", "en"}:
            return self.fail_response("language must be one of: zh, en")
        return None

    def _clean_text(self, value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    def _clean_list(self, values: Optional[List[str]]) -> List[str]:
        if not values:
            return []
        if isinstance(values, str):
            value = values.strip()
            return [value] if value else []
        try:
            iterator = iter(values)
        except TypeError:
            value = str(values).strip()
            return [value] if value else []
        return [str(value).strip() for value in iterator if str(value).strip()]

    def _require_text(self, field_name: str, value: Any) -> Optional[ToolResult]:
        if not self._clean_text(value):
            return self.fail_response(f"{field_name} is required")
        return None

    def _validate_int_range(self, field_name: str, value: Any, min_value: int, max_value: int) -> Optional[ToolResult]:
        if type(value) is not int:
            return self.fail_response(f"{field_name} must be an integer between {min_value} and {max_value}")
        if value < min_value or value > max_value:
            return self.fail_response(f"{field_name} must be between {min_value} and {max_value}")
        return None

    async def create_interview_plan(
        self,
        target_role: str,
        prep_days: int,
        project_name: str = "KKManus",
        tech_stack: Optional[List[str]] = None,
        focus_areas: Optional[List[str]] = None,
        daily_minutes: int = 90,
        language: str = "zh",
        include_task_suggestions: bool = True,
    ) -> ToolResult:
        """Create a structured interview preparation plan.

        Args:
            target_role: Target interview role, such as "AI Agent backend engineer".
            prep_days: Number of preparation days, from 1 to 90.
            project_name: Main project to use in interview stories.
            tech_stack: Key technologies to emphasize.
            focus_areas: Topics the user wants to practice.
            daily_minutes: Minutes available per day, from 15 to 480.
            language: Output language, "zh" or "en".
            include_task_suggestions: Whether to include task sections that can be passed to create_tasks.

        Returns:
            ToolResult containing JSON with phases, daily_schedule, suggested_task_sections, and next_step.
        """
        validation_error = self._require_text("target_role", target_role)
        if validation_error:
            return validation_error
        language_error = self._validate_language(language)
        if language_error:
            return language_error
        prep_days_error = self._validate_int_range("prep_days", prep_days, 1, 90)
        if prep_days_error:
            return prep_days_error
        daily_minutes_error = self._validate_int_range("daily_minutes", daily_minutes, 15, 480)
        if daily_minutes_error:
            return daily_minutes_error

        target_role_text = self._clean_text(target_role)
        project_name_text = self._clean_text(project_name) or "KKManus"
        stack = self._clean_list(tech_stack)
        areas = self._clean_list(focus_areas) or ["项目叙事", "系统架构", "工具系统", "排障复盘"]
        plan_days = min(prep_days, 14)
        daily_schedule = []
        for day in range(1, plan_days + 1):
            focus = areas[(day - 1) % len(areas)]
            daily_schedule.append({
                "day": day,
                "focus": focus,
                "tasks": [
                    f"围绕 {project_name_text} 准备 {focus} 的 2 分钟讲解",
                    f"整理 2 个和 {focus} 相关的面试追问",
                ],
                "expected_output": f"一段可口述的 {focus} 回答稿",
            })

        payload: Dict[str, Any] = {
            "tool": "interview_prep",
            "type": "interview_plan",
            "version": "v1",
            "input": {
                "target_role": target_role_text,
                "prep_days": prep_days,
                "project_name": project_name_text,
                "tech_stack": stack,
                "focus_areas": areas,
                "daily_minutes": daily_minutes,
                "language": language,
            },
            "summary": f"{prep_days} 天 {target_role_text} 面试准备计划，围绕 {project_name_text} 的项目叙事、架构边界和技术追问展开。",
            "phases": [
                {
                    "title": "项目叙事",
                    "goals": ["讲清楚项目来源、目标和个人贡献", "准备 STAR 结构回答"],
                    "deliverables": ["项目介绍稿", "STAR 项目故事"],
                },
                {
                    "title": "技术深挖",
                    "goals": ["讲清楚关键链路和边界", "准备可验证的工程取舍"],
                    "deliverables": ["架构讲解提纲", "高频追问答案"],
                },
            ],
            "daily_schedule": daily_schedule,
            "next_step": "先生成项目故事，再生成模拟面试题进行口述练习。",
        }
        if prep_days > plan_days:
            payload["schedule_note"] = f"daily_schedule 先展示前 {plan_days} 天；完整准备周期仍按 {prep_days} 天规划，可继续按同一节奏滚动执行。"
        if include_task_suggestions:
            payload["suggested_task_sections"] = [
                {
                    "title": "Interview Prep",
                    "tasks": [
                        f"准备 {project_name_text} 项目介绍",
                        "准备 STAR 项目故事",
                        "练习 Agent run 生命周期讲解",
                    ],
                }
            ]

        return self._success_json(payload)

    async def generate_project_story(
        self,
        project_name: str,
        project_summary: str,
        tech_stack: Optional[List[str]] = None,
        personal_contribution: str = "",
        challenges: Optional[List[str]] = None,
        target_role: str = "",
        language: str = "zh",
        tone: str = "concise",
    ) -> ToolResult:
        """Generate a STAR-format project story and interview talk track.

        Args:
            project_name: Project name.
            project_summary: Short project background.
            tech_stack: Technologies used in the project.
            personal_contribution: User's contribution.
            challenges: Technical or product challenges.
            target_role: Target interview role.
            language: Output language, "zh" or "en".
            tone: One of "concise", "technical", or "storytelling".

        Returns:
            ToolResult containing JSON with star, highlights, two_minute_script, and risk_notes.
        """
        for field_name, value in {"project_name": project_name, "project_summary": project_summary}.items():
            validation_error = self._require_text(field_name, value)
            if validation_error:
                return validation_error
        language_error = self._validate_language(language)
        if language_error:
            return language_error
        if tone not in {"concise", "technical", "storytelling"}:
            return self.fail_response("tone must be one of: concise, technical, storytelling")

        project_name_text = self._clean_text(project_name)
        project_summary_text = self._clean_text(project_summary)
        stack = self._clean_list(tech_stack)
        challenge_list = self._clean_list(challenges)
        contribution = self._clean_text(personal_contribution) or "梳理项目边界、稳定核心 demo、补充可解释化能力"
        target_role_text = self._clean_text(target_role)

        payload = {
            "tool": "interview_prep",
            "type": "project_story",
            "version": "v1",
            "input": {
                "project_name": project_name_text,
                "target_role": target_role_text,
                "tech_stack": stack,
                "tone": tone,
                "language": language,
            },
            "star": {
                "situation": project_summary_text,
                "task": f"把 {project_name_text} 打磨成面试中可稳定演示、可解释、可扩展的项目。",
                "action": [contribution] + challenge_list[:3],
                "result": ["核心 demo 链路稳定", "项目边界和后续扩展路线更清晰"],
            },
            "highlights": [
                {
                    "title": "工程化改造",
                    "talk_track": f"{project_name_text} 的重点不是包装成从零原创，而是基于现有课程项目做可验证的工程化改造。",
                    "interviewer_followups": ["你具体改了哪些稳定性问题？", "你如何证明这些改动有效？"],
                },
                {
                    "title": "可解释工具链路",
                    "talk_track": "我会先讲用户消息如何进入 Agent run，再讲工具注册、执行、消息落库和前端展示。",
                    "interviewer_followups": ["工具调用结果怎么回到前端？", "messages 和 events 的边界是什么？"],
                },
            ],
            "two_minute_script": f"我在 {project_name_text} 中主要做的是 {contribution}。项目背景是：{project_summary_text}。技术上我会重点讲 {', '.join(stack) if stack else '前后端、Agent Core 和工具系统'}。",
            "risk_notes": ["不要声称项目完全从零原创。", "不要声称高风险 sandbox/browser/files 工具已经恢复。"],
        }
        return self._success_json(payload)

    async def generate_mock_questions(
        self,
        target_role: str,
        project_name: str = "KKManus",
        tech_stack: Optional[List[str]] = None,
        difficulty: str = "mid",
        question_count: int = 8,
        focus_areas: Optional[List[str]] = None,
        include_answer_guidance: bool = True,
        language: str = "zh",
    ) -> ToolResult:
        """Generate project-aware mock interview questions.

        Args:
            target_role: Target interview role.
            project_name: Project name to anchor questions.
            tech_stack: Technologies to cover.
            difficulty: One of "junior", "mid", or "senior".
            question_count: Number of questions to generate, from 1 to 20.
            focus_areas: Specific areas to emphasize.
            include_answer_guidance: Whether to include suggested answer direction.
            language: Output language, "zh" or "en".

        Returns:
            ToolResult containing JSON with questions, practice_order, and next_step.
        """
        validation_error = self._require_text("target_role", target_role)
        if validation_error:
            return validation_error
        language_error = self._validate_language(language)
        if language_error:
            return language_error
        if difficulty not in {"junior", "mid", "senior"}:
            return self.fail_response("difficulty must be one of: junior, mid, senior")
        question_count_error = self._validate_int_range("question_count", question_count, 1, 20)
        if question_count_error:
            return question_count_error

        target_role_text = self._clean_text(target_role)
        project_name_text = self._clean_text(project_name) or "KKManus"
        stack = self._clean_list(tech_stack)
        areas = self._clean_list(focus_areas) or ["项目背景", "架构边界", "工具系统", "稳定性排障", "安全边界"]
        questions = []
        for index in range(question_count):
            area = areas[index % len(areas)]
            question = {
                "id": f"q{index + 1}",
                "question": f"你会如何结合 {project_name_text} 解释 {area}？",
                "category": area,
                "difficulty": difficulty,
                "assesses": [area, "表达结构", "工程取舍"],
            }
            if include_answer_guidance:
                question["answer_direction"] = f"先给结论，再结合 {project_name_text} 的实际链路说明你做了什么、为什么这么做、如何验证。"
            questions.append(question)

        payload = {
            "tool": "interview_prep",
            "type": "mock_questions",
            "version": "v1",
            "input": {
                "target_role": target_role_text,
                "project_name": project_name_text,
                "tech_stack": stack,
                "difficulty": difficulty,
                "question_count": question_count,
                "focus_areas": areas,
                "language": language,
            },
            "questions": questions,
            "practice_order": [question["id"] for question in questions],
            "next_step": "任选 3 题先口述回答，再让 KKManus 帮你改写表达。",
        }
        return self._success_json(payload)
