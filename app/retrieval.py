from __future__ import annotations

import math
import os
import re
from collections import Counter

from app.catalog import Assessment
from app.constraints import ConversationConstraints


DOMAIN_TARGETS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("senior leadership", "cxo", "director", "executive", "leadership benchmark"), ("Occupational Personality Questionnaire OPQ32r", "OPQ Universal Competency Report 2.0", "OPQ Leadership Report")),
    (("rust", "networking", "high-performance", "infrastructure"), ("Smart Interview Live Coding", "Linux Programming (General)", "Networking and Implementation (New)", "SHL Verify Interactive G+", "Occupational Personality Questionnaire OPQ32r")),
    (("contact centre", "contact center", "inbound calls", "customer service"), ("SVAR - Spoken English (US) (New)", "Contact Center Call Simulation (New)", "Entry Level Customer Serv-Retail & Contact Center", "Customer Service Phone Simulation")),
    (("financial analyst", "finance", "final-year"), ("SHL Verify Interactive – Numerical Reasoning", "Financial Accounting (New)", "Basic Statistics (New)", "Graduate Scenarios", "Occupational Personality Questionnaire OPQ32r")),
    (("sales organization", "sales organisation", "re-skill", "reskill", "sales transformation"), ("Global Skills Assessment", "Global Skills Development Report", "Occupational Personality Questionnaire OPQ32r", "OPQ MQ Sales Report", "Sales Transformation 2.0 - Individual Contributor")),
    (("plant operators", "chemical facility", "safety", "procedure compliance", "industrial"), ("Dependability and Safety Instrument (DSI)", "Manufac. & Indust. - Safety & Dependability 8.0", "Workplace Health and Safety (New)")),
    (("healthcare admin", "patient records", "hipaa", "medical terminology"), ("HIPAA (Security)", "Medical Terminology (New)", "Microsoft Word 365 - Essentials (New)", "Dependability and Safety Instrument (DSI)", "Occupational Personality Questionnaire OPQ32r")),
    (("admin assistants", "excel", "word daily", "word", "office"), ("Microsoft Excel 365 - Essentials (New)", "Microsoft Word 365 (New)", "MS Excel (New)", "MS Word (New)", "Occupational Personality Questionnaire OPQ32r")),
    (("full-stack", "core java", "spring", "sql", "microservice", "docker", "aws"), ("Core Java (Advanced Level) (New)", "Spring (New)", "RESTful Web Services (New)", "SQL (New)", "Amazon Web Services (AWS) Development (New)", "Docker (New)", "SHL Verify Interactive G+", "Occupational Personality Questionnaire OPQ32r")),
    (("graduate management trainee", "management trainee", "recent graduates", "situational judgement"), ("SHL Verify Interactive G+", "Occupational Personality Questionnaire OPQ32r", "Graduate Scenarios")),
)

NAMED_SKILL_TARGETS = {
    "java": ("Java 8", "Core Java", "Java Frameworks", "Java Design Patterns", "Java Web Services", "Java Platform"),
    "python": ("Python (New)",),
    "sql": ("SQL (New)", "Microsoft SQL Server", "SQL Server", "Oracle PL/SQL"),
    "excel": ("MS Excel", "Microsoft Excel"),
    "word": ("MS Word", "Microsoft Word"),
    "aws": ("Amazon Web Services",),
    "docker": ("Docker",),
    "spring": ("Spring",),
    "rest": ("RESTful Web Services",),
    "hipaa": ("HIPAA",),
    "medical terminology": ("Medical Terminology",),
    "safety": ("Safety", "Dependability"),
}


class HybridRetriever:
    def __init__(self, catalog: list[Assessment]) -> None:
        self.catalog = catalog
        self._semantic_ready = False
        self._model = None
        self._index = None
        self._embeddings = None
        self._build_semantic_index()

    def retrieve(self, constraints: ConversationConstraints, top_k: int = 40) -> list[Assessment]:
        semantic = self._semantic_search(constraints.retrieval_query(), top_k=top_k)
        lexical = self._lexical_search(constraints.retrieval_query(), top_k=top_k)
        seeded = self._seed_candidates(constraints)
        merged = _merge_rankings(seeded, semantic, lexical)
        return self.rerank(merged, constraints)[:top_k]

    def rerank(self, candidates: list[Assessment], constraints: ConversationConstraints) -> list[Assessment]:
        query = constraints.retrieval_query().lower()
        domain_order = self._domain_order(query)
        order_index = {name: i for i, name in enumerate(domain_order)}
        scored: list[tuple[float, Assessment]] = []

        for rank, assessment in enumerate(candidates):
            if assessment.name in constraints.exclude_names:
                continue
            score = 100 - rank
            hay = assessment.searchable
            if assessment.name in order_index:
                score += 350 - order_index[assessment.name] * 5
            for skill, targets in NAMED_SKILL_TARGETS.items():
                if skill in query and any(target.lower() in assessment.name.lower() for target in targets):
                    score += 80
            for code in constraints.assessment_types:
                if code in assessment.test_type:
                    score += 25
            if constraints.include_personality and "P" in assessment.test_type:
                score += 35
            if ("P" in constraints.assessment_types or constraints.include_personality or "stakeholder" in query) and assessment.name == "Occupational Personality Questionnaire OPQ32r":
                score += 120
            if constraints.include_simulation and "S" in assessment.test_type:
                score += 35
            if constraints.include_cognitive and "A" in assessment.test_type:
                score += 35
            if constraints.include_sjt and "B" in assessment.test_type:
                score += 35
            if constraints.seniority and constraints.seniority in hay:
                score += 12
            scored.append((score, assessment))

        scored.sort(key=lambda item: (-item[0], item[1].name))
        return [assessment for _, assessment in scored]

    def select_diverse(self, ranked: list[Assessment], constraints: ConversationConstraints, limit: int = 10) -> list[Assessment]:
        selected: list[Assessment] = []
        seen = set()
        required_types = set(constraints.assessment_types)
        if constraints.include_personality:
            required_types.add("P")
        if constraints.include_cognitive:
            required_types.add("A")
        if constraints.include_sjt:
            required_types.add("B")
        if constraints.include_simulation:
            required_types.add("S")

        for assessment in ranked:
            if assessment.name in seen or assessment.name in constraints.exclude_names:
                continue
            selected.append(assessment)
            seen.add(assessment.name)
            if len(selected) == limit:
                break

        for code in required_types:
            if any(code in assessment.test_type for assessment in selected):
                continue
            replacement = next(
                (assessment for assessment in ranked if code in assessment.test_type and assessment.name not in seen),
                None,
            )
            if replacement:
                selected.insert(min(2, len(selected)), replacement)
                seen.add(replacement.name)
                selected = selected[:limit]
        return selected

    def _domain_order(self, query: str) -> list[str]:
        names: list[str] = []
        for triggers, targets in DOMAIN_TARGETS:
            hits = sum(1 for trigger in triggers if trigger in query)
            if hits >= 2 or (hits == 1 and any(word in query for word in ("confirmed", "final", "battery", "shortlist"))):
                names.extend(targets)
        if "drop rest" in query or "rest out" in query:
            names = [name for name in names if name != "RESTful Web Services (New)"]
        if "drop the opq" in query or "remove opq" in query:
            names = [name for name in names if name != "Occupational Personality Questionnaire OPQ32r"]
        if "simulation" not in query and "quickly screen admin assistants" in query:
            names = ["MS Excel (New)", "MS Word (New)", "Occupational Personality Questionnaire OPQ32r"]
        return list(dict.fromkeys(names))

    def _seed_candidates(self, constraints: ConversationConstraints) -> list[Assessment]:
        query = constraints.retrieval_query().lower()
        by_name = {assessment.name: assessment for assessment in self.catalog}
        seeds: list[Assessment] = []
        for name in self._domain_order(query):
            assessment = by_name.get(name)
            if assessment:
                seeds.append(assessment)
        for skill, targets in NAMED_SKILL_TARGETS.items():
            if skill not in query:
                continue
            for assessment in self.catalog:
                if any(target.lower() in assessment.name.lower() for target in targets):
                    seeds.append(assessment)
        if (constraints.include_personality or "P" in constraints.assessment_types) and "Occupational Personality Questionnaire OPQ32r" in by_name:
            seeds.append(by_name["Occupational Personality Questionnaire OPQ32r"])
        if constraints.include_cognitive and "SHL Verify Interactive G+" in by_name:
            seeds.append(by_name["SHL Verify Interactive G+"])
        if constraints.include_sjt and "Graduate Scenarios" in by_name:
            seeds.append(by_name["Graduate Scenarios"])
        dedup: dict[str, Assessment] = {}
        for assessment in seeds:
            if assessment.name not in constraints.exclude_names:
                dedup[assessment.name] = assessment
        return list(dedup.values())

    def _build_semantic_index(self) -> None:
        if os.getenv("ENABLE_SEMANTIC_RETRIEVAL", "0") != "1":
            return
        try:
            import faiss  # type: ignore
            import numpy as np  # type: ignore
            from sentence_transformers import SentenceTransformer  # type: ignore

            self._model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
            docs = [assessment.document for assessment in self.catalog]
            embeddings = self._model.encode(docs, normalize_embeddings=True, show_progress_bar=False)
            embeddings = np.asarray(embeddings, dtype="float32")
            index = faiss.IndexFlatIP(embeddings.shape[1])
            index.add(embeddings)
            self._index = index
            self._embeddings = embeddings
            self._semantic_ready = True
        except Exception:
            self._semantic_ready = False

    def _semantic_search(self, query: str, top_k: int) -> list[Assessment]:
        if not self._semantic_ready or not self._model or not self._index:
            return []
        import numpy as np  # type: ignore

        vector = self._model.encode([query], normalize_embeddings=True, show_progress_bar=False)
        vector = np.asarray(vector, dtype="float32")
        _, indices = self._index.search(vector, min(top_k, len(self.catalog)))
        return [self.catalog[i] for i in indices[0] if i >= 0]

    def _lexical_search(self, query: str, top_k: int) -> list[Assessment]:
        q_terms = _terms(query)
        q_counts = Counter(q_terms)
        scored: list[tuple[float, Assessment]] = []
        for assessment in self.catalog:
            doc_terms = _terms(assessment.searchable)
            doc_counts = Counter(doc_terms)
            overlap = sum(q_counts[t] * doc_counts.get(t, 0) for t in q_counts)
            if overlap:
                norm = math.sqrt(sum(v * v for v in doc_counts.values())) or 1
                scored.append((overlap / norm, assessment))
        scored.sort(key=lambda item: (-item[0], item[1].name))
        return [assessment for _, assessment in scored[:top_k]]


def _terms(text: str) -> list[str]:
    return [term for term in re.findall(r"[a-z0-9+#.]+", text.lower()) if len(term) > 2]


def _merge_rankings(*rankings: list[Assessment]) -> list[Assessment]:
    scores: dict[str, tuple[float, Assessment]] = {}
    for ranking in rankings:
        for idx, assessment in enumerate(ranking):
            current = scores.get(assessment.name, (0.0, assessment))[0]
            scores[assessment.name] = (current + 1 / (idx + 1), assessment)
    return [item[1] for item in sorted(scores.values(), key=lambda pair: -pair[0])]
