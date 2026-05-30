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
            tree = ast.parse(args.expression, mode="eval")
            for node in ast.walk(tree):
                if not isinstance(node, _ALLOWED_NODES):
                    return CalculatorResponse(
                        result=0.0,
                        expression=args.expression,
                        error=f"Disallowed expression element: {type(node).__name__}"
                    )
            result = eval(compile(tree, "<calc>", "eval"))
            return CalculatorResponse(result=float(result), expression=args.expression)
        except Exception as e:
            return CalculatorResponse(result=0.0, expression=args.expression, error=str(e))
