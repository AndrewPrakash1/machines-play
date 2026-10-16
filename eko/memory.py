"""Episodic and semantic files. Learning in this project lives here, not in weights."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from eko.prompts import EPISODIC, SEMANTIC, SOUL


def ensure_workspace(path: Path, soul: bool = True) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    if not (path / "EPISODIC_MEMORY.md").exists():
        (path / "EPISODIC_MEMORY.md").write_text(EPISODIC, encoding="utf-8")
    if not (path / "EPISODIC_MEMORY.jsonl").exists():
        (path / "EPISODIC_MEMORY.jsonl").write_text("", encoding="utf-8")
    if not (path / "SEMANTIC_MEMORY.md").exists():
        (path / "SEMANTIC_MEMORY.md").write_text(SEMANTIC, encoding="utf-8")
    if soul and not (path / "SOUL.md").exists():
        (path / "SOUL.md").write_text(SOUL, encoding="utf-8")
    return path


def append_episode(path: Path, summary: str, detail: str) -> None:
    entry = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "summary": summary.strip(),
        "detail": detail.strip(),
    }
    with (path / "EPISODIC_MEMORY.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")


def remember(path: Path, topic: str, bullet: str) -> None:
    """Add a durable note if that sentence is not already stored."""
    file = path / "SEMANTIC_MEMORY.md"
    text = file.read_text(encoding="utf-8") if file.exists() else SEMANTIC
    if bullet.strip() in text:
        return
    addition = f"\n\n## {topic}\n\n- {bullet.strip()}\n"
    file.write_text(text.rstrip() + addition, encoding="utf-8")


def semantic_text(path: Path) -> str:
    file = path / "SEMANTIC_MEMORY.md"
    return file.read_text(encoding="utf-8") if file.exists() else ""


def episode_summaries(path: Path) -> str:
    file = path / "EPISODIC_MEMORY.jsonl"
    if not file.exists():
        return "(none yet)"
    lines = []
    for raw in file.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            item = json.loads(raw)
        except json.JSONDecodeError:
            continue
        stamp = item.get("timestamp", "")
        lines.append(f"- {stamp} {item.get('summary', '').strip()}")
    return "\n".join(lines) if lines else "(none yet)"


def knows(path: Path, *needles: str) -> bool:
    text = (semantic_text(path) + "\n" + episode_summaries(path)).lower()
    return all(needle.lower() in text for needle in needles)


def spire_recipe(path: Path) -> dict | None:
    import re

    match = re.search(r"spire-throw:\s*(\{.*\})", semantic_text(path))
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or not data.get("jump"):
        return None
    return data


def ablate(path: Path, needle: str) -> int:
    """Delete every line that mentions `needle`. Returns how many lines went away."""
    removed = 0
    needle_l = needle.lower()
    for name in ("SEMANTIC_MEMORY.md", "EPISODIC_MEMORY.jsonl", "EPISODIC_MEMORY.md"):
        file = path / name
        if not file.exists():
            continue
        kept = []
        for line in file.read_text(encoding="utf-8").splitlines(keepends=True):
            if needle_l in line.lower():
                removed += 1
            else:
                kept.append(line)
        file.write_text("".join(kept), encoding="utf-8")
    return removed
