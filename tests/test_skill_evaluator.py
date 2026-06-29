import os
import pytest
from core.skill_registry import SkillRegistry
from meta.skill_evaluator import SkillEvaluator


COMPLETE_SKILL_CODE = (
    "from pydantic import BaseModel\n"
    "from core.base import BaseSkill\n"
    "class MyArgs(BaseModel):\n"
    "    x: int\n"
    "class MyResp(BaseModel):\n"
    "    result: int\n"
    "class MySkill(BaseSkill):\n"
    "    @property\n"
    "    def name(self):\n"
    "        return 'my_skill'\n"
    "    @property\n"
    "    def description(self):\n"
    "        return 'a complete skill for testing'\n"
    "    @property\n"
    "    def expected_args(self):\n"
    "        return MyArgs\n"
    "    @property\n"
    "    def expected_response_type(self):\n"
    "        return MyResp\n"
    "    async def execute(self, **kwargs):\n"
    "        return MyResp(result=kwargs['x'])\n"
)

SKILL_MISSING_EXECUTE_CODE = (
    "from pydantic import BaseModel\n"
    "from core.base import BaseSkill\n"
    "class MyArgs(BaseModel):\n"
    "    x: int\n"
    "class MyResp(BaseModel):\n"
    "    result: int\n"
    "class MySkill(BaseSkill):\n"
    "    @property\n"
    "    def name(self):\n"
    "        return 'my_skill'\n"
    "    @property\n"
    "    def description(self):\n"
    "        return 'a complete skill for testing'\n"
    "    @property\n"
    "    def expected_args(self):\n"
    "        return MyArgs\n"
    "    @property\n"
    "    def expected_response_type(self):\n"
    "        return MyResp\n"
)

NO_BASESKILL_CODE = (
    "class SomethingElse:\n"
    "    pass\n"
)


def _evaluator_with_tmp_registry(tmpdir):
    registry = SkillRegistry(persist_path=os.path.join(str(tmpdir), "registry.json"))
    return SkillEvaluator(registry=registry, skills_dir=str(tmpdir))


# --- _check_structure_from_code ---

def test_check_structure_complete_code(tmpdir):
    evaluator = _evaluator_with_tmp_registry(tmpdir)
    assert evaluator._check_structure_from_code(COMPLETE_SKILL_CODE) == 20.0


def test_check_structure_missing_execute(tmpdir):
    evaluator = _evaluator_with_tmp_registry(tmpdir)
    # 4 of 5 required members present -> 4 * 4 = 16
    assert evaluator._check_structure_from_code(SKILL_MISSING_EXECUTE_CODE) == 16.0


def test_check_structure_no_baseskill_subclass(tmpdir):
    evaluator = _evaluator_with_tmp_registry(tmpdir)
    assert evaluator._check_structure_from_code(NO_BASESKILL_CODE) == 0.0


def test_check_structure_syntax_error(tmpdir):
    evaluator = _evaluator_with_tmp_registry(tmpdir)
    assert evaluator._check_structure_from_code("def broken( # no colon\n    pass") == 0.0


# --- _check_antipattern_from_code ---

def test_check_antipattern_clean(tmpdir):
    evaluator = _evaluator_with_tmp_registry(tmpdir)
    assert evaluator._check_antipattern_from_code(COMPLETE_SKILL_CODE) == 15.0


def test_check_antipattern_single_eval(tmpdir):
    evaluator = _evaluator_with_tmp_registry(tmpdir)
    code = "x = eval('1+1')\n"
    assert evaluator._check_antipattern_from_code(code) == 10.0


def test_check_antipattern_two_hits(tmpdir):
    evaluator = _evaluator_with_tmp_registry(tmpdir)
    code = "x = eval('1+1')\ny = exec('z=1')\n"
    assert evaluator._check_antipattern_from_code(code) == 5.0


def test_check_antipattern_four_hits(tmpdir):
    evaluator = _evaluator_with_tmp_registry(tmpdir)
    code = "eval('1')\nexec('2')\nos.system('3')\nsubprocess.run([])\n"
    assert evaluator._check_antipattern_from_code(code) == 0.0


def test_check_antipattern_clamped_to_zero(tmpdir):
    evaluator = _evaluator_with_tmp_registry(tmpdir)
    # 8 hits would be -25, clamp to 0
    code = (
        "eval('1')\nexec('2')\nos.system('3')\nsubprocess.run([])\n"
        "__import__('os')\ncompile('x', '<s>', 'exec')\nglobals()\nlocals()\n"
    )
    assert evaluator._check_antipattern_from_code(code) == 0.0


# --- evaluate_code_quality ---

def test_evaluate_code_quality_full(tmpdir):
    evaluator = _evaluator_with_tmp_registry(tmpdir)
    # 20 structure + 15 antipattern = 35
    assert evaluator.evaluate_code_quality(COMPLETE_SKILL_CODE) == 35.0


def test_evaluate_code_quality_reduced(tmpdir):
    evaluator = _evaluator_with_tmp_registry(tmpdir)
    code = COMPLETE_SKILL_CODE + "result = eval('1+1')\n"
    # 20 structure + 10 antipattern = 30
    assert evaluator.evaluate_code_quality(code) == 30.0


# --- evaluate(skill_name) end-to-end ---

def test_evaluate_complete_skill_with_stats(tmpdir):
    skills_dir = str(tmpdir)
    filepath = os.path.join(skills_dir, "my_skill.py")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(COMPLETE_SKILL_CODE)

    registry = SkillRegistry(persist_path=os.path.join(str(tmpdir), "registry.json"))
    registry.register("my_skill", "a complete skill for testing")
    registry.record_execution("my_skill", success=True, execution_time=0.05)

    evaluator = SkillEvaluator(registry=registry, skills_dir=skills_dir)
    score = evaluator.evaluate("my_skill")

    # dim1_structure = 20 (complete)
    # dim2_success_rate = 30 * (1/1) = 30
    # dim3_error_handling = 20 (no last_error)
    # dim4_specificity = 15 (description longer than 10 chars)
    # dim5_antipattern = 15 (clean)
    # total = 100
    assert score == 100.0


def test_evaluate_missing_skill_file_returns_zero_for_code_dims(tmpdir):
    skills_dir = str(tmpdir)
    registry = SkillRegistry(persist_path=os.path.join(str(tmpdir), "registry.json"))
    # Register but never write a skill file
    registry.register("ghost_skill", "a skill with no file")
    registry.record_execution("ghost_skill", success=True, execution_time=0.01)

    evaluator = SkillEvaluator(registry=registry, skills_dir=skills_dir)
    score = evaluator.evaluate("ghost_skill")

    # dim1_structure = 0 (no file)
    # dim2_success_rate = 30 * 1.0 = 30
    # dim3_error_handling = 20
    # dim4_specificity = 15 (description > 10 chars)
    # dim5_antipattern = 0 (no file)
    # total = 65
    assert score == 65.0


def test_evaluate_unregistered_skill_returns_zero(tmpdir):
    evaluator = _evaluator_with_tmp_registry(tmpdir)
    assert evaluator.evaluate("never_registered") == 0.0


def test_find_skill_file_by_name_property(tmpdir):
    # File name does not match skill name; should be found via AST scan
    skills_dir = str(tmpdir)
    filepath = os.path.join(skills_dir, "custom_file.py")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(COMPLETE_SKILL_CODE)

    evaluator = _evaluator_with_tmp_registry(tmpdir)
    found = evaluator._find_skill_file("my_skill")
    assert found == filepath


def test_find_skill_file_direct_path(tmpdir):
    skills_dir = str(tmpdir)
    filepath = os.path.join(skills_dir, "my_skill.py")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(COMPLETE_SKILL_CODE)

    evaluator = _evaluator_with_tmp_registry(tmpdir)
    assert evaluator._find_skill_file("my_skill") == filepath


def test_find_skill_file_missing(tmpdir):
    evaluator = _evaluator_with_tmp_registry(tmpdir)
    assert evaluator._find_skill_file("does_not_exist") is None
