import ssl

import httpx
import pytest

from tools import verify_csa

FEED_URL = "https://www.asc-csa.gc.ca/rss/default_eng.xml"


def mock_source(monkeypatch, feed):
    real_client = httpx.Client
    observed_contexts = []

    def handler(request):
        if str(request.url) == verify_csa.PORTAL:
            return httpx.Response(
                200,
                text='<a href="/rss/default_eng.xml">RSS</a>',
                headers={"content-type": "text/html"},
            )
        assert str(request.url) == FEED_URL
        return httpx.Response(200, content=feed, headers={"content-type": "text/xml"})

    def client(**kwargs):
        observed_contexts.append(kwargs["verify"])
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(verify_csa.httpx, "Client", client)
    return observed_contexts


def test_atom_namespaces_and_link_attributes_are_parsed_with_tls12(monkeypatch):
    contexts = mock_source(
        monkeypatch,
        b"""<feed xmlns="http://www.w3.org/2005/Atom">
      <entry><title>Synthetic Moon fixture</title>
      <link rel="self" href="https://example.org/self"/>
      <link rel="alternate" href="https://example.org/moon"/>
      <published>2026-11-13T00:00:00Z</published></entry>
    </feed>""",
    )
    report = verify_csa.verify(tls12=True)
    assert report["verification"] == "complete"
    assert report["feed_format"] == "atom"
    assert report["item_count"] == report["matching_item_count"] == 1
    assert report["item_fields"] == ["link", "published", "title"]
    assert report["relevant_entries"][0]["link"] == "https://example.org/moon"
    assert report["relevant_entries"][0]["published_at"] == "2026-11-13T00:00:00Z"
    assert report["feed_url"] == FEED_URL
    assert report["tls_mode"] == "TLS1.2_only"
    assert contexts[0].minimum_version == contexts[0].maximum_version == ssl.TLSVersion.TLSv1_2
    assert contexts[0].verify_mode == ssl.CERT_REQUIRED
    assert contexts[0].check_hostname is True


def test_rss_items_and_dates_remain_supported(monkeypatch):
    mock_source(
        monkeypatch,
        b"""<rss version="2.0"><channel><item>
    <title>Synthetic Gateway fixture</title><link>https://example.org/gateway</link>
    <pubDate>Fri, 13 Nov 2026 00:00:00 GMT</pubDate></item></channel></rss>""",
    )
    report = verify_csa.verify()
    assert report["verification"] == "complete"
    assert report["feed_format"] == "rss"
    assert report["matching_item_count"] == 1
    assert report["relevant_entries"][0]["link"] == "https://example.org/gateway"
    assert report["relevant_entries"][0]["published_at"] == "Fri, 13 Nov 2026 00:00:00 GMT"


def test_accessible_feed_without_matching_entries_is_complete(monkeypatch):
    mock_source(
        monkeypatch,
        b"""<feed xmlns="http://www.w3.org/2005/Atom">
    <entry><title>Synthetic satellite fixture</title></entry></feed>""",
    )
    report = verify_csa.verify()
    assert report["verification"] == "complete"
    assert report["item_count"] == 1
    assert report["matching_item_count"] == 0
    assert report["relevant_entries"] == []


@pytest.mark.parametrize(
    "body",
    [
        b"<rss>",
        b"<html><body>Not a feed</body></html>",
        b'<!DOCTYPE rss [<!ENTITY payload SYSTEM "file:///unread">]><rss>&payload;</rss>',
    ],
)
def test_malformed_unrecognized_and_unsafe_xml_is_incomplete(monkeypatch, body):
    mock_source(monkeypatch, body)
    report = verify_csa.verify()
    assert report["verification"] == "incomplete"
    assert report["failure"]
    assert report["relevant_entries"] == []
