import asyncio
from pydantic import BaseModel, Field
from typing import Type, Optional
from duckduckgo_search import DDGS
from core.base import BaseSkill


class WebSearchArgs(BaseModel):
    query: str = Field(..., description="The search query string.")
    max_results: int = Field(default=5, description="Maximum number of results to return.")


class WebSearchResponse(BaseModel):
    results: str
    error: Optional[str] = None


class WebSearchSkill(BaseSkill):
    @property
    def name(self) -> str:
        return "web_search_skill"

    @property
    def description(self) -> str:
        return "Search the web using DuckDuckGo. Trigger words: search, find, look up, web search, internet search, 搜索, 查找"

    @property
    def expected_args(self) -> Type[BaseModel]:
        return WebSearchArgs

    @property
    def expected_response_type(self) -> Type[BaseModel]:
        return WebSearchResponse

    async def execute(self, **kwargs) -> WebSearchResponse:
        args = self.expected_args(**kwargs)
        try:
            results = await asyncio.to_thread(
                self._search, args.query, args.max_results
            )
            if not results:
                return WebSearchResponse(results="No results found.")
            formatted = []
            for i, r in enumerate(results, 1):
                title = r.get("title", "No title")
                snippet = r.get("body", "")
                link = r.get("href", "")
                formatted.append(f"{i}. {title}\n   {snippet}\n   {link}")
            return WebSearchResponse(results="\n\n".join(formatted))
        except Exception as e:
            return WebSearchResponse(results="", error=str(e))

    @staticmethod
    def _search(query: str, max_results: int) -> list:
        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=max_results))
