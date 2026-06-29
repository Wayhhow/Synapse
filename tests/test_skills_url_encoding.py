import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from urllib.parse import quote

from skills.translation_skill import TranslationSkill, TranslationResponse
from skills.news_skill import NewsSkill, NewsResponse


TRANSLATION_MOCK_PAYLOAD = {
    "responseData": {"translatedText": "你好"},
    "matches": [],
}

NEWS_MOCK_XML = (
    '<?xml version="1.0"?>'
    '<rss><channel><item>'
    '<title>Test</title><link>http://x</link>'
    '</item></channel></rss>'
)


@pytest.mark.asyncio
@patch("httpx.AsyncClient.get", new_callable=AsyncMock)
async def test_translation_skill_url_encodes_special_chars(mock_get):
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = TRANSLATION_MOCK_PAYLOAD
    mock_get.return_value = mock_resp

    skill = TranslationSkill()
    result = await skill.execute(
        text="hello & world #1",
        source_language="en",
        target_language="zh",
    )

    assert isinstance(result, TranslationResponse)
    assert result.translated_text == "你好"
    assert result.error is None

    mock_get.assert_called_once()
    called_url = mock_get.call_args.args[0]

    expected_encoded = quote("hello & world #1")
    assert expected_encoded == "hello%20%26%20world%20%231"
    assert f"q={expected_encoded}" in called_url
    assert "q=hello & world #1" not in called_url
    assert "&langpair=en|zh" in called_url


@pytest.mark.asyncio
@patch("httpx.AsyncClient.get", new_callable=AsyncMock)
async def test_news_skill_url_encodes_special_chars(mock_get):
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.text = NEWS_MOCK_XML
    mock_get.return_value = mock_resp

    skill = NewsSkill()
    result = await skill.execute(query="AI & robotics news", count=3)

    assert isinstance(result, NewsResponse)
    assert result.error is None
    assert "Test" in result.results

    mock_get.assert_called_once()
    called_url = mock_get.call_args.args[0]

    expected_encoded = quote("AI & robotics news")
    assert "%26" in expected_encoded
    assert "%20" in expected_encoded
    assert f"q={expected_encoded}" in called_url
    assert "q=AI & robotics news" not in called_url
    assert "&hl=en-US&gl=US&ceid=US:en" in called_url


@pytest.mark.asyncio
@patch("httpx.AsyncClient.get", new_callable=AsyncMock)
async def test_translation_skill_preserves_normal_text(mock_get):
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = TRANSLATION_MOCK_PAYLOAD
    mock_get.return_value = mock_resp

    skill = TranslationSkill()
    result = await skill.execute(
        text="hello world",
        source_language="en",
        target_language="zh",
    )

    assert isinstance(result, TranslationResponse)
    assert result.translated_text == "你好"
    assert result.error is None

    mock_get.assert_called_once()
    called_url = mock_get.call_args.args[0]

    expected_encoded = quote("hello world")
    assert expected_encoded == "hello%20world"
    assert f"q={expected_encoded}" in called_url
    assert called_url.startswith("https://api.mymemory.translated.net/get?q=")
    assert "&langpair=en|zh" in called_url
