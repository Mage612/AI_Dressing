from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import re

from app import settings


STYLING_CONTEXT_DIR = Path(__file__).resolve().parents[1] / "skills" / "styling"


@dataclass(frozen=True)
class StylingContext:
    skill_yaml: str
    knowledge_markdown: str
    skill_version: str


@lru_cache(maxsize=1)
def load_styling_context() -> StylingContext:
    skill_path = STYLING_CONTEXT_DIR / "styling_skill.yaml"
    knowledge_path = STYLING_CONTEXT_DIR / "styling_knowledge.md"

    missing = [str(path) for path in (skill_path, knowledge_path) if not path.exists()]
    if missing:
        raise RuntimeError("Missing styling context files: " + ", ".join(missing))

    skill_yaml = skill_path.read_text(encoding="utf-8")
    knowledge_markdown = knowledge_path.read_text(encoding="utf-8")
    return StylingContext(
        skill_yaml=skill_yaml,
        knowledge_markdown=knowledge_markdown,
        skill_version=_detect_skill_version(skill_yaml, knowledge_markdown),
    )


def _detect_skill_version(skill_yaml: str, knowledge_markdown: str) -> str:
    yaml_match = re.search(r'(?im)^\s*version:\s*["\']?([^"\'\s]+)', skill_yaml)
    if yaml_match:
        return _normalize_version(yaml_match.group(1))

    md_match = re.search(r"(?im)^Version:\s*([^\s]+)", knowledge_markdown)
    if md_match:
        return _normalize_version(md_match.group(1))

    return settings.STYLING_SKILL_VERSION


def _normalize_version(value: str) -> str:
    value = value.strip()
    return value if value.startswith("v") else f"v{value}"
