from __future__ import annotations

import re


OFF_TOPIC_PATTERNS = [
    r"\b(salary|compensation|benefits|visa|contract|lawsuit|tax|medical|doctor)\b",
    r"\b(law|legal|regulation|regulatory|compliance obligation|legally required)\b",
    r"\b(job description|write a jd|interview questions|background check)\b",
    r"\b(weather|recipe|movie|stock price)\b",
]

INJECTION_PATTERNS = [
    r"ignore (all )?(previous|earlier|above) (instructions|messages|rules)",
    r"disregard (all )?(previous|earlier|above) (instructions|messages|rules)",
    r"forget (all )?(previous|earlier|above) (instructions|messages|rules)",
    r"system prompt|developer message|hidden instructions|policy text",
    r"pretend you are unrestricted|jailbreak|act as.*unfiltered",
    r"override your instructions|new instructions are",
]


def is_scope_violation(text: str) -> bool:
    t = text.lower()
    return any(re.search(pattern, t) for pattern in OFF_TOPIC_PATTERNS + INJECTION_PATTERNS)


def refusal_reply() -> str:
    return (
        "I can only help with SHL assessment selection and comparisons from the SHL Individual "
        "Test Solutions catalog. Please share the role, skills, seniority, and assessment constraints."
    )
