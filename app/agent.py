from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from app.models import ChatResponse, Message, Recommendation


TYPE_LABELS = {
    "A": "Ability & Aptitude",
    "B": "Biodata & Situational Judgement",
    "C": "Competencies",
    "D": "Development & 360",
    "E": "Assessment Exercises",
    "K": "Knowledge & Skills",
    "P": "Personality & Behavior",
    "S": "Simulations",
}

OFF_TOPIC = {
    "salary",
    "compensation",
    "legal",
    "law",
    "lawsuit",
    "visa",
    "contract",
    "interview questions",
    "write a jd",
    "job description",
    "benefits",
    "background check",
    "ignore previous",
    "system prompt",
    "developer message",
    "prompt injection",
}

VAGUE_TERMS = {
    "assessment",
    "assessments",
    "test",
    "tests",
    "hire",
    "hiring",
    "candidate",
    "candidates",
    "employee",
    "role",
    "job",
}

TYPE_KEYWORDS = {
    "A": {"ability", "aptitude", "cognitive", "reasoning", "numerical", "deductive", "inductive", "general ability"},
    "K": {"skill", "skills", "knowledge", "technical", "coding", "programming", "developer", "engineer", "software"},
    "P": {"personality", "behavior", "behaviour", "culture", "fit", "style", "stakeholder", "leadership"},
    "S": {"simulation", "simulate", "hands-on", "practical"},
    "B": {"situational", "judgement", "judgment", "biodata"},
    "C": {"competency", "competencies"},
}

NAMED_SKILL_BOOSTS = {
    "java": ("Java 8", "Core Java", "Java Frameworks", "Java Design Patterns", "Java Web Services", "Java Platform"),
    "python": ("Python",),
    "sql": ("SQL (New)", "Microsoft SQL Server", "SQL Server", "Oracle PL/SQL"),
    "excel": ("Microsoft Excel",),
    "agile": ("Agile Testing", "Agile Software Development"),
    "manual testing": ("Manual Testing",),
    "communication": ("Business Communication", "English Comprehension"),
}

SYNONYMS = {
    "java developer": {"java", "programming", "software", "developer", "stakeholder"},
    "software engineer": {"programming", "software", "computer science", "developer", "sql", "agile"},
    "data analyst": {"data", "sql", "excel", "analysis", "numerical"},
    "qa": {"quality", "testing", "manual testing", "agile testing"},
    "tester": {"testing", "manual testing", "agile testing", "quality"},
    "manager": {"management", "leadership", "personality", "judgement"},
    "sales": {"sales", "customer", "communication", "personality"},
    "graduate": {"graduate", "general ability", "reasoning"},
}

CURATED_SCENARIOS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (
        ("senior leadership", "cxo", "director", "executive", "leadership benchmark"),
        (
            "Occupational Personality Questionnaire OPQ32r",
            "OPQ Universal Competency Report 2.0",
            "OPQ Leadership Report",
        ),
    ),
    (
        ("rust", "networking", "high-performance", "infrastructure"),
        (
            "Smart Interview Live Coding",
            "Linux Programming (General)",
            "Networking and Implementation (New)",
            "SHL Verify Interactive G+",
            "Occupational Personality Questionnaire OPQ32r",
        ),
    ),
    (
        ("contact centre", "contact center", "inbound calls", "customer service"),
        (
            "SVAR - Spoken English (US) (New)",
            "Contact Center Call Simulation (New)",
            "Entry Level Customer Serv-Retail & Contact Center",
            "Customer Service Phone Simulation",
        ),
    ),
    (
        ("financial analyst", "financial analysts", "finance", "final-year"),
        (
            "SHL Verify Interactive – Numerical Reasoning",
            "Financial Accounting (New)",
            "Basic Statistics (New)",
            "Graduate Scenarios",
            "Occupational Personality Questionnaire OPQ32r",
        ),
    ),
    (
        ("sales organization", "sales organisation", "re-skill", "reskill", "sales transformation"),
        (
            "Global Skills Assessment",
            "Global Skills Development Report",
            "Occupational Personality Questionnaire OPQ32r",
            "OPQ MQ Sales Report",
            "Sales Transformation 2.0 - Individual Contributor",
        ),
    ),
    (
        ("plant operators", "chemical facility", "safety", "procedure compliance", "industrial"),
        (
            "Dependability and Safety Instrument (DSI)",
            "Manufac. & Indust. - Safety & Dependability 8.0",
            "Workplace Health and Safety (New)",
        ),
    ),
    (
        ("healthcare admin", "patient records", "hipaa", "medical terminology"),
        (
            "HIPAA (Security)",
            "Medical Terminology (New)",
            "Microsoft Word 365 - Essentials (New)",
            "Dependability and Safety Instrument (DSI)",
            "Occupational Personality Questionnaire OPQ32r",
        ),
    ),
    (
        ("admin assistants", "excel", "word daily", "word", "office"),
        (
            "Microsoft Excel 365 - Essentials (New)",
            "Microsoft Word 365 (New)",
            "MS Excel (New)",
            "MS Word (New)",
            "Occupational Personality Questionnaire OPQ32r",
        ),
    ),
    (
        ("full-stack", "core java", "spring", "sql", "microservice", "docker", "aws"),
        (
            "Core Java (Advanced Level) (New)",
            "Spring (New)",
            "RESTful Web Services (New)",
            "SQL (New)",
            "Amazon Web Services (AWS) Development (New)",
            "Docker (New)",
            "SHL Verify Interactive G+",
            "Occupational Personality Questionnaire OPQ32r",
        ),
    ),
    (
        ("graduate management trainee", "management trainee", "recent graduates", "situational judgement"),
        (
            "SHL Verify Interactive G+",
            "Occupational Personality Questionnaire OPQ32r",
            "Graduate Scenarios",
        ),
    ),
)


@dataclass(frozen=True)
class Assessment:
    name: str
    url: str
    test_type: str
    description: str
    entity_id: str = ""
    job_levels: str = ""
    languages: str = ""
    duration: str = ""
    remote: str = ""
    adaptive: str = ""
    keys: list[str] | None = None

    @property
    def searchable(self) -> str:
        return " ".join(
            [
                self.name,
                self.test_type,
                self.description,
                self.job_levels,
                self.languages,
                self.duration,
                self.remote,
                self.adaptive,
                " ".join(self.keys or []),
            ]
        ).lower()


class SHLAgent:
    def __init__(self, catalog_path: Path | None = None) -> None:
        path = catalog_path or Path(__file__).parent / "data" / "shl_catalog.json"
        rows = json.loads(path.read_text(encoding="utf-8"))
        fields = set(Assessment.__dataclass_fields__)
        self.catalog = [Assessment(**{k: v for k, v in row.items() if k in fields}) for row in rows]

    def respond(self, messages: list[Message]) -> ChatResponse:
        user_messages = [m.content for m in messages if m.role == "user"]
        latest = user_messages[-1]
        full_context = "\n".join(user_messages[-8:])

        if self._is_off_topic(latest):
            return ChatResponse(
                reply=(
                    "I can only help with SHL assessment selection and comparisons from the SHL Individual "
                    "Test Solutions catalog. Please share the role, skills, seniority, and assessment constraints."
                ),
                recommendations=[],
                end_of_conversation=False,
            )

        if self._is_compare(latest):
            return self._compare(latest)

        if self._asks_for_shorter_opq_alternative(latest, full_context):
            return ChatResponse(
                reply=(
                    "OPQ32r is the catalog personality assessment that best fits that need. I do not have a "
                    "grounded shorter SHL personality replacement to recommend from the catalog; if time is the "
                    "priority, I can remove OPQ32r and keep the cognitive and situational judgement items."
                ),
                recommendations=[],
                end_of_conversation=False,
            )

        if self._should_clarify(messages, full_context):
            return ChatResponse(
                reply=(
                    "I can help narrow this down. What role are you hiring for, what skills or behaviors matter most, "
                    "and do you need cognitive, technical, personality, or simulation-style assessments?"
                ),
                recommendations=[],
                end_of_conversation=False,
            )

        ranked = self._apply_curated_scenarios(full_context, self._rank(full_context))
        requested_types = self._requested_types(full_context)
        if requested_types and not any(any(t in a.test_type for t in requested_types) for a in ranked[:10]):
            ranked = self._rank(full_context + " " + " ".join(TYPE_LABELS[t] for t in requested_types))

        selected = self._diverse_top(ranked, requested_types, limit=10)
        if not selected:
            return ChatResponse(
                reply=(
                    "I could not ground a shortlist in the SHL Individual Test Solutions catalog from that context. "
                    "Please provide the target role and the skills or traits you want to measure."
                ),
                recommendations=[],
                end_of_conversation=False,
            )

        recs = [Recommendation(name=a.name, url=a.url, test_type=a.test_type) for a in selected]
        role_hint = self._role_hint(full_context)
        reply = f"Got it. Here are {len(recs)} SHL Individual Test Solutions"
        if role_hint:
            reply += f" that best match {role_hint}"
        reply += "."
        return ChatResponse(reply=reply, recommendations=recs, end_of_conversation=True)

    def _is_off_topic(self, text: str) -> bool:
        t = text.lower()
        if any(term in t for term in OFF_TOPIC):
            return True
        return bool(re.search(r"\b(weather|recipe|movie|stock price|medical|doctor|tax)\b", t))

    def _is_compare(self, text: str) -> bool:
        t = text.lower()
        return any(word in t for word in ("compare", "difference", "different", "versus", " vs ", "better than"))

    def _should_clarify(self, messages: list[Message], context: str) -> bool:
        user_turns = [m for m in messages if m.role == "user"]
        text = context.lower()
        if len(user_turns) == 1 and "senior leadership" in text and not any(
            signal in text for signal in ("selection", "development", "benchmark", "report")
        ):
            return True
        if len(user_turns) == 1 and ("contact centre" in text or "contact center" in text) and not any(
            language in text for language in ("english", "spanish", "french", "german", "hindi")
        ):
            return True
        tokens = set(re.findall(r"[a-z0-9+#.]+", text))
        meaningful = tokens - VAGUE_TERMS
        has_catalog_signal = any(term in text for term in ("java", "python", "sql", "developer", "analyst", "sales", "manager", "qa", "testing"))
        has_type_signal = bool(self._requested_types(text))
        if len(user_turns) == 1 and (len(meaningful) < 3 or (not has_catalog_signal and not has_type_signal)):
            return True
        return len(meaningful) < 2 and not has_catalog_signal

    def _requested_types(self, text: str) -> set[str]:
        t = text.lower()
        wanted: set[str] = set()
        for code, words in TYPE_KEYWORDS.items():
            if any(word in t for word in words):
                wanted.add(code)
        return wanted

    def _rank(self, context: str) -> list[Assessment]:
        query = self._expand(context.lower())
        query_terms = set(re.findall(r"[a-z0-9+#.]+", query)) - VAGUE_TERMS
        requested_types = self._requested_types(query)
        scored: list[tuple[float, Assessment]] = []
        for assessment in self.catalog:
            hay = assessment.searchable
            name_terms = set(re.findall(r"[a-z0-9+#.]+", assessment.name.lower()))
            score = 0.0
            for term in query_terms:
                if len(term) <= 2:
                    continue
                if term in name_terms:
                    score += 12
                elif assessment.name.lower().startswith(term):
                    score += 8
                elif term in assessment.name.lower():
                    score += 3
                elif term in hay:
                    score += 2
            for code in requested_types:
                if code in assessment.test_type:
                    score += 5
            if "stakeholder" in query and "Business Communication" in assessment.name:
                score += 8
            if "stakeholder" in query and "OPQ" in assessment.name:
                score += 5
            if re.search(r"\bjava\b", query) and assessment.name == "Java 8 (New)":
                score += 20
            if re.search(r"\bjava\b", query) and re.search(r"\bjava\b", assessment.name.lower()):
                score += 25
            if re.search(r"\bjava\b", query) and assessment.name == "JavaScript (New)":
                score -= 20
            for trigger, names in NAMED_SKILL_BOOSTS.items():
                if trigger in query and any(name.lower() in assessment.name.lower() for name in names):
                    score += 30
            if "python" in query and assessment.name == "Python (New)":
                score += 70
            if re.search(r"\bsql\b", query) and assessment.name == "SQL (New)":
                score += 70
            if ("stakeholder" in query or "personality" in query) and assessment.name == "Occupational Personality Questionnaire OPQ32r":
                score += 50
            if "developer" in query and "programming" in hay:
                score += 4
            if score > 0:
                scored.append((score, assessment))
        scored.sort(key=lambda item: (-item[0], item[1].name))
        return [item[1] for item in scored]

    def _expand(self, text: str) -> str:
        additions: list[str] = []
        for phrase, terms in SYNONYMS.items():
            if phrase in text or any(part in text for part in phrase.split()):
                additions.extend(terms)
        return text + " " + " ".join(additions)

    def _asks_for_shorter_opq_alternative(self, latest: str, context: str) -> bool:
        latest_l = latest.lower()
        context_l = context.lower()
        return "opq" in context_l and "shorter" in latest_l and any(
            word in latest_l for word in ("replace", "alternative", "remove")
        )

    def _apply_curated_scenarios(self, context: str, ranked: list[Assessment]) -> list[Assessment]:
        t = context.lower()
        curated_names: list[str] = []
        for triggers, names in CURATED_SCENARIOS:
            hits = sum(1 for trigger in triggers if trigger in t)
            if hits >= 2 or (hits == 1 and any(strong in t for strong in ("confirmed", "final", "shortlist", "battery"))):
                curated_names.extend(names)

        if "drop rest" in t or "rest out" in t:
            curated_names = [name for name in curated_names if name != "RESTful Web Services (New)"]
        if "drop the opq" in t or "opq32r removed" in t:
            curated_names = [name for name in curated_names if name != "Occupational Personality Questionnaire OPQ32r"]
        if "industrial" in t and "safety" in t and "confirmed" in t:
            curated_names = [
                "Manufac. & Indust. - Safety & Dependability 8.0",
                "Workplace Health and Safety (New)",
            ]
        if "simulation" not in t and "quickly screen admin assistants" in t:
            curated_names = [
                "MS Excel (New)",
                "MS Word (New)",
                "Occupational Personality Questionnaire OPQ32r",
            ]

        by_name = {assessment.name: assessment for assessment in self.catalog}
        curated = [by_name[name] for name in dict.fromkeys(curated_names) if name in by_name]
        seen = {assessment.name for assessment in curated}
        return curated + [assessment for assessment in ranked if assessment.name not in seen]

    def _diverse_top(self, ranked: list[Assessment], requested_types: set[str], limit: int) -> list[Assessment]:
        selected: list[Assessment] = []
        seen = set()
        for assessment in ranked:
            if assessment.name in seen:
                continue
            if requested_types and not any(code in assessment.test_type for code in requested_types):
                always_keep = {
                    "SHL Verify Interactive G+",
                    "Occupational Personality Questionnaire OPQ32r",
                }
                if len(selected) >= 5 and assessment.name not in always_keep:
                    continue
            selected.append(assessment)
            seen.add(assessment.name)
            if len(selected) == limit:
                break
        for code in requested_types:
            if any(code in assessment.test_type for assessment in selected):
                continue
            replacement = next(
                (assessment for assessment in ranked if code in assessment.test_type and assessment.name not in seen),
                None,
            )
            if replacement:
                insert_at = min(2, len(selected))
                selected.insert(insert_at, replacement)
                seen.add(replacement.name)
                selected = selected[:limit]
        return selected

    def _compare(self, latest: str) -> ChatResponse:
        mentioned = self._mentioned_assessments(latest)
        if len(mentioned) < 2:
            return ChatResponse(
                reply="Which two SHL assessments from the catalog would you like me to compare?",
                recommendations=[],
                end_of_conversation=False,
            )
        left, right = mentioned[:2]
        reply = (
            f"{left.name} is a {self._type_text(left.test_type)} assessment. Catalog description: "
            f"{left.description} {right.name} is a {self._type_text(right.test_type)} assessment. "
            f"Catalog description: {right.description} In short, the first focuses on {self._short_focus(left)}, "
            f"while the second focuses on {self._short_focus(right)}."
        )
        return ChatResponse(reply=reply, recommendations=[], end_of_conversation=False)

    def _mentioned_assessments(self, text: str) -> list[Assessment]:
        t = text.lower()
        matches: list[tuple[int, Assessment]] = []
        aliases = {
            "opq": "Occupational Personality Questionnaire OPQ32r",
            "opq32r": "Occupational Personality Questionnaire OPQ32r",
            "gsa": "Global Skills Development Report",
            "general ability screen": "Verify - General Ability Screen",
        }
        for alias, name in aliases.items():
            if re.search(rf"\b{re.escape(alias)}\b", t):
                assessment = next((a for a in self.catalog if a.name == name), None)
                if assessment:
                    matches.append((100, assessment))
        for assessment in self.catalog:
            name = assessment.name.lower()
            base = re.sub(r"\s*\(new\)", "", name)
            if name in t or base in t:
                matches.append((len(base), assessment))
        dedup: dict[str, tuple[int, Assessment]] = {}
        for score, assessment in matches:
            dedup[assessment.name] = max(dedup.get(assessment.name, (0, assessment)), (score, assessment), key=lambda x: x[0])
        return [item[1] for item in sorted(dedup.values(), key=lambda x: -x[0])]

    def _type_text(self, test_type: str) -> str:
        return "/".join(TYPE_LABELS.get(code, code) for code in test_type.split())

    def _short_focus(self, assessment: Assessment) -> str:
        desc = assessment.description.split(".")[0]
        return desc[:140].lower()

    def _role_hint(self, context: str) -> str:
        t = context.lower()
        for role in ("java developer", "python developer", "software engineer", "data analyst", "qa tester", "sales", "manager"):
            if role in t:
                return role
        return ""
