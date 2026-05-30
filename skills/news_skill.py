import xml.etree.ElementTree as ET
import httpx
from pydantic import BaseModel, Field
from typing import Type, Optional
from core.base import BaseSkill


class NewsArgs(BaseModel):
    query: str = Field(..., description="Search query for news articles.")
    count: int = Field(default=5, description="Maximum number of news articles to return.")


class NewsResponse(BaseModel):
    results: str
    error: Optional[str] = None


class NewsSkill(BaseSkill):
    @property
    def name(self) -> str:
        return "news_skill"

    @property
    def description(self) -> str:
        return "Fetch latest news articles from Google News RSS. Trigger words: news, latest news, headlines, 新闻, 资讯"

    @property
    def expected_args(self) -> Type[BaseModel]:
        return NewsArgs

    @property
    def expected_response_type(self) -> Type[BaseModel]:
        return NewsResponse

    async def execute(self, **kwargs) -> NewsResponse:
        args = self.expected_args(**kwargs)
        try:
            url = (
                f"https://news.google.com/rss/search"
                f"?q={args.query}&hl=en-US&gl=US&ceid=US:en"
            )
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
            root = ET.fromstring(resp.text)
            items = root.findall(".//item")
            formatted = []
            for i, item in enumerate(items[: args.count], 1):
                title = item.findtext("title", "No title")
                link = item.findtext("link", "")
                formatted.append(f"{i}. {title}\n   {link}")
            if not formatted:
                return NewsResponse(results="No news articles found.")
            return NewsResponse(results="\n\n".join(formatted))
        except httpx.HTTPStatusError as exc:
            return NewsResponse(results="", error=f"HTTP error from news feed: {exc.response.status_code}")
        except httpx.RequestError as exc:
            return NewsResponse(results="", error=f"Network error when calling news feed: {exc}")
        except ET.ParseError as exc:
            return NewsResponse(results="", error=f"Failed to parse news feed XML: {exc}")
        except Exception as exc:
            return NewsResponse(results="", error=f"Unexpected error: {exc}")
