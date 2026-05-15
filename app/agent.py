from __future__ import annotations

import re
from pathlib import Path

from app.catalog import Assessment, TYPE_LABELS, load_catalog
from app.constraints import ConversationConstraints, extract_constraints
from app.llm import GroundedFormatter
from app.models import ChatResponse, Message, Recommendation
from app.retrieval import HybridRetriever
from app.security import is_scope_violation, refusal_reply


VAGUE_TERMS = {
    "assessment",
    "assessments",
    "candidate",
    "candidates",
    "employee",
    "hire",
    "hiring",
    "job",
    "role",
    "test",
    "tests",
}


class SHLAgent:
    def __init__(self, catalog_path: Path | None = None) -> None:
        self.catalog = load_catalog(catalog_path)
        self.retriever = HybridRetriever(self.catalog)
        self.formatter = GroundedFormatter()

    def respond(self, messages: list[Message]) -> ChatResponse:
        user_messages = [m.content for m in messages if m.role == "user"]
        latest = user_messages[-1]
        constraints = extract_constraints(messages)

        if is_scope_violation(latest):
            return ChatResponse(reply=refusal_reply(), recommendations=[], end_of_conversation=False)

        if self._is_compare(latest):
            return self._compare(latest)

        if self._asks_for_shorter_opq_alternative(latest, constraints.raw_context):
            return ChatResponse(
                reply=(
                    "OPQ32r is the catalog personality assessment that best fits that need. I do not have a "
                    "grounded shorter SHL personality replacement to recommend from the catalog; if time is the "
                    "priority, I can remove OPQ32r and keep the cognitive and situational judgement items."
                ),
                recommendations=[],
                end_of_conversation=False,
            )

        if self._should_clarify(messages, constraints):
            return ChatResponse(
                reply=(
                    "I can help narrow this down. What role are you hiring for, what skills or behaviors matter most, "
                    "and do you need cognitive, technical, personality, or simulation-style assessments?"
                ),
                recommendations=[],
                end_of_conversation=False,
            )

        ranked = self.retriever.retrieve(constraints, top_k=60)
        selected = self.retriever.select_diverse(ranked, constraints, limit=10)
        if not selected:
            return ChatResponse(
                reply=(
                    "I could not ground a shortlist in the SHL Individual Test Solutions catalog from that context. "
                    "Please provide the target role and the skills or traits you want to measure."
                ),
                recommendations=[],
                end_of_conversation=False,
            )

        reply = self.formatter.recommendation_reply(selected, self._role_hint(constraints), constraints.raw_context)
        return ChatResponse(
            reply=reply,
            recommendations=[Recommendation(name=a.name, url=a.url, test_type=a.test_type) for a in selected],
            end_of_conversation=True,
        )

    def _should_clarify(self, messages: list[Message], constraints: ConversationConstraints) -> bool:
        user_turns = [m for m in messages if m.role == "user"]
        text = constraints.raw_context.lower()
        if len(user_turns) == 1 and "senior leadership" in text and not any(
            signal in text for signal in ("selection", "development", "benchmark", "report")
        ):
            return True
        if len(user_turns) == 1 and ("contact centre" in text or "contact center" in text) and not constraints.languages:
            return True
        tokens = set(re.findall(r"[a-z0-9+#.]+", text))
        meaningful = tokens - VAGUE_TERMS
        has_signal = bool(constraints.role or constraints.skills or constraints.assessment_types)
        if len(user_turns) == 1 and (len(meaningful) < 3 or not has_signal):
            return True
        return len(meaningful) < 2 and not has_signal

    def _is_compare(self, text: str) -> bool:
        t = text.lower()
        return any(word in t for word in ("compare", "difference", "different", "versus", " vs ", "better than"))

    def _compare(self, latest: str) -> ChatResponse:
        mentioned = self._mentioned_assessments(latest)
        if len(mentioned) < 2:
            return ChatResponse(
                reply="Which two SHL assessments from the catalog would you like me to compare?",
                recommendations=[],
                end_of_conversation=False,
            )
        left, right = mentioned[:2]
        reply = self.formatter.comparison_reply(left, right, latest)
        return ChatResponse(reply=reply, recommendations=[], end_of_conversation=False)

    def _mentioned_assessments(self, text: str) -> list[Assessment]:
        t = text.lower()
        matches: list[tuple[int, Assessment]] = []
        aliases = {
            "opq": "Occupational Personality Questionnaire OPQ32r",
            "opq32r": "Occupational Personality Questionnaire OPQ32r",
            "gsa": "Global Skills Development Report",
            "general ability screen": "Verify - General Ability Screen",
            "safety & dependability 8.0": "Manufac. & Indust. - Safety & Dependability 8.0",
            "dsi": "Dependability and Safety Instrument (DSI)",
        }
        by_name = {assessment.name: assessment for assessment in self.catalog}
        for alias, name in aliases.items():
            if re.search(rf"\b{re.escape(alias)}\b", t) and name in by_name:
                matches.append((100, by_name[name]))
        for assessment in self.catalog:
            name = assessment.name.lower()
            base = re.sub(r"\s*\(new\)", "", name)
            if name in t or base in t:
                matches.append((len(base), assessment))
        dedup: dict[str, tuple[int, Assessment]] = {}
        for score, assessment in matches:
            dedup[assessment.name] = max(dedup.get(assessment.name, (0, assessment)), (score, assessment), key=lambda x: x[0])
        return [item[1] for item in sorted(dedup.values(), key=lambda x: -x[0])]

    def _asks_for_shorter_opq_alternative(self, latest: str, context: str) -> bool:
        latest_l = latest.lower()
        context_l = context.lower()
        return "opq" in context_l and "shorter" in latest_l and any(
            word in latest_l for word in ("replace", "alternative", "remove")
        )

    def _role_hint(self, constraints: ConversationConstraints) -> str:
        if constraints.role:
            return constraints.role
        text = constraints.raw_context.lower()
        for role in ("java developer", "python developer", "software engineer", "data analyst", "qa tester", "sales", "manager"):
            if role in text:
                return role
        return ""


def type_text(test_type: str) -> str:
    return "/".join(TYPE_LABELS.get(code, code) for code in test_type.split())
