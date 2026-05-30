from pydantic import BaseModel, Field
from typing import Type
import asyncio
from core.base import BaseSkill

class WeatherArgs(BaseModel):
    location: str = Field(..., description="The city or location to get the weather for.")
    date: str = Field(default="today", description="The date to get the weather for. Defaults to today.")

class WeatherResponse(BaseModel):
    location: str
    weather: str
    temperature: float

class WeatherSkill(BaseSkill):
    @property
    def name(self) -> str:
        return "weather_skill"

    @property
    def description(self) -> str:
        return "Get the current weather for a specific location and optional date."

    @property
    def expected_args(self) -> Type[BaseModel]:
        return WeatherArgs

    @property
    def expected_response_type(self) -> Type[BaseModel]:
        return WeatherResponse

    async def execute(self, **kwargs) -> WeatherResponse:
        # Validate input arguments
        args = self.expected_args(**kwargs)

        # Simulate asynchronous API call
        await asyncio.sleep(0.1)

        # Mock weather data
        mock_data = {
            "location": args.location,
            "weather": "Sunny" if args.date.lower() == "today" else "Cloudy",
            "temperature": 25.0
        }

        # Return validated response model
        return self.expected_response_type(**mock_data)
