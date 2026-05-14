from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent import SHLAgent
from app.models import Message

TRACE_DIR = Path(r"D:\Download\GenAI_SampleConversations")


def extract_user_turns(text: str) -> list[str]:
    turns: list[str] = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == "**User**":
            block: list[str] = []
            for following in lines[i + 1 :]:
                if following.startswith("**Agent**") or following.startswith("### Turn"):
                    break
                if following.startswith(">"):
                    block.append(following.lstrip("> ").strip())
                elif block and not following.strip():
                    break
            turns.append("\n".join(block).strip())
    return [turn for turn in turns if turn]


def extract_expected_names(text: str) -> list[str]:
    names: list[str] = []
    for line in text.splitlines():
        match = re.match(r"\|\s*\d+\s*\|\s*(.*?)\s*\|", line)
        if match:
            name = (
                match.group(1)
                .replace("â€“", "–")
                .replace("â€”", "—")
                .replace("SVAR Spoken English (US) (New)", "SVAR - Spoken English (US) (New)")
                .replace(
                    "Entry Level Customer Serv - Retail & Contact Center",
                    "Entry Level Customer Serv-Retail & Contact Center",
                )
                .replace("Microsoft Excel 365 (New)", "Microsoft Excel 365 - Essentials (New)")
            )
            if name not in names:
                names.append(name)
    return names


def main() -> None:
    agent = SHLAgent()
    total_recall = 0.0
    count = 0
    for path in sorted(TRACE_DIR.glob("C*.md")):
        text = path.read_text(encoding="utf-8")
        expected = extract_expected_names(text)
        user_turns = extract_user_turns(text)
        messages: list[Message] = []
        for turn in user_turns[-8:]:
            messages.append(Message(role="user", content=turn))
            messages.append(Message(role="assistant", content="Acknowledged."))
        messages = messages[:-1]
        response = agent.respond(messages)
        actual = [item.name for item in response.recommendations]
        hits = len(set(expected) & set(actual))
        recall = hits / len(expected) if expected else 1.0
        total_recall += recall
        count += 1
        print(f"{path.name}: recall={recall:.2f} hits={hits}/{len(expected)}")
        print("  expected:", expected)
        print("  actual:  ", actual)
    print(f"Mean Recall@10: {total_recall / count:.2f}")


if __name__ == "__main__":
    main()
