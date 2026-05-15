from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.models import Message


TYPE_KEYWORDS = {
    "A": {"ability", "aptitude", "cognitive", "reasoning", "numerical", "deductive", "inductive", "general ability"},
    "K": {"skill", "skills", "knowledge", "technical", "coding", "programming", "developer", "engineer", "software"},
    "P": {"personality", "behavior", "behaviour", "culture", "fit", "style", "stakeholder", "leadership"},
    "S": {"simulation", "simulate", "hands-on", "practical"},
    "B": {"situational", "judgement", "judgment", "biodata", "scenario", "scenarios"},
    "C": {"competency", "competencies"},
    "D": {"development", "360", "feedback", "reskill", "re-skill"},
}

SKILL_TERMS = [
    ".net",
    "agile",
    "angular",
    "aws",
    "call center",
    "contact center",
    "contact centre",
    "core java",
    "customer service",
    "docker",
    "excel",
    "finance",
    "hipaa",
    "java",
    "linux",
    "medical terminology",
    "networking",
    "python",
    "rest",
    "rust",
    "safety",
    "sales",
    "spring",
    "sql",
    "word",
]


@dataclass
class ConversationConstraints:
    raw_context: str
    latest_user: str
    role: str = ""
    seniority: str = ""
    skills: list[str] = field(default_factory=list)
    assessment_types: set[str] = field(default_factory=set)
    languages: list[str] = field(default_factory=list)
    include_personality: bool = False
    include_simulation: bool = False
    include_cognitive: bool = False
    include_sjt: bool = False
    exclude_names: set[str] = field(default_factory=set)
    confirmed: bool = False

    def retrieval_query(self) -> str:
        parts = [
            self.role,
            self.seniority,
            " ".join(self.skills),
            " ".join(sorted(self.assessment_types)),
            " ".join(self.languages),
            self.raw_context,
        ]
        return " ".join(part for part in parts if part)


def extract_constraints(messages: list[Message]) -> ConversationConstraints:
    user_messages = [m.content for m in messages if m.role == "user"]
    latest = user_messages[-1]
    context = "\n".join(user_messages[-8:])
    text = context.lower()

    constraints = ConversationConstraints(raw_context=context, latest_user=latest)
    constraints.role = _extract_role(text)
    constraints.seniority = _extract_seniority(text)
    constraints.skills = _extract_skills(text)
    constraints.assessment_types = _extract_types(text)
    constraints.languages = _extract_languages(text)
    constraints.include_personality = any(word in text for word in ("personality", "opq", "behavior", "behaviour", "fit"))
    constraints.include_simulation = any(word in text for word in ("simulation", "simulate", "hands-on", "capabilities"))
    constraints.include_cognitive = any(word in text for word in ("cognitive", "reasoning", "g+", "general ability"))
    constraints.include_sjt = any(word in text for word in ("situational", "judgement", "judgment", "scenario"))
    constraints.confirmed = any(word in latest.lower() for word in ("confirmed", "lock", "final", "that's good", "that works"))

    if re.search(r"\bdrop (the )?opq\b|remove (the )?opq", text):
        constraints.exclude_names.add("Occupational Personality Questionnaire OPQ32r")
    if re.search(r"\bdrop rest\b|rest out|remove rest", text):
        constraints.exclude_names.add("RESTful Web Services (New)")
    return constraints


def _extract_role(text: str) -> str:
    role_patterns = [
        r"(senior full-stack engineer)",
        r"(senior rust engineer)",
        r"(java developer)",
        r"(financial analysts?)",
        r"(contact cent(?:er|re) agents?)",
        r"(plant operators?)",
        r"(healthcare admin staff)",
        r"(admin assistants?)",
        r"(graduate management trainee)",
        r"(sales organization|sales organisation)",
        r"(senior leadership|cxo|director-level)",
    ]
    for pattern in role_patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return ""


def _extract_seniority(text: str) -> str:
    for word in ("entry-level", "graduate", "mid-level", "senior", "director", "executive", "cxo"):
        if word in text:
            return word
    years = re.search(r"(\d+\+?\s*years?)", text)
    return years.group(1) if years else ""


def _extract_skills(text: str) -> list[str]:
    skills = [term for term in SKILL_TERMS if term in text]
    if "spoken english" in text or "inbound calls" in text:
        skills.append("spoken english")
    return list(dict.fromkeys(skills))


def _extract_types(text: str) -> set[str]:
    wanted: set[str] = set()
    for code, words in TYPE_KEYWORDS.items():
        if any(word in text for word in words):
            wanted.add(code)
    return wanted


def _extract_languages(text: str) -> list[str]:
    languages: list[str] = []
    for word in ("english", "spanish", "french", "german", "latin american spanish"):
        if word in text:
            languages.append(word)
    if "us" in text and "english" in text:
        languages.append("english usa")
    return languages
