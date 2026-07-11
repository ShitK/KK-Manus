from typing import Any


LANGUAGES = {"zh", "en"}
COACH_STYLES = {"concise", "direct", "encouraging", "balanced"}
QUESTION_CATEGORIES = {
    "architecture",
    "implementation detail",
    "dependency and packaging",
    "testing and automation",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_from_aliases(
    value: Any,
    canonical: set[str],
    aliases: dict[str, tuple[str, ...]],
) -> tuple[str, bool]:
    lowered = _text(value).lower()
    if lowered in canonical:
        return lowered, False
    for normalized, terms in aliases.items():
        if lowered in {term.lower() for term in terms}:
            return normalized, True
    return "", False


def normalize_language(value: Any) -> tuple[str, bool]:
    return _normalize_from_aliases(
        value,
        LANGUAGES,
        {
            "zh": ("中文", "汉语", "用中文", "请用中文展示", "chinese"),
            "en": ("英文", "英语", "用英文", "please use english", "english"),
        },
    )


def normalize_coach_style(value: Any) -> tuple[str, bool]:
    return _normalize_from_aliases(
        value,
        COACH_STYLES,
        {
            "concise": ("简洁", "简短", "短一点", "精简", "简洁一点"),
            "direct": ("直接", "严格", "尖锐", "直接一点"),
            "encouraging": ("鼓励", "鼓励式", "温和", "温和一点"),
            "balanced": (
                "平衡",
                "均衡",
                "平衡一点",
                "既指出优点也指出不足",
                "既说优点也说不足",
            ),
        },
    )


def normalize_question_category(value: Any) -> tuple[str, bool]:
    return _normalize_from_aliases(
        value,
        QUESTION_CATEGORIES,
        {
            "architecture": ("架构", "架构设计", "架构边界", "模块边界", "系统设计"),
            "implementation detail": ("实现", "实现细节", "代码细节", "具体实现"),
            "dependency and packaging": ("依赖", "打包", "工程化", "依赖与工程化"),
            "testing and automation": ("测试", "自动化", "测试验证", "质量保障", "ci"),
        },
    )
