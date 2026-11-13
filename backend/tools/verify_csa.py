"""Explicit live source probe; never run by deterministic tests or normal API startup."""

import argparse
import json
import ssl
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

PORTAL = "https://www.asc-csa.gc.ca/eng/astronomy/moon-exploration/"
MAX_BYTES = 2 * 1024 * 1024
ATOM = "{http://www.w3.org/2005/Atom}"


def feed_observation(root):
    if root.tag == ATOM + "feed":
        feed_format = "atom"
        items = root.findall(ATOM + "entry")
    elif root.tag == "rss" and root.find("channel") is not None:
        feed_format = "rss"
        items = root.findall("./channel/item")
    else:
        raise ValueError("XML is valid but is not a supported RSS or Atom feed")
    keywords = ("moon", "artemis", "gateway", "canadarm3")
    matches = [
        item
        for item in items
        if any(word in " ".join(item.itertext()).lower() for word in keywords)
    ]
    entries = []
    for item in matches[:5]:
        if feed_format == "atom":
            links = [
                link.get("href")
                for link in item.findall(ATOM + "link")
                if link.get("rel", "alternate") == "alternate" and link.get("href")
            ]
            entries.append(
                {
                    "title": item.findtext(ATOM + "title"),
                    "link": links[0] if links else None,
                    "published_at": item.findtext(ATOM + "published")
                    or item.findtext(ATOM + "updated"),
                }
            )
        else:
            entries.append(
                {
                    "title": item.findtext("title"),
                    "link": item.findtext("link"),
                    "published_at": item.findtext("pubDate"),
                }
            )
    return {
        "feed_format": feed_format,
        "item_count": len(items),
        "item_fields": sorted({child.tag.rsplit("}", 1)[-1] for item in items for child in item}),
        "matching_item_count": len(matches),
        "relevant_entries": entries,
    }


class FeedLinks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        href = attributes.get("href", "")
        if tag in {"a", "link"} and ("rss" in href.lower() or "rss" in attributes.get("type", "")):
            self.links.append(urljoin(PORTAL, href))


def fetch(client, url):
    if urlsplit(url).hostname != "www.asc-csa.gc.ca":
        raise ValueError("Probe only follows links on the official CSA host")
    with client.stream("GET", url) as response:
        body = bytearray()
        for chunk in response.iter_bytes():
            body.extend(chunk)
            if len(body) > MAX_BYTES:
                raise ValueError("Response exceeded the two MiB probe limit")
        return response.status_code, response.headers.get("content-type"), bytes(body)


def verify(tls12: bool = False):
    report = {
        "verified_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "official_source_url": PORTAL,
        "tls_mode": "TLS1.2_only" if tls12 else "system_default",
        "certificate_verification": True,
        "verification": "incomplete",
        "xml_valid": None,
        "item_fields": [],
        "relevant_entries": [],
    }
    try:
        context = ssl.create_default_context()
        if tls12:
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.maximum_version = ssl.TLSVersion.TLSv1_2
        with httpx.Client(
            verify=context, timeout=10, follow_redirects=False, trust_env=False
        ) as client:
            status, content_type, body = fetch(client, PORTAL)
            report.update(portal_http_status=status, portal_content_type=content_type)
            if status != 200:
                raise ValueError(f"Portal returned HTTP {status}; feed discovery incomplete")
            parser = FeedLinks()
            parser.feed(body.decode("utf-8"))
            if not parser.links:
                raise ValueError("No published RSS link found on the portal")
            report["feed_url"] = parser.links[0]
            status, content_type, body = fetch(client, parser.links[0])
            report.update(feed_http_status=status, feed_content_type=content_type)
            if status != 200:
                raise ValueError(f"Feed returned HTTP {status}")
            report["xml_valid"] = False
            root = ElementTree.fromstring(body, forbid_dtd=True)
            report["xml_valid"] = True
            report.update(feed_observation(root))
            report["verification"] = "complete"
    except (httpx.HTTPError, ValueError, ElementTree.ParseError, DefusedXmlException) as exc:
        report["failure"] = f"{type(exc).__name__}: {exc}"
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Write a Markdown report at this explicit path")
    parser.add_argument(
        "--tls12",
        action="store_true",
        help="Use only TLS 1.2 for source compatibility; certificate verification stays enabled",
    )
    args = parser.parse_args()
    report = verify(tls12=args.tls12)
    text = (
        "# CSA source feed verification\n\n"
        "Live observation, not a production integration or scientific result. "
        "The RSS URL is discovered from the official Moon Exploration portal. "
        "RSS and Atom are parsed with external entities and DTDs prohibited. "
        "Entries reflect the feed at verification time; relevance uses keyword matching. "
        "TLS mode is explicit and certificate verification remains enabled.\n\n"
        "```json\n" + json.dumps(report, indent=2, ensure_ascii=True) + "\n```\n"
    )
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text)
    return 0 if report["verification"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
