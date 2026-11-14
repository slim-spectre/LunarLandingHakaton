import hashlib
import logging
import ssl
import time
from datetime import datetime
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import urlsplit

import httpx
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from app.core.config import get_settings
from app.core.problems import APIProblem
from app.storage import as_utc, iso, utcnow

CSA_FEED_URL = "https://www.asc-csa.gc.ca/rss/default_eng.xml"
ATOM = "{http://www.w3.org/2005/Atom}"
CSA_LOCK = 740102
LOGGER = logging.getLogger(__name__)


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def plain_text(value):
    parser = PlainText()
    parser.feed(value)
    return " ".join(" ".join(parser.parts).split())


def parse_resources(document):
    root = ElementTree.fromstring(document, forbid_dtd=True)
    if root.tag == ATOM + "feed":
        entries, prefix = root.findall(ATOM + "entry"), ATOM
    elif root.tag == "rss" and root.find("channel") is not None:
        entries, prefix = root.findall("./channel/item"), ""
    else:
        raise ValueError("Source is not a supported RSS or Atom feed")
    items = []
    for entry in entries:

        def text(name, node=entry):
            element = node.find(prefix + name)
            return " ".join(element.itertext()) if element is not None else ""

        title = plain_text(text("title"))
        summary = plain_text(text("summary" if prefix else "description"))[:2000]
        content = (title + " " + summary).lower()
        topics = [
            topic for topic in ("moon", "artemis", "gateway", "canadarm3") if topic in content
        ]
        if not topics:
            continue
        if prefix:
            links = [
                link.get("href")
                for link in entry.findall(ATOM + "link")
                if link.get("rel", "alternate") == "alternate" and link.get("href")
            ]
            url = links[0] if links else ""
            published = datetime.fromisoformat(text("published"))
            identifier = text("id")
        else:
            url = text("link").strip()
            published = parsedate_to_datetime(text("pubDate"))
            identifier = text("guid")
        if not title or urlsplit(url).scheme != "https" or not urlsplit(url).hostname:
            raise ValueError("A relevant feed entry has invalid title or URL")
        if published.tzinfo is None:
            raise ValueError("Publication time must include a timezone")
        items.append(
            {
                "id": identifier or hashlib.sha256(url.encode()).hexdigest(),
                "title": title,
                "summary": summary,
                "url": url,
                "published_at": iso(published),
                "topics": topics,
            }
        )
    return sorted(
        items, key=lambda item: datetime.fromisoformat(item["published_at"]), reverse=True
    )


def fetch_resources():
    context = ssl.create_default_context()
    context.minimum_version = context.maximum_version = ssl.TLSVersion.TLSv1_2
    started = time.monotonic()
    with httpx.Client(verify=context, timeout=5, follow_redirects=False, trust_env=False) as client:
        with client.stream("GET", CSA_FEED_URL) as response:
            response.raise_for_status()
            document = bytearray()
            for chunk in response.iter_bytes():
                document.extend(chunk)
                if len(document) > 2 * 1024 * 1024 or time.monotonic() - started > 10:
                    raise ValueError("CSA response exceeds the size or time budget")
    return {"items": parse_resources(bytes(document)), "fetched_at": iso(utcnow())}


def get_resources(repository, limit, fetcher=fetch_resources):
    settings = get_settings()
    cached = repository.resource("csa:v1")

    def cached_result(status):
        return {
            **cached["payload"],
            "items": cached["payload"]["items"][:limit],
            "data_status": status,
        }

    def age():
        return (repository.clock() - as_utc(cached["fetched_at"])).total_seconds()

    if cached and age() < settings.csa_cache_seconds:
        return cached_result("cached")
    with repository.provider_lock(CSA_LOCK) as acquired:
        if acquired:
            # Recheck after locking: another API process may already have refreshed the feed.
            cached = repository.resource("csa:v1")
            if cached and age() < settings.csa_cache_seconds:
                return cached_result("cached")
            try:
                payload = fetcher()
                repository.save_resource(
                    "csa:v1", payload, datetime.fromisoformat(payload["fetched_at"])
                )
                return {**payload, "items": payload["items"][:limit], "data_status": "fresh"}
            except (
                httpx.HTTPError,
                ValueError,
                ElementTree.ParseError,
                DefusedXmlException,
            ) as exc:
                LOGGER.warning("CSA source refresh failed (%s)", type(exc).__name__)
        if cached and age() <= settings.csa_stale_seconds:
            return cached_result("stale")
    raise APIProblem(
        503, "CSA_UNAVAILABLE", "CSA resources are unavailable and no usable cache exists"
    )
