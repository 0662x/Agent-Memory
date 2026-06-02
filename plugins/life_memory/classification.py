from __future__ import annotations

import re
from collections.abc import Iterable

from .models import ClassificationDecision, MemoryClassification
from .time_utils import clamp

_TECHNICAL_RE = re.compile(
    r"\b("
    r"hermes|openclaw|codex|ssh|tts|qq ?bot|plugin|pytest|pyproject|sqlite|"
    r"api|sdk|dependency|dependencies|runtime|workspace|repository|repo|"
    r"debug|bug|stack trace|class|function|module|schema|database|server|"
    r"macos|windows|linux|git|branch|commit|docker|venv"
    r")\b",
    re.I,
)
_CHINESE_TECHNICAL_RE = re.compile(
    r"(接口|依赖|数据库|仓库|分支|提交|调试|服务器|运行时|插件|代码|"
    r"单元测试|集成测试|测试用例|测试覆盖|跑测试)"
)

_USER_PROFILE_RE = re.compile(
    r"\b("
    r"from now on|always|whenever|when you|generate|respond|reply|answer|"
    r"responses?|answers?|write|format|tone|style|language|translation|translate|include .* below|"
    r"call me|refer to me|my long[- ]term goal|long[- ]term goal|career goal|academic goal|"
    r"career plan|future career|want to become|hope to become"
    r")\b",
    re.I,
)
_PROFILE_GOAL_RE = re.compile(
    r"\b(my )?(?:long[- ]term|career|academic|future) (?:goal|plan)s?\b|"
    r"\b(?:want|hope|plan) to (?:become|work as|pursue)\b",
    re.I,
)
_CHINESE_USER_PROFILE_RE = re.compile(
    r"(从现在开始|以后你|回答时|回复时|翻译|叫我|称呼我|输出格式|长期目标|职业目标|学业目标|人生目标|未来目标|职业规划)"
)
_CHINESE_PROFILE_GOAL_RE = re.compile(
    r"(长期目标|职业目标|学业目标|人生目标|未来目标|职业规划|希望以后|未来想|以后想|想成为|想做[^。！？\n]{0,20}岗位)"
)

_TEMPORARY_CONTEXT_RE = re.compile(
    r"\b("
    r"for this conversation|for this chat|for this session|current task|"
    r"right now|temporary|temporarily|draft|this file|this report|today's task"
    r")\b",
    re.I,
)
_CHINESE_TEMPORARY_CONTEXT_RE = re.compile(r"(这次对话|当前任务|这个任务|这份报告|临时|暂时|先别|不要长期记|不要保存|别保存)")

_TEMPORARY_EMOTION_RE = re.compile(
    r"\b("
    r"tired today|a bit tired|sleepy today|stressed today|busy today|"
    r"feeling .* today|currently feeling|right now i(?:'m| am)"
    r")\b",
    re.I,
)
_CHINESE_TEMPORARY_EMOTION_RE = re.compile(r"(今天.*(累|困|焦虑|压力|忙)|现在.*(累|困|焦虑|压力))")

_LIFE_MEMORY_RE = re.compile(
    r"\b("
    r"remember|prefer|prefers|preference|favorite|favourite|like|likes|love|loves|enjoy|enjoys|"
    r"usually|often|tend|habit|routine|after midnight|morning|night|"
    r"sister|brother|mother|father|partner|wife|husband|family|friend|"
    r"live|lives|home|birthday|pet|dog|cat|exercise|sleep|dinner|breakfast|lunch|work late|"
    r"relationship|lifestyle"
    r")\b",
    re.I,
)
_CHINESE_LIFE_MEMORY_RE = re.compile(
    r"(记一下|记住|长期记|我通常|我一般|我经常|我往往|我偏好|我喜欢|我更喜欢|"
    r"喜欢喝|喜欢吃|更喜欢喝|更喜欢吃|偏好喝|偏好吃|饭后.*喜欢|"
    r"通常会.*(喝|吃|买|去|泡|做)|一般会.*(喝|吃|买|去|泡|做)|经常会.*(喝|吃|买|去|泡|做)|"
    r"周[一二三四五六日天].*(通常|一般|经常|习惯)|"
    r"我住在|我搬到|我的(姐姐|妹妹|哥哥|弟弟|妈妈|爸爸|伴侣|妻子|丈夫|家人|朋友)|"
    r"生日|宠物|睡眠|运动|慢跑|跑步|健身|羽毛球|游泳|散步|豆浆)"
)

_ABSTRACT_PATTERN_RE = re.compile(
    r"\b("
    r"across several sessions|over time|repeated evidence|multiple times|"
    r"pattern|tends to|tend to|usually|often|rejects over-engineered|mvp-first"
    r")\b",
    re.I,
)

_PREFERENCE_RE = re.compile(
    r"\b(prefer|prefers|preference|favorite|favourite|rather|like|likes|love|loves|enjoy|enjoys)\b",
    re.I,
)
_CHINESE_PREFERENCE_RE = re.compile(r"(偏好|喜欢|更喜欢|更能集中|不喜欢|讨厌)")

_PATTERN_RE = re.compile(
    r"\b(usually|often|tend|tends|habit|routine|over time|repeated|across several sessions)\b",
    re.I,
)
_STRONG_PATTERN_RE = re.compile(r"\b(tend|tends|pattern|over time|repeated|across several sessions)\b", re.I)
_CHINESE_PATTERN_RE = re.compile(r"(通常|通常会|一般|一般会|经常|经常会|往往|习惯|总是)")
_CHINESE_STRONG_PATTERN_RE = re.compile(r"(通常|一般|经常|往往|习惯|反复|多次)")

_FAMILY_RE = re.compile(r"\b(sister|brother|mother|father|parent|partner|wife|husband|family)\b", re.I)
_WORK_RE = re.compile(r"\b(work|focus|deep work|implementation|mvp|project)\b", re.I)
_NIGHT_RE = re.compile(r"\b(night|midnight|late)\b", re.I)
_MORNING_RE = re.compile(r"\b(morning|early)\b", re.I)
_FOOD_RE = re.compile(r"\b(food|coffee|tea|restaurant|breakfast|lunch|dinner)\b", re.I)
_HEALTH_RE = re.compile(r"\b(exercise|sleep|tired|health|medication|therapy)\b", re.I)
_CHINESE_FAMILY_RE = re.compile(r"(姐姐|妹妹|哥哥|弟弟|妈妈|爸爸|父母|伴侣|妻子|丈夫|家人|朋友)")
_CHINESE_WORK_RE = re.compile(r"(工作|专注|实现|计划|复盘|重构|会议|例会)")
_CHINESE_NIGHT_RE = re.compile(r"(晚上|夜里|半夜|深夜)")
_CHINESE_MORNING_RE = re.compile(r"(早上|上午|清晨)")
_CHINESE_FOOD_RE = re.compile(r"(咖啡|茶|餐厅|早餐|午餐|晚餐|晚饭|饮品|豆浆)")
_CHINESE_HEALTH_RE = re.compile(r"(运动|睡眠|累|健康|药|治疗|焦虑|慢跑|跑步|健身|羽毛球|游泳|散步)")


def classify_candidate(
    content: str,
    *,
    explicit_user_request: bool = False,
    evidence_count: int = 1,
    category_hint: str | None = None,
    tags: Iterable[str] | None = None,
    source: str | None = None,
    source_ref: str | None = None,
    context: dict | None = None,
) -> ClassificationDecision:
    del source, source_ref, context
    text = " ".join((content or "").strip().split())
    provided_tags = tuple(_normalize_tag(tag) for tag in (tags or ()) if _normalize_tag(tag))

    if not text:
        return ClassificationDecision(
            classification=MemoryClassification.NO_SAVE,
            confidence=1.0,
            reason="Empty content has no durable memory value.",
            should_store=False,
        )

    if _is_abstract_experience(text, evidence_count):
        suggested_tags = _merge_tags(provided_tags, ("pattern_candidate", "abstract_experience"))
        return ClassificationDecision(
            classification=MemoryClassification.ABSTRACT_EXPERIENCE,
            confidence=0.84,
            reason="Repeated evidence supports an abstract experience candidate rather than a direct life memory.",
            primary_category="personal_pattern",
            tags=suggested_tags,
            should_store=False,
        )

    if _TECHNICAL_RE.search(text) or _CHINESE_TECHNICAL_RE.search(text):
        return ClassificationDecision(
            classification=MemoryClassification.TECHNICAL_MEMORY,
            confidence=0.9,
            reason="Technical project or runtime detail belongs in Hermes technical memory, not life memory.",
            tags=provided_tags,
            should_store=False,
        )

    if _is_user_profile(text):
        return ClassificationDecision(
            classification=MemoryClassification.USER_PROFILE,
            confidence=0.86,
            reason="Stable response preference or language/format instruction belongs in user profile memory.",
            tags=provided_tags,
            should_store=False,
        )

    if _is_temporary_context(text):
        return ClassificationDecision(
            classification=MemoryClassification.TEMPORARY_WORKING_MEMORY,
            confidence=0.82,
            reason="Temporary conversation or current task context should stay in working memory.",
            tags=provided_tags,
            should_store=False,
        )

    if (_TEMPORARY_EMOTION_RE.search(text) or _CHINESE_TEMPORARY_EMOTION_RE.search(text)) and not explicit_user_request:
        return ClassificationDecision(
            classification=MemoryClassification.NO_SAVE,
            confidence=0.86,
            reason="Temporary one-off state has no durable life-memory value by default.",
            tags=provided_tags,
            should_store=False,
        )

    if _looks_like_life_memory(text, explicit_user_request):
        primary_category = _primary_category(text, category_hint)
        suggested_tags = _suggest_tags(text, primary_category, provided_tags, explicit_user_request)
        confidence = 0.86 if explicit_user_request or _LIFE_MEMORY_RE.search(text) else 0.72
        reason_parts = ["In-scope life memory"]
        if primary_category == "personal_preference":
            reason_parts.append("with personal preference and routine signals")
        elif primary_category == "personal_pattern":
            reason_parts.append("with repeated personal behavior pattern signals")
        else:
            reason_parts.append("with personal fact signals")
        return ClassificationDecision(
            classification=MemoryClassification.LIFE_MEMORY,
            confidence=clamp(confidence),
            reason=" ".join(reason_parts) + ".",
            primary_category=primary_category,
            tags=suggested_tags,
            should_store=True,
        )

    return ClassificationDecision(
        classification=MemoryClassification.NO_SAVE,
        confidence=0.72,
        reason="Content is trivial, uncertain, or lacks a clear durable life-memory signal.",
        tags=provided_tags,
        should_store=False,
    )


def _is_abstract_experience(text: str, evidence_count: int) -> bool:
    return evidence_count >= 3 and bool(_ABSTRACT_PATTERN_RE.search(text))


def _is_user_profile(text: str) -> bool:
    if _PROFILE_GOAL_RE.search(text) or _CHINESE_PROFILE_GOAL_RE.search(text):
        return True
    if "remember" in text.lower() and _LIFE_MEMORY_RE.search(text):
        return False
    if any(term in text for term in ("记一下", "记住", "长期记")) and _CHINESE_LIFE_MEMORY_RE.search(text):
        return False
    return bool(_USER_PROFILE_RE.search(text) or _CHINESE_USER_PROFILE_RE.search(text))


def _is_temporary_context(text: str) -> bool:
    return bool(_TEMPORARY_CONTEXT_RE.search(text) or _CHINESE_TEMPORARY_CONTEXT_RE.search(text))


def _looks_like_life_memory(text: str, explicit_user_request: bool) -> bool:
    return explicit_user_request or bool(_LIFE_MEMORY_RE.search(text) or _CHINESE_LIFE_MEMORY_RE.search(text))


def _primary_category(text: str, category_hint: str | None) -> str:
    normalized_hint = _normalize_tag(category_hint or "")
    if normalized_hint in {"personal_fact", "personal_preference", "personal_pattern"}:
        return normalized_hint
    if _STRONG_PATTERN_RE.search(text) or _CHINESE_STRONG_PATTERN_RE.search(text):
        return "personal_pattern"
    if _PREFERENCE_RE.search(text) or _CHINESE_PREFERENCE_RE.search(text):
        return "personal_preference"
    if _PATTERN_RE.search(text) or _CHINESE_PATTERN_RE.search(text):
        return "personal_pattern"
    return "personal_fact"


def _suggest_tags(
    text: str,
    primary_category: str,
    provided_tags: tuple[str, ...],
    explicit_user_request: bool,
) -> tuple[str, ...]:
    tags: list[str] = list(provided_tags)
    if primary_category == "personal_preference":
        tags.append("preference")
    if primary_category == "personal_pattern":
        tags.append("pattern_candidate")
    if _PATTERN_RE.search(text) or _CHINESE_PATTERN_RE.search(text):
        tags.append("routine")
    if _FAMILY_RE.search(text) or _CHINESE_FAMILY_RE.search(text):
        tags.append("family")
    if _WORK_RE.search(text) or _CHINESE_WORK_RE.search(text):
        tags.append("work_style")
    if _NIGHT_RE.search(text) or _CHINESE_NIGHT_RE.search(text):
        tags.append("night")
    if _MORNING_RE.search(text) or _CHINESE_MORNING_RE.search(text):
        tags.append("morning")
    if _FOOD_RE.search(text) or _CHINESE_FOOD_RE.search(text):
        tags.append("food")
    if _HEALTH_RE.search(text) or _CHINESE_HEALTH_RE.search(text):
        tags.append("health")
    if explicit_user_request and (_TEMPORARY_EMOTION_RE.search(text) or _CHINESE_TEMPORARY_EMOTION_RE.search(text)):
        tags.append("recent_state")
    return _merge_tags((), tags)


def _normalize_tag(value: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", value.strip().lower()).strip("_")


def _merge_tags(existing: tuple[str, ...], new_tags: Iterable[str]) -> tuple[str, ...]:
    merged: list[str] = []
    for tag in (*existing, *tuple(new_tags)):
        normalized = _normalize_tag(tag)
        if normalized and normalized not in merged:
            merged.append(normalized)
    return tuple(merged)
