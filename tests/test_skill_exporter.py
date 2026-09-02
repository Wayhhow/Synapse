"""Tests for the SKILL.md-standard exporter (meta.skill_exporter)."""
import os

from meta.skill_exporter import SkillExporter, build_skill_md
from core.config import SynapseConfig
from core.memory import Memory
from core.skill_registry import SkillRegistry
from router.router import SkillRouter


def _make_router(tmpdir, trace=False):
    registry = SkillRegistry(persist_path=os.path.join(str(tmpdir), "r.json"))
    config = SynapseConfig(trace_enabled=trace)
    router = SkillRouter(api_key="test-api-key", registry=registry, config=config)
    router.memory = Memory(max_history=10)
    return router


def test_export_all_skills_creates_standard_folders(tmpdir):
    router = _make_router(tmpdir)
    out = os.path.join(str(tmpdir), "export")
    exported = SkillExporter(router.skills, router.skills_dir).export(out)

    assert len(exported) == 6
    for name in exported:
        folder = os.path.join(out, name)
        assert os.path.isfile(os.path.join(folder, "SKILL.md"))
        assert os.path.isfile(os.path.join(folder, "skill.py"))
        with open(os.path.join(folder, "SKILL.md"), encoding="utf-8") as f:
            content = f.read()
        assert content.startswith("---\n")
        assert f"name: '{name}'" in content
        assert "## Usage" in content


def test_export_selected_skills_only(tmpdir):
    router = _make_router(tmpdir)
    out = os.path.join(str(tmpdir), "export")
    exported = SkillExporter(router.skills, router.skills_dir).export(out, skill_names=["weather_skill"])
    assert exported == ["weather_skill"]


def test_skill_md_includes_argument_docs(tmpdir):
    router = _make_router(tmpdir)
    skill = router.skills["calculator_skill"]
    doc = build_skill_md(skill)
    assert "`expression`" in doc
    assert skill.description in doc


def test_exported_skill_py_is_valid_python(tmpdir):
    import ast
    router = _make_router(tmpdir)
    out = os.path.join(str(tmpdir), "export")
    SkillExporter(router.skills, router.skills_dir).export(out)
    for name in os.listdir(out):
        src_path = os.path.join(out, name, "skill.py")
        with open(src_path, encoding="utf-8") as f:
            ast.parse(f.read())  # must not raise
