"""
Export Synapse skills as `SKILL.md` folders compatible with the
`Agent Skills open standard <https://agentskills.io>`_ (introduced by
Anthropic in Oct 2025, published as an open standard in Dec 2025 and
supported by Claude Code, Cursor, Codex CLI and 20+ other agents).

Each exported skill is a directory::

    <out>/<skill_name>/
    ├── SKILL.md          # YAML frontmatter (name/description) + docs
    └── skill.py          # the executable skill source

This makes every skill Synapse auto-generates instantly portable to the
wider agent ecosystem — and vice versa, human-authored SKILL.md packages
document exactly the metadata (name, description, trigger conditions) our
router relies on.
"""

import os
import re
from typing import Dict, Optional

from core.base import BaseSkill


def _yaml_escape(value: str) -> str:
    """Quote a string for YAML frontmatter (single-quote style)."""
    return "'" + value.replace("'", "''") + "'"


def _inspect_skill(skill: BaseSkill) -> Dict[str, Optional[str]]:
    """Extract arg/response field docs from the Pydantic models."""
    fields: Dict[str, str] = {}
    try:
        schema = skill.expected_args.model_json_schema()
        for name, prop in schema.get("properties", {}).items():
            desc = prop.get("description", "")
            ftype = prop.get("type", "any")
            fields[name] = f"{ftype}" + (f" — {desc}" if desc else "")
    except Exception:
        fields = {}
    return fields


def build_skill_md(skill: BaseSkill) -> str:
    """Render the SKILL.md document for one skill."""
    args = _inspect_skill(skill)
    arg_lines = "\n".join(f"- `{name}`: {desc}" for name, desc in args.items()) or "- (none)"
    try:
        response_fields = list(skill.expected_response_type.model_json_schema().get("properties", {}).keys())
    except Exception:
        response_fields = []
    response_lines = ", ".join(f"`{f}`" for f in response_fields) or "(none)"

    frontmatter = (
        "---\n"
        f"name: {_yaml_escape(skill.name)}\n"
        f"description: {_yaml_escape(skill.description)}\n"
        "---\n"
    )
    body = f"""# {skill.name}

{skill.description}

## Usage

Call this skill with the following arguments:

{arg_lines}

The skill responds with a structured object containing: {response_lines}.

## Source

The complete, executable implementation lives in `skill.py` next to this file.
"""
    return frontmatter + body


class SkillExporter:
    """Writes SKILL.md-standard folders for all (or selected) skills."""

    def __init__(self, skills: Dict[str, BaseSkill], skills_dir: str = "skills"):
        self.skills = skills
        self.skills_dir = skills_dir

    def _read_source(self, skill: BaseSkill) -> str:
        """Best-effort read of the module source from the skills directory."""
        module = type(skill).__module__
        filename = module.split(".")[-1]
        path = os.path.join(self.skills_dir, f"{filename}.py")
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        return f"# Source for '{skill.name}' not found (module: {module})"

    def export(self, out_dir: str, skill_names: Optional[list] = None) -> list:
        """Export skills; returns the list of exported skill names."""
        os.makedirs(out_dir, exist_ok=True)
        exported = []
        for name, skill in self.skills.items():
            if skill_names is not None and name not in skill_names:
                continue
            source = self._read_source(skill)
            dest = os.path.join(out_dir, re.sub(r"[^A-Za-z0-9_\-]", "_", name))
            os.makedirs(dest, exist_ok=True)
            with open(os.path.join(dest, "SKILL.md"), "w", encoding="utf-8") as f:
                f.write(build_skill_md(skill))
            with open(os.path.join(dest, "skill.py"), "w", encoding="utf-8") as f:
                f.write(source)
            exported.append(name)
        return exported
