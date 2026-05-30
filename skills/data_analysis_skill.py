import statistics
from pydantic import BaseModel, Field
from typing import Type, Optional
from core.base import BaseSkill


class DataAnalysisArgs(BaseModel):
    data: str = Field(..., description="Comma-separated numbers, e.g. '1,2,3,4,5'.")
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

    async def execute(self, **kwargs) -> DataAnalysisResponse:
        args = self.expected_args(**kwargs)
        try:
            numbers = [float(x.strip()) for x in args.data.split(",") if x.strip()]
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
