from typing import Any, Dict, List


Question = Dict[str, Any]
MAX_QUESTION_CHARS = 300
MAX_DIRECTION_CHARS = 500
MAX_DETAIL_SUMMARY_CHARS = 300
MAX_WHY_CHARS = 240
MAX_EVIDENCE_DETAILS = 3
CONFIDENCE_VALUES = {"low", "medium", "high"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _truncate(value: str, limit: int) -> str:
    text = _text(value)
    return text[:limit]


def _items(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _source_paths_from_refs(context_pack: Dict[str, Any], refs: List[str]) -> List[str]:
    evidence_map = _items(context_pack.get("evidence_map"))
    paths = []
    for ref in refs:
        if ref.startswith("manifest:"):
            path = ref.removeprefix("manifest:")
            if path and _manifest_by_path(context_pack, path) and path not in paths:
                paths.append(path)
            continue
        for evidence in evidence_map:
            if isinstance(evidence, dict) and evidence.get("id") == ref:
                if _text(evidence.get("source_type")) != "source":
                    continue
                path = _text(evidence.get("source_path"))
                if path and path not in paths:
                    paths.append(path)
    return paths


def _confidence(value: Any, fallback: str = "medium") -> str:
    text = _text(value)
    return text if text in CONFIDENCE_VALUES else fallback


def _confidence_cap(value: Any, cap: str) -> str:
    order = {"low": 0, "medium": 1, "high": 2}
    confidence = _confidence(value, cap)
    return confidence if order[confidence] <= order[cap] else cap


def _fallback_paths(context_pack: Dict[str, Any]) -> List[str]:
    paths = []
    for manifest in _items(context_pack.get("manifest_summary")):
        if isinstance(manifest, dict) and _text(manifest.get("path")):
            paths.append(_text(manifest.get("path")))
    directory = context_pack.get("directory_summary") or {}
    if isinstance(directory, dict):
        for path in _items(directory.get("notable_paths")):
            text = _text(path)
            if text and text not in paths:
                paths.append(text)
    return paths[:3] or ["README"]


def _first_evidence_refs(context_pack: Dict[str, Any], limit: int = 2) -> List[str]:
    refs = []
    for evidence in _items(context_pack.get("evidence_map")):
        if isinstance(evidence, dict):
            ref = _text(evidence.get("id"))
            if ref and ref not in refs:
                refs.append(ref)
        if len(refs) >= limit:
            break
    return refs


def _manifest_paths(context_pack: Dict[str, Any]) -> List[str]:
    paths = []
    for manifest in _items(context_pack.get("manifest_summary")):
        if isinstance(manifest, dict):
            path = _text(manifest.get("path"))
            if path:
                paths.append(path)
    return paths


def _manifest_refs(context_pack: Dict[str, Any]) -> List[str]:
    return [f"manifest:{path}" for path in _manifest_paths(context_pack)]


def _manifest_by_path(context_pack: Dict[str, Any], path: str) -> Dict[str, Any]:
    for manifest in _items(context_pack.get("manifest_summary")):
        if isinstance(manifest, dict) and _text(manifest.get("path")) == path:
            return manifest
    return {}


def _file_summary_by_path(context_pack: Dict[str, Any], path: str) -> Dict[str, Any]:
    for file_summary in _items(context_pack.get("file_summaries")):
        if isinstance(file_summary, dict) and _text(file_summary.get("path")) == path:
            return file_summary
    return {}


def _source_evidence_by_id(
    context_pack: Dict[str, Any],
    evidence_id: str,
) -> Dict[str, Any]:
    for evidence in _items(context_pack.get("evidence_map")):
        if not isinstance(evidence, dict) or _text(evidence.get("id")) != evidence_id:
            continue
        if _text(evidence.get("source_type")) != "source":
            return {}
        source_path = _text(evidence.get("source_path"))
        return evidence if source_path else {}
    return {}


def _snippet_for_evidence(context_pack: Dict[str, Any], evidence_id: str, source_path: str) -> str:
    evidence = _source_evidence_by_id(context_pack, evidence_id)
    snippet = _text(evidence.get("snippet"))
    if snippet:
        return _truncate(snippet, MAX_DETAIL_SUMMARY_CHARS)

    file_summary = _file_summary_by_path(context_pack, source_path)
    for snippet_item in _items(file_summary.get("evidence_snippets")):
        if isinstance(snippet_item, dict) and _text(snippet_item.get("id")) == evidence_id:
            text = _text(snippet_item.get("text"))
            if text:
                return _truncate(text, MAX_DETAIL_SUMMARY_CHARS)
    return ""


def _manifest_summary_text(manifest: Dict[str, Any]) -> str:
    parts = []
    ecosystem = _text(manifest.get("ecosystem"))
    summary = _text(manifest.get("summary"))
    dependencies = [
        _text(item) for item in _items(manifest.get("dependencies")) if _text(item)
    ]
    scripts = [
        _text(item)
        for item in _items(manifest.get("scripts_or_entrypoints"))
        if _text(item)
    ]
    if ecosystem:
        parts.append(f"{ecosystem} manifest")
    if summary:
        parts.append(summary)
    if dependencies:
        parts.append(f"dependencies: {', '.join(dependencies[:5])}")
    if scripts:
        parts.append(f"entrypoints/scripts: {', '.join(scripts[:5])}")
    return _truncate(". ".join(parts), MAX_DETAIL_SUMMARY_CHARS)


def _detail_why(evidence_type: str, category: str, language: str) -> str:
    is_en = language == "en"
    normalized_category = _text(category)
    if evidence_type == "manifest":
        text = (
            "Helps explain packaging, dependencies, and entrypoint evidence for this question."
            if is_en
            else "用于解释 packaging、dependency、entrypoint 等工程化证据如何支撑这道题。"
        )
    elif evidence_type == "source":
        text = (
            "Grounds the answer in selected source evidence rather than a generic repository claim."
            if is_en
            else "把回答落到已选源码证据上，避免只做泛泛的仓库判断。"
        )
    elif evidence_type == "directory":
        text = (
            "Shows repository structure and responsibility boundaries relevant to the question."
            if is_en
            else "用于说明仓库结构、职责边界和这道题相关的工程组织方式。"
        )
    elif evidence_type == "readme":
        text = (
            "Captures the repository purpose and declared usage context."
            if is_en
            else "用于补充仓库目标和 README 中声明的使用语境。"
        )
    else:
        text = (
            f"Provides limited evidence for {normalized_category}."
            if is_en
            else f"为 {normalized_category} 提供有限证据。"
        )
    return _truncate(text, MAX_WHY_CHARS)


def _source_detail(
    context_pack: Dict[str, Any],
    evidence_id: str,
    category: str,
    confidence: str,
    language: str,
) -> Dict[str, Any]:
    evidence = _source_evidence_by_id(context_pack, evidence_id)
    if not evidence:
        return {}
    source_path = _text(evidence.get("source_path"))
    file_summary = _file_summary_by_path(context_pack, source_path)
    snippet = _snippet_for_evidence(context_pack, evidence_id, source_path)
    summary = _truncate(
        _text(file_summary.get("summary")) or f"Source evidence from {source_path}.",
        MAX_DETAIL_SUMMARY_CHARS,
    )
    detail = {
        "evidence_id": evidence_id,
        "source_path": source_path,
        "evidence_type": "source",
        "why_it_matters": _detail_why("source", category, language),
        "confidence": _confidence(evidence.get("confidence"), confidence),
    }
    if snippet:
        detail["snippet"] = snippet
    if summary:
        detail["summary"] = summary
    return detail if detail.get("snippet") or detail.get("summary") else {}


def _manifest_detail(
    context_pack: Dict[str, Any],
    path: str,
    category: str,
    confidence: str,
    language: str,
) -> Dict[str, Any]:
    manifest = _manifest_by_path(context_pack, path)
    if not manifest:
        return {}
    summary = _manifest_summary_text(manifest)
    if not summary:
        return {}
    return {
        "evidence_id": f"manifest:{path}",
        "source_path": path,
        "evidence_type": "manifest",
        "summary": summary,
        "why_it_matters": _detail_why("manifest", category, language),
        "confidence": confidence,
    }


def _readme_detail(
    context_pack: Dict[str, Any],
    category: str,
    confidence: str,
    language: str,
) -> Dict[str, Any]:
    readme_summary = context_pack.get("readme_summary") or {}
    if not isinstance(readme_summary, dict):
        return {}
    summary = _truncate(_text(readme_summary.get("summary")), MAX_DETAIL_SUMMARY_CHARS)
    if not summary:
        return {}
    return {
        "evidence_id": "readme:README#summary",
        "source_path": "README",
        "evidence_type": "readme",
        "summary": summary,
        "why_it_matters": _detail_why("readme", category, language),
        "confidence": _confidence(readme_summary.get("confidence"), confidence),
    }


def _directory_detail(
    context_pack: Dict[str, Any],
    category: str,
    confidence: str,
    language: str,
) -> Dict[str, Any]:
    directory = context_pack.get("directory_summary") or {}
    if not isinstance(directory, dict):
        return {}
    summary = _text(directory.get("summary"))
    notable_paths = [
        _text(path)
        for path in _items(directory.get("notable_paths"))
        if _text(path)
    ]
    if notable_paths:
        summary = f"{summary} Notable paths: {', '.join(notable_paths[:5])}."
    summary = _truncate(summary, MAX_DETAIL_SUMMARY_CHARS)
    if not summary:
        return {}
    confidence_value = "low" if directory.get("truncated") else confidence
    return {
        "evidence_id": "directory:summary",
        "source_path": "repository tree",
        "evidence_type": "directory",
        "summary": summary,
        "why_it_matters": _detail_why("directory", category, language),
        "confidence": confidence_value,
    }


def _append_detail(details: List[Dict[str, Any]], detail: Dict[str, Any]) -> None:
    if not detail:
        return
    required = ["evidence_id", "source_path", "evidence_type", "why_it_matters"]
    if any(not _text(detail.get(field)) for field in required):
        return
    if not (_text(detail.get("snippet")) or _text(detail.get("summary"))):
        return
    if detail["evidence_id"] in {existing["evidence_id"] for existing in details}:
        return
    details.append(detail)


def _evidence_details(
    context_pack: Dict[str, Any],
    refs: List[str],
    category: str,
    confidence: str,
    language: str,
) -> List[Dict[str, Any]]:
    details: List[Dict[str, Any]] = []
    for ref in refs:
        if len(details) >= MAX_EVIDENCE_DETAILS:
            break
        if ref.startswith("src:"):
            _append_detail(details, _source_detail(context_pack, ref, category, confidence, language))
        elif ref.startswith("manifest:"):
            _append_detail(
                details,
                _manifest_detail(context_pack, ref.removeprefix("manifest:"), category, confidence, language),
            )
        elif ref.startswith("readme:"):
            _append_detail(details, _readme_detail(context_pack, category, confidence, language))
        elif ref == "directory:summary":
            _append_detail(details, _directory_detail(context_pack, category, confidence, language))

    fallback_candidates = []
    should_add_manifest_fallback = (
        _text(category) == "dependency and packaging" or not details
    )
    if should_add_manifest_fallback and not any(detail.get("evidence_type") == "manifest" for detail in details):
        fallback_candidates.extend(
            _manifest_detail(context_pack, path, category, confidence, language)
            for path in _manifest_paths(context_pack)
        )
    fallback_candidates.extend(
        [
            _readme_detail(context_pack, category, confidence, language),
            _directory_detail(context_pack, category, confidence, language),
        ]
    )
    for detail in fallback_candidates:
        if len(details) >= MAX_EVIDENCE_DETAILS:
            break
        _append_detail(details, detail)
    return details[:MAX_EVIDENCE_DETAILS]


def _detail_topic(detail: Dict[str, Any], category: str, language: str) -> str:
    evidence_type = detail.get("evidence_type")
    normalized_category = _text(category)
    is_en = language == "en"
    if evidence_type == "manifest" and normalized_category == "dependency and packaging":
        return (
            "packaging, dependency, and entrypoint evidence"
            if is_en
            else "packaging / dependency / entrypoint 证据"
        )
    if evidence_type == "source" and normalized_category == "implementation detail":
        return "implementation boundary or concrete behavior" if is_en else "实现边界或具体行为"
    if evidence_type == "directory":
        return "repository structure and responsibility split" if is_en else "仓库结构和职责边界"
    if evidence_type == "readme":
        return "repository purpose and declared usage" if is_en else "仓库目标和声明的使用语境"
    return "the evidence behind this question" if is_en else "这道题背后的证据"


def _grounded_direction(
    category: str,
    difficulty: str,
    language: str,
    details: List[Dict[str, Any]],
    fallback_paths: List[str],
) -> str:
    difficulty_direction = _difficulty_direction(difficulty, language)
    if not details:
        if language == "en":
            return _truncate(
                f"{difficulty_direction} Available repository evidence is limited, so state the boundary as a preliminary conclusion and name what README, manifest, directory, or source evidence you would need next.",
                MAX_DIRECTION_CHARS,
            )
        return _truncate(
            f"{difficulty_direction} 可用证据有限，因此先把结论说明为初步判断，再明确还需要 README、manifest、目录或源码中的哪些证据来验证。",
            MAX_DIRECTION_CHARS,
        )

    first_path = _text(details[0].get("source_path"))
    second_path = _text(details[1].get("source_path")) if len(details) > 1 else ""
    topic = (
        _detail_topic(details[0], category, language)
        if details
        else ("repository evidence" if language == "en" else "仓库证据")
    )

    if language == "en":
        if difficulty == "junior":
            body = f" Start from {first_path} to identify {topic} in simple terms."
            if second_path:
                body += f" Then connect {second_path} to what the component does and how it fits the structure."
            body += " Close with one concrete way to verify the understanding."
        elif difficulty == "senior":
            body = (
                f" Start from {first_path} to define the supported boundary, "
                "then discuss trade-offs, failure modes, and evolution paths."
            )
            if second_path:
                body += f" Use {second_path} to ground the implementation or verification point."
            body += " Close with production-readiness checks and what evidence is still missing."
        else:
            body = (
                f" Start from {first_path} to explain {topic}, then describe "
                "how you would verify the behavior and locate issues."
            )
            if second_path:
                body += f" Connect {second_path} to the implementation or automation evidence."
            body += " Call out any conclusion that is limited by the available evidence."
        return _truncate(f"{difficulty_direction}{body}", MAX_DIRECTION_CHARS)

    if difficulty == "junior":
        body = f" 先结合 {first_path} 识别{topic}，用简单语言说明它是什么、负责什么。"
        if second_path:
            body += f" 再结合 {second_path} 说明它和项目结构如何协作。"
        body += " 最后补一句你会如何验证这个理解。"
    elif difficulty == "senior":
        body = f" 先结合 {first_path} 说明当前证据支持的设计边界，再讨论权衡、故障模式和演进路径。"
        if second_path:
            body += f" 用 {second_path} 补充实现或验证依据。"
        body += " 最后说明生产化还需要补哪些验证和风险收敛。"
    else:
        body = f" 先结合 {first_path} 说明{topic}，再讲你会如何验证行为、定位问题。"
        if second_path:
            body += f" 再连接 {second_path} 说明实现或自动化证据。"
        body += " 如果证据有限，要明确哪些结论只是初步判断。"
    return _truncate(f"{difficulty_direction}{body}", MAX_DIRECTION_CHARS)


def _symbol_summary(context_pack: Dict[str, Any]) -> str:
    symbols = []
    for file_summary in _items(context_pack.get("file_summaries")):
        if isinstance(file_summary, dict):
            for symbol in _items(file_summary.get("important_symbols")):
                text = _text(symbol)
                if text and text not in symbols:
                    symbols.append(text)
        if len(symbols) >= 4:
            break
    return ", ".join(symbols[:4]) if symbols else "关键源码"


def _repo_name(context_pack: Dict[str, Any]) -> str:
    metadata = context_pack.get("repo_metadata") or {}
    if isinstance(metadata, dict):
        return _text(metadata.get("full_name")) or _text(metadata.get("repo")) or "这个仓库"
    return "这个仓库"


def _difficulty_direction(difficulty: str, language: str) -> Dict[str, str]:
    normalized = difficulty if difficulty in {"junior", "mid", "senior"} else "mid"
    if language == "en":
        return {
            "junior": "Start by identifying the visible components and explaining them in simple terms.",
            "mid": "Start from the implementation evidence, then explain how you would verify the behavior.",
            "senior": "Start with trade-offs, evolution paths, failure modes, and how you would make the design production-ready.",
        }[normalized]
    return {
        "junior": "先识别可见组件和基础职责，用简单语言说明它们如何协作。",
        "mid": "先结合实现证据说明设计和验证方式，再补充你会如何定位问题。",
        "senior": "先讲权衡、演进路径和故障模式，再说明你会如何把设计推进到生产可用。",
    }[normalized]


def _build_templates(
    context_pack: Dict[str, Any],
    target_role: str,
    difficulty: str,
    language: str,
    has_source_evidence: bool,
) -> List[Question]:
    repo = _repo_name(context_pack)
    refs = _first_evidence_refs(context_pack)
    manifest_refs = _manifest_refs(context_pack)
    source_paths = _source_paths_from_refs(context_pack, refs) or _fallback_paths(context_pack)
    manifest_paths = _manifest_paths(context_pack)
    confidence = "medium" if has_source_evidence else "low"
    role = target_role or "software engineer"
    symbols = _symbol_summary(context_pack)
    difficulty_direction = _difficulty_direction(difficulty, language)

    if language == "en":
        templates = [
            {
                "category": "architecture",
                "question": f"How would you explain the architecture boundary of {repo} for a {role} interview?",
                "answer_direction": f"{difficulty_direction} Connect the repository purpose, directory structure, manifests, and selected source evidence to explain module boundaries and runtime responsibilities.",
                "evidence_refs": refs,
                "source_paths": source_paths,
                "confidence": confidence,
            },
            {
                "category": "implementation detail",
                "question": f"How would you use {symbols} to explain a concrete implementation detail in {repo}?",
                "answer_direction": f"{difficulty_direction} Point to the concrete file or symbol, explain the user-facing capability, why it matters, and how you would verify it.",
                "evidence_refs": refs[:1],
                "source_paths": source_paths[:1],
                "confidence": confidence,
            },
        ]
        if manifest_refs:
            templates.append(
                {
                    "category": "dependency and packaging",
                    "question": f"What do the project manifests reveal about the technology stack and packaging strategy of {repo}?",
                    "answer_direction": f"{difficulty_direction} Use the manifest files to identify the ecosystem and dependencies, then explain how this shapes local development, deployment, and interview talking points.",
                    "evidence_refs": manifest_refs,
                    "source_paths": manifest_paths,
                    "confidence": confidence,
                }
            )
        templates.append(
            {
                "category": "testing and automation",
                "question": f"How would you discuss testing or automation readiness in {repo}?",
                "answer_direction": f"{difficulty_direction} Start from automation-related files or scripts, explain the confidence they provide, and state what extra tests or checks you would add before production use.",
                "evidence_refs": refs,
                "source_paths": source_paths,
                "confidence": confidence,
            }
        )
        return templates

    templates = [
        {
            "category": "architecture",
            "question": f"你会如何面向 {role} 面试解释 {repo} 的架构边界？",
            "answer_direction": f"{difficulty_direction} 再说明仓库目标，并结合目录结构、manifest 和源码证据解释模块边界、运行职责，以及你如何判断这些边界是合理的。",
            "evidence_refs": refs,
            "source_paths": source_paths,
            "confidence": confidence,
        },
        {
            "category": "implementation detail",
            "question": f"你会如何结合 {repo} 中的 {symbols} 说明一个具体实现细节？",
            "answer_direction": f"{difficulty_direction} 再讲用户可感知的能力，指向具体文件或符号，说明你做了什么、为什么这么做、如何验证这个实现是可靠的。",
            "evidence_refs": refs[:1],
            "source_paths": source_paths[:1],
            "confidence": confidence,
        },
    ]
    if manifest_refs:
        templates.append(
            {
                "category": "dependency and packaging",
                "question": f"你会如何根据 {repo} 的配置文件解释它的技术栈和工程化方式？",
                "answer_direction": f"{difficulty_direction} 再从 manifest 文件切入，说明生态、依赖和入口，并解释这些信息如何影响本地开发、部署和面试表达。",
                "evidence_refs": manifest_refs,
                "source_paths": manifest_paths,
                "confidence": confidence,
            }
        )
    templates.append(
        {
            "category": "testing and automation",
            "question": f"你会如何评价 {repo} 的测试或自动化准备程度？",
            "answer_direction": f"{difficulty_direction} 再引用自动化脚本、测试目录或源码证据，说明它们提供了什么质量保障，以及上线前你会补哪些检查。",
            "evidence_refs": refs,
            "source_paths": source_paths,
            "confidence": confidence,
        }
    )
    return templates


def build_interview_questions(
    project_context_pack: Dict[str, Any],
    target_role: str,
    difficulty: str,
    question_count: int,
    language: str,
) -> Dict[str, Any]:
    has_source_evidence = bool(_items(project_context_pack.get("file_summaries"))) and bool(
        _items(project_context_pack.get("evidence_map"))
    )
    requested_count = max(1, min(int(question_count), 10))
    normalized_difficulty = _text(difficulty) or "mid"
    normalized_language = "en" if language == "en" else "zh"
    templates = _build_templates(
        project_context_pack,
        _text(target_role),
        normalized_difficulty,
        normalized_language,
        has_source_evidence,
    )
    selected = templates[:requested_count]
    questions = []
    for index, question in enumerate(selected, start=1):
        normalized = dict(question)
        normalized["id"] = f"Q{index}"
        normalized["difficulty"] = normalized_difficulty
        normalized["evidence_refs"] = _items(normalized.get("evidence_refs"))
        normalized["source_paths"] = _items(normalized.get("source_paths")) or _fallback_paths(project_context_pack)
        confidence_cap = "medium" if has_source_evidence else "low"
        normalized["confidence"] = _confidence_cap(normalized.get("confidence"), confidence_cap)
        evidence_details = _evidence_details(
            project_context_pack,
            normalized["evidence_refs"],
            _text(normalized.get("category")),
            normalized["confidence"],
            normalized_language,
        )
        normalized["evidence_details"] = evidence_details
        for detail in evidence_details:
            detail_path = _text(detail.get("source_path"))
            if (
                detail_path
                and detail_path not in {"README", "repository tree"}
                and detail_path not in normalized["source_paths"]
            ):
                normalized["source_paths"].append(detail_path)
        normalized["question"] = _truncate(normalized.get("question"), MAX_QUESTION_CHARS)
        normalized["answer_direction"] = _grounded_direction(
            _text(normalized.get("category")),
            normalized_difficulty,
            normalized_language,
            evidence_details,
            normalized["source_paths"],
        )
        questions.append(normalized)

    return {
        "questions": questions,
        "summary": {
            "requested_count": requested_count,
            "generated_count": len(questions),
            "available_template_count": len(templates),
            "strategy": "deterministic_evidence_templates",
            "difficulty": normalized_difficulty,
            "has_source_evidence": has_source_evidence,
            "has_evidence_details": any(question.get("evidence_details") for question in questions),
        },
    }
