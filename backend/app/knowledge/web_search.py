from __future__ import annotations

import html
import base64
import re
import urllib.parse
from typing import Any

import httpx

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


def normalize_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)

    if "duckduckgo.com" in parsed.netloc:
        query = urllib.parse.parse_qs(parsed.query)
        if query.get("uddg"):
            return query["uddg"][0]

    if "bing.com" in parsed.netloc and "/ck/a" in parsed.path:
        query = urllib.parse.parse_qs(parsed.query)
        encoded = query.get("u", [""])[0]
        if encoded:
            try:
                padded = encoded + "=" * (-len(encoded) % 4)
                return base64.urlsafe_b64decode(padded).decode("utf-8", errors="ignore")
            except Exception:
                pass

    if any(host in parsed.netloc for host in ("baidu.com", "sogou.com", "so.com")):
        try:
            resolved = httpx.get(
                url,
                headers={"User-Agent": USER_AGENT},
                timeout=3.0,
                follow_redirects=True,
            )
            if resolved.status_code == 200 and ("sogou.com" in parsed.netloc or "so.com" in parsed.netloc):
                match = re.search(r'window\.location\.replace\("([^"]+)"\)', resolved.text)
                if match:
                    return html.unescape(match.group(1))
            return str(resolved.url)
        except Exception:
            pass

    return url


def search_duckduckgo(query: str, limit: int = 5, timeout: float = 5.0) -> list[dict[str, str]]:
    try:
        response = httpx.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
            follow_redirects=True,
        )
        response.raise_for_status()
    except Exception:
        return []

    results: list[dict[str, str]] = []
    for url, title in re.findall(
        r'<a rel="nofollow" class="result__a" href="([^"]+)"[^>]*>(.*?)</a>',
        response.text,
    )[:limit]:
        cleaned_title = re.sub(r"<[^>]+>", "", title)
        results.append(
            {
                "title": html.unescape(cleaned_title).strip(),
                "url": normalize_url(html.unescape(url)),
            }
        )
    return results


def search_bing_cn(query: str, limit: int = 5, timeout: float = 5.0) -> list[dict[str, str]]:
    try:
        response = httpx.get(
            "https://cn.bing.com/search",
            params={"q": query},
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
            follow_redirects=True,
        )
        response.raise_for_status()
    except Exception:
        return []

    results: list[dict[str, str]] = []
    for url, title in re.findall(
        r'<li class="b_algo".*?<h2[^>]*><a[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        response.text,
        re.DOTALL,
    )[:limit]:
        cleaned_title = re.sub(r"<[^>]+>", "", title)
        results.append(
            {
                "title": html.unescape(cleaned_title).strip(),
                "url": normalize_url(html.unescape(url)),
            }
        )
    return results


def search_baidu(query: str, limit: int = 5, timeout: float = 5.0) -> list[dict[str, str]]:
    try:
        response = httpx.get(
            "https://www.baidu.com/s",
            params={"wd": query},
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
            follow_redirects=True,
        )
        response.raise_for_status()
    except Exception:
        return []

    results: list[dict[str, str]] = []
    for url, title in re.findall(
        r'<h3[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        response.text,
        re.DOTALL,
    )[:limit]:
        cleaned_title = re.sub(r"<[^>]+>", "", title)
        results.append(
            {
                "title": html.unescape(cleaned_title).strip(),
                "url": normalize_url(html.unescape(url)),
            }
        )
    return results


def search_sogou(query: str, limit: int = 5, timeout: float = 6.0) -> list[dict[str, str]]:
    try:
        response = httpx.get(
            "https://www.sogou.com/web",
            params={"query": query},
            headers={"User-Agent": USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9"},
            timeout=timeout,
            follow_redirects=True,
        )
        response.raise_for_status()
    except Exception:
        return []

    results: list[dict[str, str]] = []
    for href, title in re.findall(
        r'<h3[^>]*>.*?<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        response.text,
        re.DOTALL,
    )[:limit]:
        cleaned_title = re.sub(r"<[^>]+>", "", title)
        url = href if href.startswith("http") else f"https://www.sogou.com{href}"
        results.append(
            {
                "title": html.unescape(cleaned_title).strip(),
                "url": normalize_url(html.unescape(url)),
            }
        )
    return results


def search_360(query: str, limit: int = 5, timeout: float = 6.0) -> list[dict[str, str]]:
    try:
        response = httpx.get(
            "https://www.so.com/s",
            params={"q": query},
            headers={"User-Agent": USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9"},
            timeout=timeout,
            follow_redirects=True,
        )
        response.raise_for_status()
    except Exception:
        return []

    results: list[dict[str, str]] = []
    for href, title in re.findall(
        r'<h3[^>]*>.*?<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        response.text,
        re.DOTALL,
    )[:limit]:
        cleaned_title = re.sub(r"<[^>]+>", "", title)
        url = href if href.startswith("http") else f"https://www.so.com{href}"
        results.append(
            {
                "title": html.unescape(cleaned_title).strip(),
                "url": normalize_url(html.unescape(url)),
            }
        )
    return results


def web_search(query: str, limit: int = 5, timeout: float = 5.0) -> list[dict[str, str]]:
    for provider in (search_sogou, search_360, search_bing_cn, search_baidu):
        results = provider(query, limit=limit, timeout=timeout)
        if results:
            return results
    return []


def web_note(results: list[dict[str, Any]]) -> str:
    if not results:
        return "当前环境无法完成联网检索（网络受限或搜索引擎不可访问），可检查网络或配置搜索 API 后重试。"
    return f"以下内容来源于网络搜索，共 {len(results)} 条，请人工核实后再引用。"
