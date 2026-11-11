from __future__ import annotations

import re
from typing import Any

import requests

try:
    import trafilatura  # type: ignore
except ImportError:  # pragma: no cover
    trafilatura = None


def fetch_article(url: str) -> str:
    headers = {"User-Agent": "Mozilla/5.0 (brain-gym/0.1)"}
    html = requests.get(url, headers=headers, timeout=30).text
    if trafilatura is not None:
        text = trafilatura.extract(html, output_format="txt", include_comments=False)
        if text and len(text) > 400:
            return text
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def fetch_youtube_transcript(url: str) -> tuple[str, str]:
    m = re.search(r"(?:v=|youtu\.be/|shorts/)([\w-]{11})", url)
    if not m:
        raise ValueError(f"Could not find a YouTube video ID in {url}")
    video_id = m.group(1)
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("youtube-transcript-api is required for YouTube mode") from exc

    api = YouTubeTranscriptApi()
    fetched = api.fetch(video_id)
    text = " ".join(snippet.text for snippet in fetched)
    try:
        title = (
            requests.get(
                f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={video_id}&format=json",
                timeout=10,
            )
            .json()
            .get("title", video_id)
        )
    except Exception:
        title = video_id
    return text.strip(), title


def load_article_from_args(args: Any) -> tuple[str, str, str, str | None]:
    if getattr(args, "url", None):
        article = fetch_article(args.url)
        return article, "url", args.url, None
    if getattr(args, "youtube", None):
        article, title = fetch_youtube_transcript(args.youtube)
        return article, "youtube", args.youtube, title
    if getattr(args, "file", None):
        with open(args.file, "r", encoding="utf-8") as handle:
            return handle.read(), "file", args.file, None
    if getattr(args, "text", None):
        return args.text, "text", "pasted text", None
    raise ValueError("No article input provided")
