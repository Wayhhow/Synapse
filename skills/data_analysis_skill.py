import json
import statistics
from pydantic import BaseModel, Field
from typing import Type, Optional, List, Union
from core.base import BaseSkill


class DataAnalysisArgs(BaseModel):
    data: str = Field(..., description="Comma-separated numbers (e.g. '1,2,3,4,5') OR a JSON array (e.g. '[1,2,3,4,5]').")
    analysis_type: str = Field(default="describe", description="Type of analysis. Currently only 'describe' is supported.")


class DataAnalysisResponse(BaseModel):
    mean: float
    median: float
    std: float
    min: float
    max: float
    count: int
    error: Optional[str] = None


class DataAnalysisSkill(BaseSkill):
    @property
    def name(self) -> str:
        return "data_analysis_skill"

    @property
    def description(self) -> str:
        return "Perform statistical analysis on numerical data. Trigger words: analyze, statistics, data analysis, calculate stats, 统计, 分析"

    @property
    def expected_args(self) -> Type[BaseModel]:
        return DataAnalysisArgs

    @property
    def expected_response_type(self) -> Type[BaseModel]:
        return DataAnalysisResponse

    @staticmethod
    def _parse_numbers(raw: str) -> List[float]:
        """
        Bug-14 fix: accept BOTH the legacy comma-separated format and the
        spec-required JSON array format. Try JSON first (handles `[1,2,3]`,
        `[1, 2.5, 3]`, etc.); fall back to comma-separated splitting on
        failure or when the string does not look like a JSON array.
        """
        stripped = raw.strip()
        # Only attempt JSON parse when the string plausibly looks like a
        # JSON array — this avoids surprising "valueError" messages for
        # plain comma-separated inputs that happen to fail JSON parsing
        # for reasons unrelated to our spec (e.g. trailing comma).
        if stripped.startswith("[") and stripped.endswith("]"):
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, list):
                    numbers: List[float] = []
                    for item in parsed:
                        # `bool` is a subclass of `int` in Python; exclude it
                        # explicitly so `True`/`False` don't silently become 1/0.
                        if isinstance(item, bool) or not isinstance(item, (int, float)):
                            raise ValueError(f"non-numeric element: {item!r}")
                        numbers.append(float(item))
                    return numbers
            except (json.JSONDecodeError, ValueError):
                # Fall through to comma-separated parsing below.
                pass
        return [float(x.strip()) for x in raw.split(",") if x.strip()]

    async def execute(self, **kwargs) -> DataAnalysisResponse:
        args = self.expected_args(**kwargs)
        try:
            numbers = self._parse_numbers(args.data)
            if not numbers:
                return DataAnalysisResponse(
                    mean=0.0, median=0.0, std=0.0,
                    min=0.0, max=0.0, count=0,
                    error="No valid numbers provided."
                )
            return DataAnalysisResponse(
                mean=statistics.mean(numbers),
                median=statistics.median(numbers),
                std=statistics.stdev(numbers) if len(numbers) > 1 else 0.0,
                min=min(numbers),
                max=max(numbers),
                count=len(numbers),
            )
        except Exception as e:
            return DataAnalysisResponse(
                mean=0.0, median=0.0, std=0.0,
                min=0.0, max=0.0, count=0,
                error=str(e)
            )
