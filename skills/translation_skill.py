import httpx
from urllib.parse import quote
from pydantic import BaseModel, Field
from typing import Type, Optional
from core.base import BaseSkill


class TranslationArgs(BaseModel):
    text: str = Field(..., description="The text to translate.")
    source_language: str = Field(default="en", description="Source language code, e.g. 'en'.")
    target_language: str = Field(default="zh", description="Target language code, e.g. 'zh'.")


class TranslationResponse(BaseModel):
    translated_text: str
    source_language: str
    target_language: str
    error: Optional[str] = None


class TranslationSkill(BaseSkill):
    @property
    def name(self) -> str:
        return "translation_skill"

    @property
    def description(self) -> str:
        return "Translate text between languages using MyMemory API. Trigger words: translate, translation, 翻译, 语言转换"

    @property
    def expected_args(self) -> Type[BaseModel]:
        return TranslationArgs

    @property
    def expected_response_type(self) -> Type[BaseModel]:
        return TranslationResponse

    async def execute(self, **kwargs) -> TranslationResponse:
        args = self.expected_args(**kwargs)
        try:
            url = (
                f"https://api.mymemory.translated.net/get"
                f"?q={quote(args.text)}&langpair={args.source_language}|{args.target_language}"
            )
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
            translated = data.get("responseData", {}).get("translatedText", "")
            if not translated:
                matches = data.get("matches", [])
                if matches:
                    translated = matches[0].get("translation", "")
            return TranslationResponse(
                translated_text=translated,
                source_language=args.source_language,
                target_language=args.target_language,
            )
        except httpx.HTTPStatusError as exc:
            return TranslationResponse(
                translated_text="",
                source_language=args.source_language,
                target_language=args.target_language,
                error=f"HTTP error from translation API: {exc.response.status_code}"
            )
        except httpx.RequestError as exc:
            return TranslationResponse(
                translated_text="",
                source_language=args.source_language,
                target_language=args.target_language,
                error=f"Network error when calling translation API: {exc}"
            )
        except Exception as exc:
            return TranslationResponse(
                translated_text="",
                source_language=args.source_language,
                target_language=args.target_language,
                error=f"Unexpected error: {exc}"
            )
