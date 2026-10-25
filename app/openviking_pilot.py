"""Source-preserving resource catalogue for a public-only, isolated retrieval pilot."""

import hashlib
import re
from datetime import date
from urllib.parse import urlsplit

import httpx


def prepare_resources(corpus, *, owner):
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,39}", owner):
        raise ValueError("invalid experiment owner")
    resources = []
    for doc_id, doc in corpus["documents"].items():
        pages = sorted({p for c in corpus["cases"] for p in c["context_pages"].get(doc_id, [])})
        for page in pages:
            text = doc["text_pages"][page - 1]["text"]
            text_hash = hashlib.sha256(text.encode()).hexdigest()
            identity = f"{owner}/{doc['pdf_sha256']}/{page}/{text_hash}"
            resources.append(
                dict(
                    id=hashlib.sha256(identity.encode()).hexdigest(),
                    owner=owner,
                    document_id=doc_id,
                    symbol=doc["symbol"],
                    report_period=doc["report_period"],
                    published_date=doc["published_date"],
                    pdf_sha256=doc["pdf_sha256"],
                    page=page,
                    text=text,
                    text_sha256=text_hash,
                    active=True,
                )
            )
    return resources


def allowed_resources(resources, *, owner, symbol, as_of):
    visible = date.fromisoformat(as_of)
    return [
        r
        for r in resources
        if r["active"] is True
        and r["owner"] == owner
        and r["symbol"] == symbol
        and date.fromisoformat(r["published_date"]) < visible
    ]


def resolve_hits(hits, bindings, allowed):
    by_id = {r["id"]: r for r in allowed if r["active"] is True}
    result = []
    seen = set()
    for hit in hits:
        uri = hit.get("uri", "")
        if not isinstance(uri, str) or "%" in uri or ".." in uri.split("/"):
            continue
        for root, identity in bindings.items():
            if (uri == root or uri.startswith(root + "/")) and identity in by_id:
                if identity not in seen:
                    result.append(by_id[identity])
                    seen.add(identity)
                break
    return result


def _terms(text):
    text = text.casefold()
    terms = re.findall(r"[a-z0-9]+", text)
    for segment in re.findall(r"[\u4e00-\u9fff]+", text):
        terms.extend(segment[i : i + 2] for i in range(max(1, len(segment) - 1)))
    return set(terms)


def lexical_find(query, resources, *, limit=3):
    """Transparent lexical comparator, explicitly not production Chroma/BGE."""
    terms = _terms(query)
    ranked = sorted(resources, key=lambda r: (-len(terms & _terms(r["text"])), r["id"]))
    return [r for r in ranked if terms & _terms(r["text"])][: max(0, limit)]


def retrieval_coverage(gold, found):
    """Only tests whether a gold source was retrieved, never answer correctness."""
    if gold["status"] != "supported":
        return None
    anchors = gold.get("allowed_anchors") or [gold["anchor"]]
    return any(
        r["document_id"] == a["document_id"] and r["page"] == a["page"] and a["quote"] in r["text"]
        for r in found
        for a in anchors
    )


def verify_content(resource, content):
    return (
        isinstance(content, str)
        and hashlib.sha256(resource["text"].encode()).hexdigest() == resource["text_sha256"]
        and resource["text"] in content
        and (
            "backend_body_sha256" not in resource
            or hashlib.sha256(content.encode()).hexdigest() == resource["backend_body_sha256"]
        )
    )


def bind_content(resource, content):
    """Keep backend-body identity separate from original PDF/page fingerprints."""
    if not verify_content(resource, content):
        raise ValueError("backend body does not preserve frozen source")
    return dict(resource, backend_body_sha256=hashlib.sha256(content.encode()).hexdigest())


def read_memory(client):
    """Commit completion is not an embedding-queue barrier."""
    queues = client.call("POST", "/api/v1/system/wait")
    if any(v.get("error_count", 0) for v in queues.values() if isinstance(v, dict)):
        raise RuntimeError("memory indexing did not complete successfully")
    result = client.call(
        "POST",
        "/api/v1/search/find",
        json=dict(
            query="财报研究的核对偏好与金额单位",
            target_uri="viking://~/memories",
            limit=3,
            level=2,
        ),
    )
    hits = result.get("memories", [])
    texts = [client.call("GET", "/api/v1/content/read", params={"uri": hit["uri"]}) for hit in hits]
    return dict(
        retrieved=len(hits),
        preference_found=any("原表单位" in str(t) and "报告期" in str(t) for t in texts),
        indexing_waited=True,
        queue_errors=sum(v.get("error_count", 0) for v in queues.values() if isinstance(v, dict)),
    )


class PilotClient:
    """HTTP-only experiment client; never inherits user SDK configuration."""

    def __init__(self, url, key, *, transport=None):
        target = urlsplit(url)
        if (
            target.scheme != "http"
            or target.hostname != "127.0.0.1"
            or target.username
            or target.password
            or target.query
            or target.fragment
            or target.path not in {"", "/"}
        ):
            raise ValueError("pilot requires a loopback HTTP origin")
        self.http = httpx.Client(
            base_url=url,
            headers={"X-API-Key": key},
            timeout=90,
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        )

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.http.close()

    def call(self, method, path, **kwargs):
        if not path.startswith("/api/v1/"):
            raise ValueError("invalid experiment endpoint")
        response = self.http.request(method, path, **kwargs)
        if not response.is_success:
            error = RuntimeError(f"OpenViking HTTP {response.status_code}")
            try:
                detail = response.json().get("error", {})
                error.api_code = str(detail.get("code", "unknown"))[:80]
                error.api_message = str(detail.get("message", ""))[:400]
            except (ValueError, AttributeError):
                pass
            raise error
        try:
            data = response.json()
            if not isinstance(data, dict) or data.get("status") != "ok" or "result" not in data:
                raise ValueError
            return data["result"]
        except (TypeError, ValueError) as exc:
            raise RuntimeError("invalid OpenViking envelope") from exc
