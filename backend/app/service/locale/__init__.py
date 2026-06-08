from __future__ import annotations

from typing import Literal, TypedDict
from urllib.parse import urlsplit

LanguageCode = Literal["zh", "en"]
CountryCode = Literal["china", "global", "unknown"]


class SourceLocale(TypedDict):
    country: CountryCode
    language: LanguageCode
    country_signal: str
    language_signal: str
    host: str | None


_CHINA_TLD_SUFFIXES = (
    ".cn",
    ".com.cn",
    ".net.cn",
    ".org.cn",
    ".gov.cn",
    ".edu.cn",
    ".中国",
    ".公司",
    ".网络",
)
_CHINA_HOST_SUFFIXES = (
    "1688.com",
    "36kr.com",
    "aliyun.com",
    "baidu.com",
    "bilibili.com",
    "bytedance.com",
    "csdn.net",
    "doubao.com",
    "feishu.cn",
    "huawei.com",
    "jd.com",
    "qq.com",
    "sina.com.cn",
    "sohu.com",
    "taobao.com",
    "tencent.com",
    "tmall.com",
    "weixin.qq.com",
    "zhihu.com",
)


def detect_language(text: str) -> LanguageCode:
    """Detect the expected output language from user-visible text."""
    if not isinstance(text, str):
        raise TypeError("detect_language expects text to be str")
    stripped = text.strip()
    if not stripped:
        return "en"
    chinese_chars = sum(1 for char in stripped if "\u4e00" <= char <= "\u9fff")
    alnum_chars = sum(1 for char in stripped if char.isalnum())
    if alnum_chars == 0:
        return "en"
    if chinese_chars >= 4:
        return "zh"
    return "zh" if chinese_chars >= 2 and chinese_chars / alnum_chars >= 0.10 else "en"


# Multilingual breadth policy. Output language picks the "home" language; market scope and
# explicit hints add further languages so niche-market sources (e.g. the best product lives in a
# non-mainstream-language country) are reachable. Each language routes to its best engine/country.
_MARKET_LANGUAGE_MARKERS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("中国", "国内", "大陆", "china", "mainland", "prc"), "zh"),
    (("日本", "日语", "日語", "japan", "japanese"), "ja"),
    (("韩国", "韓國", "한국", "korea", "korean"), "ko"),
    (("德国", "德语", "德語", "germany", "german", "deutsch"), "de"),
    (("法国", "法语", "法語", "france", "french"), "fr"),
    (("西班牙", "拉美", "spain", "spanish", "latin america", "hispanic"), "es"),
)
# ISO 639-1 language -> Tavily `country` (its localization lever). English stays global (None).
_TAVILY_COUNTRY_BY_LANGUAGE: dict[str, str] = {
    "zh": "china",
    "ja": "japan",
    "ko": "south korea",
    "de": "germany",
    "fr": "france",
    "es": "spain",
}
_MAX_SEARCH_LANGUAGES = 4


def country_for_language(language: str) -> str | None:
    """Map an ISO 639-1 language to a Tavily country localization. English = global (None)."""
    if not isinstance(language, str):
        raise TypeError("country_for_language expects language to be str")
    return _TAVILY_COUNTRY_BY_LANGUAGE.get(language.strip().casefold())


def languages_from_market_scope(market_scope: object) -> list[str]:
    scope = market_scope if isinstance(market_scope, str) else ""
    lowered = scope.casefold()
    out: list[str] = []
    for markers, language in _MARKET_LANGUAGE_MARKERS:
        if any(marker in lowered for marker in markers) and language not in out:
            out.append(language)
    return out


def _normalize_languages(languages: list[str], *, max_languages: int) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in languages:
        if not isinstance(raw, str):
            continue
        key = raw.strip().casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(key)
        if len(result) >= max_languages:
            break
    return result


def plan_search_languages(
    *,
    response_language: str | None,
    market_scope: object,
    extra_languages: list[str] | None = None,
    max_languages: int = _MAX_SEARCH_LANGUAGES,
) -> list[str]:
    """Ordered language set for retrieval breadth: home language → English (global lingua franca)
    → market-implied languages → explicit hints. Carrier language never excludes; it only orders.
    """
    home = response_language if response_language in {"zh", "en"} else "en"
    ordered = [home, "en"]
    ordered.extend(languages_from_market_scope(market_scope))
    if extra_languages:
        ordered.extend(extra_languages)
    return _normalize_languages(ordered, max_languages=max_languages)


def target_country_from_scope(*, market_scope: object) -> str | None:
    """Region emphasis is derived ONLY from an explicit market scope.

    Output language (response_language) localizes the report; it must NOT constrain
    which markets/languages are in scope. A Chinese-speaking user asking about a global
    topic still wants global sources — language is the carrier, not the market.
    """
    scope = market_scope if isinstance(market_scope, str) else ""
    lowered = scope.casefold()
    if any(marker in lowered for marker in ("china", "mainland", "中国", "国内", "大陆")):
        return "china"
    return None


def _host_from_url(source_url: str | None) -> str | None:
    if not isinstance(source_url, str) or not source_url.strip():
        return None
    try:
        parsed = urlsplit(source_url.strip())
    except ValueError:
        return None
    host = parsed.hostname
    return host.casefold() if isinstance(host, str) and host.strip() else None


def _country_from_host(host: str | None) -> tuple[CountryCode, str]:
    if host is None:
        return "unknown", "missing_url"
    if host.endswith(_CHINA_TLD_SUFFIXES):
        return "china", "china_tld"
    if any(host == suffix or host.endswith(f".{suffix}") for suffix in _CHINA_HOST_SUFFIXES):
        return "china", "known_china_host"
    return "global", "host"


def _language_from_span(span: dict[str, object] | None) -> LanguageCode | None:
    if not isinstance(span, dict):
        return None
    language_raw = span.get("response_language")
    return language_raw if language_raw in {"zh", "en"} else None


def source_locale(
    *,
    source_url: str | None,
    span: dict[str, object] | None,
    sanitized_text: str,
) -> SourceLocale:
    host = _host_from_url(source_url)
    country, country_signal = _country_from_host(host)
    span_language = _language_from_span(span)
    if span_language is not None:
        language = span_language
        language_signal = "span.response_language"
    else:
        language = detect_language(sanitized_text)
        language_signal = "sanitized_text"
    return {
        "country": country,
        "language": language,
        "country_signal": country_signal,
        "language_signal": language_signal,
        "host": host,
    }
