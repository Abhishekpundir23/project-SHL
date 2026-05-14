from __future__ import annotations

import json
from pathlib import Path

import httpx

SOURCE_URL = "https://tcp-us-prod-rnd.shl.com/voiceRater/shl-ai-hiring/shl_product_catalog.json"
OUT = Path(__file__).resolve().parents[1] / "app" / "data" / "shl_catalog.json"
RAW_OUT = Path(__file__).resolve().parents[1] / "app" / "data" / "shl_product_catalog_raw.json"

TYPE_CODES = {
    "Ability & Aptitude": "A",
    "Biodata & Situational Judgment": "B",
    "Biodata & Situational Judgement": "B",
    "Competencies": "C",
    "Development & 360": "D",
    "Assessment Exercises": "E",
    "Knowledge & Skills": "K",
    "Personality & Behavior": "P",
    "Simulations": "S",
}


def repair_json(text: str) -> str:
    """The provided catalog occasionally contains raw line breaks inside strings."""
    out: list[str] = []
    in_string = False
    escaped = False
    for ch in text:
        if in_string:
            if escaped:
                out.append(ch)
                escaped = False
            elif ch == "\\":
                out.append(ch)
                escaped = True
            elif ch == '"':
                out.append(ch)
                in_string = False
            elif ch in "\r\n\t":
                out.append(" ")
            else:
                out.append(ch)
        else:
            out.append(ch)
            if ch == '"':
                in_string = True
    return "".join(out)


def normalize(row: dict) -> dict[str, object]:
    codes: list[str] = []
    for key in row.get("keys") or []:
        code = TYPE_CODES.get(key)
        if code and code not in codes:
            codes.append(code)
    return {
        "entity_id": row.get("entity_id", ""),
        "name": " ".join(str(row.get("name", "")).split()),
        "url": str(row.get("link", "")).strip(),
        "test_type": " ".join(codes),
        "description": str(row.get("description", "")).strip(),
        "job_levels": ", ".join(row.get("job_levels") or []) or row.get("job_levels_raw", ""),
        "languages": ", ".join(row.get("languages") or []) or row.get("languages_raw", ""),
        "duration": row.get("duration") or row.get("duration_raw", ""),
        "remote": row.get("remote", ""),
        "adaptive": row.get("adaptive", ""),
        "keys": row.get("keys") or [],
    }


def main() -> None:
    headers = {"User-Agent": "Mozilla/5.0 SHL AI hiring assessment recommender"}
    try:
        with httpx.Client(headers=headers, timeout=30, follow_redirects=True) as client:
            response = client.get(SOURCE_URL)
            response.raise_for_status()
        raw_text = response.text
        RAW_OUT.write_text(raw_text + "\n", encoding="utf-8")
    except httpx.HTTPError as exc:
        if not RAW_OUT.exists():
            raise RuntimeError(f"Could not download catalog and no local snapshot exists: {exc}") from exc
        raw_text = RAW_OUT.read_text(encoding="utf-8")
        print(f"Using bundled raw catalog snapshot because download failed: {exc}")
    raw_rows = json.loads(repair_json(raw_text))
    rows = [normalize(row) for row in raw_rows]
    rows = [row for row in rows if row["name"] and row["url"] and row["test_type"]]
    OUT.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(rows)} Individual Test Solutions to {OUT}")


if __name__ == "__main__":
    main()
