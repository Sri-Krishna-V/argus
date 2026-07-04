"""RSS/Atom news connector. Entry content is the document (article pages are
paywalled/JS-rendered; the feed's own text is the honest evidence source)."""

import time
from datetime import UTC, datetime

import feedparser
import httpx

from argus.core.config import get_settings
from argus.dataplatform.connectors.base import DocumentRef


class RssConnector:
    name = "rss"

    def discover(self) -> list[DocumentRef]:
        refs: list[DocumentRef] = []
        for feed_url in get_settings().rss_feeds:
            try:
                raw = httpx.get(feed_url, timeout=30, follow_redirects=True).raise_for_status()
            except httpx.HTTPError:
                continue  # one dead feed must not kill the pass; run stats show 'seen' drop
            parsed = feedparser.parse(raw.content)
            publisher = parsed.feed.get("title")
            for entry in parsed.entries:
                native_id = entry.get("id") or entry.get("link")
                if not native_id:
                    continue
                content = (
                    entry.get("content", [{}])[0].get("value") or entry.get("summary") or ""
                )
                title = entry.get("title", "")
                if not content and not title:
                    continue
                published = None
                if entry.get("published_parsed"):
                    published = datetime.fromtimestamp(
                        time.mktime(entry.published_parsed), tz=UTC
                    )
                refs.append(
                    DocumentRef(
                        source=self.name,
                        native_id=native_id,
                        doc_type="news",
                        url=entry.get("link"),
                        title=title,
                        publisher=publisher,
                        published_at=published,
                        inline_content=f"<h1>{title}</h1>\n{content}".encode(),
                    )
                )
        return refs

    def fetch(self, ref: DocumentRef) -> bytes:  # pragma: no cover - inline_content used
        raise NotImplementedError
