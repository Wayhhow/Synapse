"""
Regression coverage for the 5-dimension ``SkillEvaluator`` scoring.

Covers:
- Bug-7 (dim3): error-handling score is computed from the skill code's
  try/except blocks and `error` response field — NOT from runtime last_error.
- Bug-8 (dim4): specificity score rewards descriptions that declare explicit
  "Trigger words:" per the synapse-skill-eval spec.
- Bug-28 (dim5): antipattern detection uses AST resolution so obfuscated
  calls (extra whitespace) are still caught.
- End-to-end ``evaluate(skill_name)`` produces sensible totals.
"""
import os


from core.skill_registry import SkillRegistry
from meta.skill_evaluator import SkillEvaluator


def _evaluator_with_tmp_registry(tmpdir):
    registry = SkillRegistry(persist_path=os.path.join(str(tmpdir), "registry.json"))
    return SkillEvaluator(registry=registry, skills_dir=str(tmpdir))


# --- Bug-7: dim3 error handling ---

def test_b07_dim3_full_score_with_try_except_and_error_field(tmpdir):
    """
    Bug-7 regression: a skill that has BOTH a try/except block AND an `error`
    field on its response model should score the maximum 20 points on dim3,
    regardless of any runtime last_error state.
    """
    code = (
        "from pydantic import BaseModel\n"
        "from typing import Optional\n"
        "from core.base import BaseSkill\n"
        "class XArgs(BaseModel):\n"
        "    pass\n"
        "class XResp(BaseModel):\n"
        "    result: str\n"
        "    error: Optional[str] = None\n"
        "class XSkill(BaseSkill):\n"
        "    @property\n"
        "    def name(self): return 'x_skill'\n"
        "    @property\n"
        "    def description(self): return 'x'\n"
        "    @property\n"
        "    def expected_args(self): return XArgs\n"
        "    @property\n"
        "    def expected_response_type(self): return XResp\n"
        "    async def execute(self, **kwargs):\n"
        "        try:\n"
        "            return XResp(result='ok')\n"
        "        except Exception as e:\n"
        "            return XResp(result='', error=str(e))\n"
    )
    evaluator = _evaluator_with_tmp_registry(tmpdir)
    assert evaluator._check_error_handling_from_code(code) == 20.0


def test_b07_dim3_partial_score_with_only_try_except(tmpdir):
    code = (
        "from pydantic import BaseModel\n"
        "from core.base import BaseSkill\n"
        "class XArgs(BaseModel):\n"
        "    pass\n"
        "class XResp(BaseModel):\n"
        "    result: str\n"
        "class XSkill(BaseSkill):\n"
        "    @property\n"
        "    def name(self): return 'x_skill'\n"
        "    @property\n"
        "    def description(self): return 'x'\n"
        "    @property\n"
        "    def expected_args(self): return XArgs\n"
        "    @property\n"
        "    def expected_response_type(self): return XResp\n"
        "    async def execute(self, **kwargs):\n"
        "        try:\n"
        "            return XResp(result='ok')\n"
        "        except Exception:\n"
        "            return XResp(result='fail')\n"
    )
    evaluator = _evaluator_with_tmp_registry(tmpdir)
    assert evaluator._check_error_handling_from_code(code) == 15.0


def test_b07_dim3_partial_score_with_only_error_field(tmpdir):
    code = (
        "from pydantic import BaseModel\n"
        "from typing import Optional\n"
        "from core.base import BaseSkill\n"
        "class XArgs(BaseModel):\n"
        "    pass\n"
        "class XResp(BaseModel):\n"
        "    result: str\n"
        "    error: Optional[str] = None\n"
        "class XSkill(BaseSkill):\n"
        "    @property\n"
        "    def name(self): return 'x_skill'\n"
        "    @property\n"
        "    def description(self): return 'x'\n"
        "    @property\n"
        "    def expected_args(self): return XArgs\n"
        "    @property\n"
        "    def expected_response_type(self): return XResp\n"
        "    async def execute(self, **kwargs):\n"
        "        return XResp(result='ok')\n"
    )
    evaluator = _evaluator_with_tmp_registry(tmpdir)
    assert evaluator._check_error_handling_from_code(code) == 15.0


def test_b07_dim3_minimum_score_without_either(tmpdir):
    code = (
        "from pydantic import BaseModel\n"
        "from core.base import BaseSkill\n"
        "class XArgs(BaseModel):\n"
        "    pass\n"
        "class XResp(BaseModel):\n"
        "    result: str\n"
        "class XSkill(BaseSkill):\n"
        "    @property\n"
        "    def name(self): return 'x_skill'\n"
        "    @property\n"
        "    def description(self): return 'x'\n"
        "    @property\n"
        "    def expected_args(self): return XArgs\n"
        "    @property\n"
        "    def expected_response_type(self): return XResp\n"
        "    async def execute(self, **kwargs):\n"
        "        return XResp(result='ok')\n"
    )
    evaluator = _evaluator_with_tmp_registry(tmpdir)
    assert evaluator._check_error_handling_from_code(code) == 5.0


def test_b07_dim3_does_not_consider_runtime_last_error(tmpdir):
    """
    Bug-7 regression: a skill that previously failed (last_error set in the
    registry) must NOT be penalized on dim3 just because of that runtime
    failure. The score is computed from the code, not from runtime state.
    """
    code = (
        "from pydantic import BaseModel\n"
        "from core.base import BaseSkill\n"
        "class XArgs(BaseModel):\n"
        "    pass\n"
        "class XResp(BaseModel):\n"
        "    result: str\n"
        "class XSkill(BaseSkill):\n"
        "    @property\n"
        "    def name(self): return 'x_skill'\n"
        "    @property\n"
        "    def description(self): return 'x'\n"
        "    @property\n"
        "    def expected_args(self): return XArgs\n"
        "    @property\n"
        "    def expected_response_type(self): return XResp\n"
        "    async def execute(self, **kwargs):\n"
        "        try:\n"
        "            return XResp(result='ok')\n"
        "        except Exception:\n"
        "            return XResp(result='fail')\n"
    )
    evaluator = _evaluator_with_tmp_registry(tmpdir)
    evaluator.registry.register("x_skill", "x")
    # Simulate a prior failure.
    evaluator.registry.record_execution("x_skill", success=False, error="previous boom")
    # dim3 still scores 15 (try/except, no error field) — last_error ignored.
    assert evaluator._check_error_handling_from_code(code) == 15.0


# --- Bug-8: dim4 specificity ---

def test_b08_dim4_full_score_with_two_trigger_words(tmpdir):
    evaluator = _evaluator_with_tmp_registry(tmpdir)
    desc = "Get the current weather. Trigger words: weather, temperature, forecast"
    assert evaluator._check_specificity_from_description(desc) == 15.0


def test_b08_dim4_partial_score_with_single_trigger_word(tmpdir):
    evaluator = _evaluator_with_tmp_registry(tmpdir)
    desc = "Get the current weather. Trigger words: weather"
    assert evaluator._check_specificity_from_description(desc) == 10.0


def test_b08_dim4_falls_back_to_length_when_no_trigger_words(tmpdir):
    """
    Bug-8 fallback: a description that does not declare trigger words still
    gets partial credit if it's at least non-trivially long. This keeps
    older skills that haven't adopted the convention from regressing to 0.
    """
    evaluator = _evaluator_with_tmp_registry(tmpdir)
    long_desc = "a complete skill for testing"
    assert evaluator._check_specificity_from_description(long_desc) == 10.0


def test_b08_dim4_short_description_without_trigger_words_scores_minimum(tmpdir):
    evaluator = _evaluator_with_tmp_registry(tmpdir)
    assert evaluator._check_specificity_from_description("x") == 5.0


def test_b08_dim4_empty_description_scores_minimum(tmpdir):
    evaluator = _evaluator_with_tmp_registry(tmpdir)
    assert evaluator._check_specificity_from_description("") == 5.0


def test_b08_dim4_case_insensitive_trigger_marker(tmpdir):
    """
    Bug-8: "Trigger words:" matching is case-insensitive so descriptions can
    use either "Trigger words:" or "trigger words:" variants.
    """
    evaluator = _evaluator_with_tmp_registry(tmpdir)
    desc = "skill. trigger words: a, b, c"
    assert evaluator._check_specificity_from_description(desc) == 15.0


# --- Bug-28: dim5 antipattern AST detection ---

def test_b28_dim5_clean_code_scores_full(tmpdir):
    evaluator = _evaluator_with_tmp_registry(tmpdir)
    clean = (
        "from pydantic import BaseModel\n"
        "from core.base import BaseSkill\n"
        "class XArgs(BaseModel):\n"
        "    pass\n"
        "class XResp(BaseModel):\n"
        "    result: str\n"
        "class XSkill(BaseSkill):\n"
        "    @property\n"
        "    def name(self): return 'x_skill'\n"
        "    @property\n"
        "    def description(self): return 'x'\n"
        "    @property\n"
        "    def expected_args(self): return XArgs\n"
        "    @property\n"
        "    def expected_response_type(self): return XResp\n"
        "    async def execute(self, **kwargs):\n"
        "        return XResp(result='ok')\n"
    )
    assert evaluator.check_antipattern_ast(clean) == 15.0


def test_b28_dim5_obfuscated_eval_caught(tmpdir):
    """
    Bug-28 regression: extra whitespace inside the call does not defeat the
    AST walker (the old substring matcher would have missed `eval  (`).
    """
    evaluator = _evaluator_with_tmp_registry(tmpdir)
    code = "x = eval  ('1')\n"
    assert evaluator.check_antipattern_ast(code) == 10.0  # 1 hit → 10


def test_b28_dim5_dangerous_attribute_call_caught(tmpdir):
    """
    Bug-28 regression: os.system is detected via attribute resolution,
    which the substring matcher only caught when the literal 'os.system'
    appeared (now also handles `os.system  (...)` with extra spaces).
    """
    evaluator = _evaluator_with_tmp_registry(tmpdir)
    code = "import os\nos.system  ('rm -rf /')\n"
    assert evaluator.check_antipattern_ast(code) == 10.0


def test_b28_dim5_multiple_dangerous_calls_clamped_to_zero(tmpdir):
    evaluator = _evaluator_with_tmp_registry(tmpdir)
    code = (
        "eval('1')\n"
        "exec('2')\n"
        "compile('3', '<s>', 'exec')\n"
    )
    assert evaluator.check_antipattern_ast(code) == 0.0


# --- End-to-end evaluate(skill_name) ---

def test_evaluate_with_full_skill_picks_up_trigger_words_score(tmpdir):
    """
    A skill that declares trigger words AND has try/except + error field
    should score higher than one that doesn't, even with the same
    success_count.
    """
    skills_dir = str(tmpdir)
    code = (
        "from pydantic import BaseModel\n"
        "from typing import Optional\n"
        "from core.base import BaseSkill\n"
        "class XArgs(BaseModel):\n"
        "    pass\n"
        "class XResp(BaseModel):\n"
        "    result: str\n"
        "    error: Optional[str] = None\n"
        "class XSkill(BaseSkill):\n"
        "    @property\n"
        "    def name(self): return 'x_skill'\n"
        "    @property\n"
        "    def description(self): return 'does x. Trigger words: alpha, beta'\n"
        "    @property\n"
        "    def expected_args(self): return XArgs\n"
        "    @property\n"
        "    def expected_response_type(self): return XResp\n"
        "    async def execute(self, **kwargs):\n"
        "        try:\n"
        "            return XResp(result='ok')\n"
        "        except Exception as e:\n"
        "            return XResp(result='', error=str(e))\n"
    )
    with open(os.path.join(skills_dir, "x_skill.py"), "w", encoding="utf-8") as f:
        f.write(code)

    registry = SkillRegistry(persist_path=os.path.join(str(tmpdir), "registry.json"))
    registry.register("x_skill", "does x. Trigger words: alpha, beta")
    registry.record_execution("x_skill", success=True, execution_time=0.05)

    evaluator = SkillEvaluator(registry=registry, skills_dir=skills_dir)
    score = evaluator.evaluate("x_skill")
    # dim1 = 20, dim2 = 30 (1/1), dim3 = 20 (try + error), dim4 = 15 (2 trigger words), dim5 = 15
    assert score == 100.0
