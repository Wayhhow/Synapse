import ast
from pydantic import BaseModel, Field
from typing import Type, Optional
from core.base import BaseSkill


class CalculatorArgs(BaseModel):
    expression: str = Field(..., description="Mathematical expression to evaluate, e.g. '2 + 3 * 4'.")


class CalculatorResponse(BaseModel):
    result: float
    expression: str
    error: Optional[str] = None


_ALLOWED_NODES = (
    ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow,
    ast.USub, ast.UAdd, ast.Mod,
)


class CalculatorSkill(BaseSkill):
    @property
    def name(self) -> str:
        return "calculator_skill"

    @property
    def description(self) -> str:
        return "Safely evaluate mathematical expressions. Trigger words: calculate, compute, math, evaluate expression, 计算, 数学"

    @property
    def expected_args(self) -> Type[BaseModel]:
        return CalculatorArgs

    @property
    def expected_response_type(self) -> Type[BaseModel]:
        return CalculatorResponse

    async def execute(self, **kwargs) -> CalculatorResponse:
        args = self.expected_args(**kwargs)
        try:
            # Bug-13 fix: guard against CPU-exhaustion DoS. A 200-char cap
            # blocks pathological inputs like "2 ** 99999999 ** 99999999 ..."
            # from ever reaching the AST walker. The cap is generous enough
            # for any reasonable human-written expression.
            if len(args.expression) > 200:
                return CalculatorResponse(
                    result=0.0,
                    expression=args.expression,
                    error="expression too long (max 200 characters)",
                )
            tree = ast.parse(args.expression, mode="eval")
            for node in ast.walk(tree):
                if not isinstance(node, _ALLOWED_NODES):
                    return CalculatorResponse(
                        result=0.0,
                        expression=args.expression,
                        error=f"Disallowed expression element: {type(node).__name__}"
                    )
            # Bug-13 fix: ast.Pow allows `2 ** 99999999` to consume CPU even
            # within the 10s sandbox timeout. Cap the exponent for `**`:
            # if either operand is a non-constant (we can't predict its value
            # at parse time) or the right-hand constant exceeds 1e6, reject.
            for node in ast.walk(tree):
                if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Pow):
                    right = node.right
                    if not isinstance(right, ast.Constant) or not isinstance(right.value, (int, float)):
                        return CalculatorResponse(
                            result=0.0,
                            expression=args.expression,
                            error="exponent must be a constant",
                        )
                    if abs(right.value) > 1e6:
                        return CalculatorResponse(
                            result=0.0,
                            expression=args.expression,
                            error="exponent too large (max 1e6)",
                        )
            result = eval(compile(tree, "<calc>", "eval"))
            return CalculatorResponse(result=float(result), expression=args.expression)
        except Exception as e:
            return CalculatorResponse(result=0.0, expression=args.expression, error=str(e))
