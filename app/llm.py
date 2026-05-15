from __future__ import annotations

import os

import httpx

from app.catalog import Assessment, TYPE_LABELS


GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")


class GroundedFormatter:
    def __init__(self) -> None:
        self.api_key = os.getenv("GROQ_API_KEY", "")

    def recommendation_reply(self, selected: list[Assessment], role_hint: str, query: str) -> str:
        fallback = self._fallback_recommendation_reply(selected, role_hint)
        if not self.api_key:
            return fallback
        context = "\n\n".join(_catalog_block(a) for a in selected[:10])
        prompt = (
            "Write a concise SHL assessment recommendation reply. Use ONLY the catalog context. "
            "Mention why the first few assessments fit the user's needs. Do not invent URLs or products. "
            "Do not output JSON.\n\n"
            f"User need:\n{query}\n\nCatalog context:\n{context}"
        )
        return self._call_groq(prompt, fallback)

    def comparison_reply(self, left: Assessment, right: Assessment, question: str) -> str:
        fallback = (
            f"{left.name} is a {_type_text(left.test_type)} assessment. Catalog description: {left.description} "
            f"{right.name} is a {_type_text(right.test_type)} assessment. Catalog description: {right.description}"
        )
        if not self.api_key:
            return fallback
        prompt = (
            "Answer the comparison using ONLY the provided SHL catalog context. If the catalog does not say "
            "something, say that it is not specified. Do not use outside knowledge.\n\n"
            f"Question: {question}\n\n"
            f"Assessment A:\n{_catalog_block(left)}\n\nAssessment B:\n{_catalog_block(right)}"
        )
        return self._call_groq(prompt, fallback)

    def _call_groq(self, prompt: str, fallback: str) -> str:
        try:
            response = httpx.post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={
                    "model": GROQ_MODEL,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a grounded SHL catalog assistant. Follow the user's API schema indirectly by returning prose only.",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 450,
                },
                timeout=8,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"].strip()
            return content or fallback
        except Exception:
            return fallback

    def _fallback_recommendation_reply(self, selected: list[Assessment], role_hint: str) -> str:
        intro = f"Got it. Here are {len(selected)} SHL Individual Test Solutions"
        if role_hint:
            intro += f" that best match {role_hint}"
        reasons = []
        for assessment in selected[:4]:
            focus = assessment.description.split(".")[0][:120]
            reasons.append(f"{assessment.name} maps to {_type_text(assessment.test_type)}: {focus}.")
        return intro + ". " + " ".join(reasons)


def _catalog_block(assessment: Assessment) -> str:
    return (
        f"Name: {assessment.name}\n"
        f"URL: {assessment.url}\n"
        f"Test type: {assessment.test_type} ({_type_text(assessment.test_type)})\n"
        f"Duration: {assessment.duration}\n"
        f"Languages: {assessment.languages}\n"
        f"Description: {assessment.description}"
    )


def _type_text(test_type: str) -> str:
    return "/".join(TYPE_LABELS.get(code, code) for code in test_type.split())
