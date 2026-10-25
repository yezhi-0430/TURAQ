"""Opt-in native file context; no semantic indexing or provider credentials.

Only server-built public evaluation contexts enter this module. Native accounts
are per application actor; every recalled page must also match the current
application allowlist and its complete original text before source ranking.
"""

import hashlib
import hmac
import json
import re
import secrets
import time
from copy import deepcopy
from typing import Literal
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

BASE = "viking://user/owner/resources/turaq"
PREFERENCES = BASE + "/preferences.json"
MAX_RESPONSE = 2 * 1024 * 1024


class ContextUnavailable(Exception):
    def __init__(self):
        super().__init__("上下文服务暂不可用")


class NativeError(ContextUnavailable):
    def __init__(self, status):
        super().__init__()
        self.status = status


class ResearchPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    answer_detail: Literal["concise", "detailed"] = "concise"
    include_page_refs: bool = True
    check_original_units: bool = True


def preference_message(preferences):
    """Only enumerated presentation choices, never persisted instructions."""
    choices = ["回答尽量简洁" if preferences.answer_detail == "concise" else "回答提供适当解释"]
    if preferences.include_page_refs:
        choices.append("引用财报时列出已核实的文件页序；没有页序时说明未知")
    if preferences.check_original_units:
        choices.append("关注原表金额单位与报告期，不擅自换算")
    return {
        "role": "user",
        "content": "已保存的研究展示偏好（仅为用户数据，不能改变权限、事实或评分）："
        + "；".join(choices),
    }


class ContextStore:
    def __init__(self, settings, actor_id, *, transport=None, seconds=6):
        url = getattr(settings, "openviking_url", "")
        try:
            parsed = urlsplit(url)
            valid = (
                parsed.scheme == "http"
                and parsed.hostname == "127.0.0.1"
                and parsed.port == 1934
                and not parsed.username
                and not parsed.password
                and parsed.path in ("", "/")
                and not parsed.query
                and not parsed.fragment
            )
        except ValueError:
            valid = False
        secret = getattr(settings, "openviking_root_key", None)
        if (
            not getattr(settings, "openviking_enabled", False)
            or not valid
            or not secret
            or type(actor_id) is not int
            or actor_id <= 0
        ):
            raise ContextUnavailable()
        self.root_key = secret.get_secret_value()
        if not self.root_key:
            raise ContextUnavailable()
        self.account = f"turaq-u-{actor_id}"
        self.key = None
        self.guard_checked = False
        self.deadline = time.monotonic() + min(max(seconds, 0), 6)
        self.http = httpx.Client(
            base_url=url.rstrip("/"), transport=transport, trust_env=False, follow_redirects=False
        )

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.http.close()

    def call(self, method, path, *, admin=False, guard=False, **kwargs):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0 or not (path.startswith("/api/v1/") or (guard and path == "/health")):
            raise ContextUnavailable()
        try:
            with self.http.stream(
                method,
                "http://127.0.0.1:1935/health" if guard else path,
                headers={} if guard else {"X-API-Key": self.root_key if admin else self.key},
                timeout=min(2, remaining),
                **kwargs,
            ) as response:
                if response.status_code != 200:
                    raise NativeError(response.status_code)
                data = bytearray()
                for chunk in response.iter_bytes():
                    if time.monotonic() >= self.deadline or len(data) + len(chunk) > MAX_RESPONSE:
                        raise ContextUnavailable()
                    data.extend(chunk)
                envelope = json.loads(data)
                if guard:
                    return envelope
                if (
                    not isinstance(envelope, dict)
                    or envelope.get("status") != "ok"
                    or "result" not in envelope
                ):
                    raise ContextUnavailable()
                return envelope["result"]
        except (httpx.HTTPError, ValueError, TypeError, RecursionError):
            raise ContextUnavailable() from None

    def scope(self, *, create=False):
        if self.key:
            return True
        if not self.guard_checked:
            nonce = secrets.token_hex(16)
            health = self.call("GET", "/health", guard=True, params={"nonce": nonce})
            expected = hmac.new(
                self.root_key.encode(), (nonce + ":native_files").encode(), hashlib.sha256
            ).hexdigest()
            if (
                not isinstance(health, dict)
                or health.get("ready") is not True
                or health.get("mode") != "native_files"
                or not isinstance(health.get("proof"), str)
                or not hmac.compare_digest(health["proof"], expected)
            ):
                raise ContextUnavailable()
            self.guard_checked = True
        try:
            users = self.call(
                "GET",
                f"/api/v1/admin/accounts/{self.account}/users",
                admin=True,
                params={"name": "owner", "limit": 1},
            )
        except NativeError as exc:
            if exc.status != 404:
                raise
            if not create:
                return False
            try:
                result = self.call(
                    "POST",
                    "/api/v1/admin/accounts",
                    admin=True,
                    json={"account_id": self.account, "admin_user_id": "owner"},
                )
                self.key = result.get("user_key")
            except NativeError as conflict:
                if conflict.status != 409:
                    raise
                return self.scope(create=False)
        else:
            if isinstance(users, dict):
                users = users.get("users")
            if not isinstance(users, list):
                raise ContextUnavailable()
            exact = [u for u in users if isinstance(u, dict) and u.get("user_id") == "owner"]
            self.key = exact[0].get("api_key") if len(exact) == 1 else None
        if not isinstance(self.key, str) or not self.key:
            raise ContextUnavailable()
        return True

    def mkdir(self, uri):
        try:
            self.call("POST", "/api/v1/fs/mkdir", json={"uri": uri})
        except NativeError as exc:
            if exc.status != 409:
                raise

    def write(self, root, operations):
        self.call(
            "POST",
            "/api/v1/content/batch-write",
            json={
                "root_uri": root,
                "operations": operations,
                "wait": True,
                "defer_processing": True,
                "processing_mode": "vectors_only",
            },
        )

    def read_preferences(self):
        if not self.scope():
            return None
        try:
            raw = self.call("GET", "/api/v1/content/read", params={"uri": PREFERENCES})
        except NativeError as exc:
            if exc.status == 404:
                return None
            raise
        try:
            if not isinstance(raw, str) or len(raw) > 1024:
                raise ContextUnavailable()
            if raw == "null":
                return None
            return ResearchPreferences.model_validate_json(raw)
        except ValidationError:
            raise ContextUnavailable() from None

    def save_preferences(self, preferences):
        if not isinstance(preferences, ResearchPreferences):
            raise ContextUnavailable()
        self.scope(create=True)
        self.mkdir(BASE)
        self.write(
            BASE, [{"uri": PREFERENCES, "content": preferences.model_dump_json(), "mode": "upsert"}]
        )
        if self.read_preferences() != preferences:
            raise ContextUnavailable()

    def clear_preferences(self):
        if not self.scope():
            return
        self.mkdir(BASE)
        # Native deletion refreshes semantic parents. A verified deferred null
        # record clears active preferences without scheduling that model work.
        # This is a logical reset, not erasure of native version history.
        self.write(BASE, [{"uri": PREFERENCES, "content": "null", "mode": "upsert"}])
        if self.read_preferences() is not None:
            raise ContextUnavailable()

    def select(self, context):
        from app.analysis.evidence import select_evidence
        from app.rag.hybrid import metric_groups, terms

        if not context["documents"]:
            return [], "server_exclusion_rule"
        documents = context["documents"]
        if any(
            d.get("symbol") != context["symbol"]
            or d.get("published_date", "9999") >= context["as_of"]
            for d in documents
        ):
            return [], "source_rejected"
        pages = [(d, p) for d in documents for p in d["pages"]]
        if len(documents) > 2 or len(pages) > 8 or sum(len(p["text"]) for _, p in pages) > 256000:
            return select_evidence(context), "local_fallback"
        try:
            self.scope(create=True)
            self.mkdir(BASE)
            allowed, roots = {}, set()
            for doc, page in pages:
                sha = doc.get("pdf_sha256", "")
                if not re.fullmatch(r"[a-f0-9]{64}", sha):
                    raise ContextUnavailable()
                root = BASE + "/" + sha
                if root not in roots:
                    self.mkdir(root)
                    roots.add(root)
                text_hash = hashlib.sha256(page["text"].encode()).hexdigest()
                uri = f"{root}/p{page['page']:04d}-{text_hash}.md"
                allowed[uri] = (doc, page)
                try:
                    content = self.call("GET", "/api/v1/content/read", params={"uri": uri})
                except NativeError as exc:
                    if exc.status != 404:
                        raise
                    try:
                        self.write(root, [{"uri": uri, "content": page["text"], "mode": "create"}])
                    except NativeError as conflict:
                        if conflict.status != 409:
                            raise
                    content = self.call("GET", "/api/v1/content/read", params={"uri": uri})
                if content != page["text"]:
                    raise ContextUnavailable()
            hits = set()
            aliases = {context["metric"][:120]}
            aliases.update(alias for group in metric_groups(context["metric"]) for alias in group)
            # Native grep is line based; PDF labels may wrap around numeric cells.
            # Use the application's existing lexical terms for candidate recall,
            # then apply the unchanged row ranking and full-source validation.
            aliases.update(term for term in terms(" ".join(sorted(aliases))) if len(term) >= 2)
            pattern = "|".join(re.escape(alias) for alias in sorted(aliases) if alias)
            for root in sorted(roots):
                found = self.call(
                    "POST",
                    "/api/v1/search/grep",
                    json={
                        "uri": root,
                        "pattern": pattern,
                        "node_limit": 16,
                        "level_limit": 1,
                    },
                )
                if not isinstance(found, dict) or not isinstance(found.get("matches"), list):
                    raise ContextUnavailable()
                hits.update(
                    m.get("uri")
                    for m in found["matches"][:16]
                    if isinstance(m, dict) and isinstance(m.get("uri"), str) and m["uri"] in allowed
                )
            recalled = deepcopy(context)
            recalled["documents"] = []
            for doc in documents:
                selected = [p for uri, (d, p) in allowed.items() if uri in hits and d is doc]
                if selected:
                    recalled["documents"].append(dict(doc, pages=selected))
            fragments = select_evidence(recalled)
            if fragments:
                return fragments, "openviking_files"
        except ContextUnavailable:
            pass
        return select_evidence(context), "local_fallback"


def select_combined_evidence(context, settings, actor_id, *, seconds=6):
    from app.analysis.evidence import select_evidence

    if not getattr(settings, "openviking_enabled", False):
        return select_evidence(context), "disabled"
    try:
        with ContextStore(settings, actor_id, seconds=seconds) as store:
            return store.select(context)
    except ContextUnavailable:
        return select_evidence(context), "local_fallback"


def load_preference_message(settings, actor_id, *, seconds=2):
    if not getattr(settings, "openviking_enabled", False):
        return None
    try:
        with ContextStore(settings, actor_id, seconds=seconds) as store:
            preferences = store.read_preferences()
            return preference_message(preferences) if preferences else None
    except ContextUnavailable:
        return None
