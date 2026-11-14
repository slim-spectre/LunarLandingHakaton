from datetime import timedelta

import httpx
import pytest
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from app.core.problems import APIProblem
from app.resources import get_resources, parse_resources
from app.routes import get_csa_fetcher
from app.storage import iso

ATOM = b"""<feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>Artemis Moon fixture</title><id>fixture-one</id>
<link rel="alternate" href="https://example.org/moon"/>
<published>2026-11-14T12:00:00+02:00</published>
<summary type="html">&lt;p&gt;Gateway and Canadarm3 fixture.&lt;/p&gt;</summary>
<content>Full article body must not be republished.</content></entry>
<entry><title>Satellite fixture</title><summary>No matching topic.</summary></entry>
</feed>"""


def payload(clock):
    return {"items": parse_resources(ATOM), "fetched_at": iso(clock[0])}


def unavailable():
    raise httpx.ConnectError("private upstream failure")


def test_atom_fields_topics_dates_and_summary_only():
    items = parse_resources(ATOM)
    assert len(items) == 1
    item = items[0]
    assert item["published_at"] == "2026-11-14T10:00:00Z"
    assert item["summary"] == "Gateway and Canadarm3 fixture."
    assert "Full article" not in str(item)
    assert item["topics"] == ["moon", "artemis", "gateway", "canadarm3"]
    assert item["url"] == "https://example.org/moon" and item["id"] == "fixture-one"


def test_rss_resources_and_stable_url_based_ids():
    xml = b"""<rss><channel><item><title>Moon fixture</title>
<link>https://example.org/moon</link><pubDate>Fri, 14 Nov 2025 12:00:00 GMT</pubDate>
<description>Fixture summary.</description></item></channel></rss>"""
    assert parse_resources(xml) == parse_resources(xml)
    assert len(parse_resources(xml)[0]["id"]) == 64


@pytest.mark.parametrize(
    "xml",
    [
        b"<feed>",
        b"<html/>",
        b'<!DOCTYPE rss [<!ENTITY payload SYSTEM "file:///unread">]><rss>&payload;</rss>',
    ],
)
def test_csa_unsafe_and_invalid_xml_is_not_accepted(xml):
    with pytest.raises((ValueError, ElementTree.ParseError, DefusedXmlException)):
        parse_resources(xml)


def test_csa_fresh_cached_stale_and_recovery(stage_repo, stage_clock):
    calls = []

    def fetch():
        calls.append(1)
        return payload(stage_clock)

    fresh = get_resources(stage_repo, 10, fetch)
    assert fresh["data_status"] == "fresh" and len(fresh["items"]) == 1
    cached = get_resources(stage_repo, 10, fetch)
    assert len(calls) == 1 and cached["data_status"] == "cached"
    stage_clock[0] += timedelta(minutes=6)
    stale = get_resources(stage_repo, 10, unavailable)
    assert stale["data_status"] == "stale" and stale["fetched_at"] == fresh["fetched_at"]
    recovered = get_resources(stage_repo, 10, fetch)
    assert recovered["data_status"] == "fresh" and recovered["fetched_at"] != fresh["fetched_at"]
    stage_clock[0] += timedelta(days=2)
    with pytest.raises(APIProblem) as problem:
        get_resources(stage_repo, 10, unavailable)
    assert problem.value.code == "CSA_UNAVAILABLE"


def test_csa_empty_feed_is_a_valid_fresh_result(stage_repo, stage_clock):
    result = get_resources(stage_repo, 10, lambda: {"items": [], "fetched_at": iso(stage_clock[0])})
    assert result["items"] == [] and result["data_status"] == "fresh"


def test_csa_http_limits_and_unavailable_error(stage_client, stage_clock):
    stage_client.app.dependency_overrides[get_csa_fetcher] = lambda: unavailable
    response = stage_client.get("/api/v1/resources/csa")
    assert response.status_code == 503 and response.json()["error"]["code"] == "CSA_UNAVAILABLE"
    for query in ("limit=0", "limit=31", "limit=no"):
        assert stage_client.get("/api/v1/resources/csa?" + query).status_code == 422
    assert stage_client.get("/api/v1/resources/csa?url=https://example.org").status_code == 400
    stage_client.app.dependency_overrides[get_csa_fetcher] = lambda: lambda: payload(stage_clock)
    response = stage_client.get("/api/v1/resources/csa?limit=1")
    assert response.status_code == 200 and len(response.json()["items"]) == 1


@pytest.mark.parametrize("mode", ["ok", "oversized", "redirect"])
def test_production_csa_transport_is_verified_bounded_and_does_not_follow_redirects(
    monkeypatch, mode
):
    import ssl

    from app import resources

    real_client = httpx.Client
    requests = []

    def handler(request):
        requests.append(str(request.url))
        if mode == "redirect":
            return httpx.Response(302, headers={"Location": "https://example.org/untrusted"})
        body = b"x" * (2 * 1024 * 1024 + 1) if mode == "oversized" else ATOM
        return httpx.Response(200, content=body)

    def client(**kwargs):
        assert kwargs["verify"].check_hostname
        assert kwargs["verify"].verify_mode == ssl.CERT_REQUIRED
        assert kwargs["verify"].maximum_version == ssl.TLSVersion.TLSv1_2
        assert not kwargs["follow_redirects"] and not kwargs["trust_env"]
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(resources.httpx, "Client", client)
    if mode == "ok":
        assert len(resources.fetch_resources()["items"]) == 1
    else:
        with pytest.raises((ValueError, httpx.HTTPStatusError)):
            resources.fetch_resources()
    assert requests == [resources.CSA_FEED_URL]
