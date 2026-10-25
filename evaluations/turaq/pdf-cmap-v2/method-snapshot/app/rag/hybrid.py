"""Experimental, explicitly scoped local retrieval; no business routing or gold access."""

import math
import re
from collections import Counter
from copy import deepcopy

from .scoring import cosine_similarity
from .table_chunks import table_units

VERSION = "table-bm25-bge-rrf-v1"
CONFIG = dict(
    lexical_candidates=12,
    dense_candidates=12,
    rrf_k=60,
    dense_min_cosine=0.5,
    max_units=3,
    max_visible_characters=4800,
)

# General financial label synonyms. These describe labels, never source locations or values.
ALIASES = (
    ("营业收入", "营业总收入", "营收"),
    (
        "归母净利润",
        "归属于上市公司股东的净利润",
        "归属于母公司股东的净利润",
        "归属于母公司所有者的净利润",
        "归属于本行股东的净利润",
    ),
    ("扣非净利润", "扣除非经常性损益后的净利润", "扣除非经常性损益的净利润"),
    (
        "经营活动现金流量净额",
        "经营活动产生的现金流量净额",
        "经营活动产生的现金净流量",
        "经营现金流",
    ),
    ("总资产", "资产总额", "资产总计"),
    ("净资产", "所有者权益合计", "股东权益合计"),
    ("不良贷款率", "不良率"),
    ("基本每股收益", "每股盈利"),
    ("稀释每股收益", "摊薄每股收益"),
    ("净资产收益率", "ROE"),
    ("毛利率", "销售毛利率"),
    ("资产负债率", "负债资产比率"),
    ("研发费用", "研发支出"),
    ("应收账款", "应收款项"),
    ("存货", "库存商品"),
)
_STOP = (
    "依据 根据 年度报告 报告 年报 财报 提取 请问 使用 原表 单位 数值 "
    "标注 所在 原文 位置 引用 给出"
).split()


def compact(text):
    return re.sub(r"\s+", "", text).lower()


def label(text):
    # Wrapped labels can have a numeric row inserted before their last syllable.
    return re.sub(r"[\W\d_]+", "", text).lower()


def terms(text):
    text = compact(text)
    for stop in _STOP:
        text = text.replace(stop, " ")
    tokens = re.findall(r"[a-z]+|\d+(?:\.\d+)?", text)
    for run in re.findall(r"[\u4e00-\u9fff]+", text):
        tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
    return Counter(tokens)


def bm25(query, documents):
    qterms = terms(query)
    counts = [terms(text) for text in documents]
    lengths = [sum(c.values()) for c in counts]
    average = sum(lengths) / len(lengths) if lengths else 1
    frequencies = Counter(term for count in counts for term in count)
    scores = []
    for count, length in zip(counts, lengths, strict=True):
        score = 0.0
        for term in qterms:
            tf = count[term]
            if tf:
                df = frequencies[term]
                idf = math.log(1 + (len(counts) - df + 0.5) / (df + 0.5))
                score += idf * tf * 2.5 / (tf + 1.5 * (0.25 + 0.75 * length / (average or 1)))
        scores.append(score)
    return scores


def metric_groups(query):
    query = compact(query)
    return [
        tuple(compact(a) for a in group)
        for group in ALIASES
        if any(compact(a) in query for a in group)
    ]


def period_compatibility(query, unit):
    quarterly = bool(re.search(r"q[1-4]|第[一二三四]季度|\d+至\d+月", compact(query)))
    header = "".join(h["text"] for h in unit["headers"])
    has_quarters = bool(re.search(r"第[一二三四]季度", header))
    return int(quarterly == has_quarters)


class HybridRetriever:
    """Caller supplies authorized resource ids; filtering precedes both rankers."""

    def __init__(self, resources, embedding_service):
        self.resources = {r["id"]: deepcopy(r) for r in resources}
        if len(self.resources) != len(resources):
            raise ValueError("duplicate resource id")
        self.embedding_service = embedding_service
        self.units = []
        for resource in resources:
            for unit in table_units(resource["text"]):
                for part in [unit["body"], *unit["headers"]]:
                    if part["text"] != resource["text"][part["char_start"] : part["char_end"]]:
                        raise ValueError("source slice mismatch")
                body = unit["body"]
                self.units.append(
                    dict(
                        unit,
                        resource_id=resource["id"],
                        document_id=resource["document_id"],
                        page=resource["page"],
                        id=f"{resource['id']}:{unit['kind']}:{body['char_start']}:{body['char_end']}",
                    )
                )
        self.vectors = (
            embedding_service.embed_documents([u["search_text"] for u in self.units])
            if self.units
            else []
        )
        if len(self.vectors) != len(self.units):
            raise ValueError("document vector count mismatch")
        dimension = len(self.vectors[0]) if len(self.vectors) else None
        if any(len(v) != dimension or cosine_similarity(v, v) is None for v in self.vectors):
            raise ValueError("invalid document vector")

    def find(self, query, allowed_ids, limit=3, mode="hybrid"):
        if (
            type(limit) is not int
            or not 1 <= limit <= CONFIG["max_units"]
            or mode not in {"hybrid", "lexical"}
        ):
            raise ValueError("invalid retrieval configuration")
        if not set(allowed_ids) <= self.resources.keys():
            raise ValueError("unknown resource in scope")
        selected = [i for i, u in enumerate(self.units) if u["resource_id"] in allowed_ids]
        if not selected:
            return []
        groups = metric_groups(query)
        expanded = query + " " + " ".join(alias for group in groups for alias in group)
        lexical_scores = bm25(expanded, [self.units[i]["search_text"] for i in selected])
        lexical_by_id = dict(zip(selected, lexical_scores, strict=True))
        lexical = sorted(
            (i for i, score in lexical_by_id.items() if score > 0),
            key=lambda i: (-lexical_by_id[i], self.units[i]["id"]),
        )[: CONFIG["lexical_candidates"]]
        similarities = {}
        if mode == "hybrid":
            qvector = self.embedding_service.embed_query(query)
            if cosine_similarity(qvector, qvector) is None:
                return []
            similarities = {i: cosine_similarity(qvector, self.vectors[i]) for i in selected}
            if any(score is None for score in similarities.values()):
                return []
        dense = sorted(
            (i for i, score in similarities.items() if score >= CONFIG["dense_min_cosine"]),
            key=lambda i: (-similarities[i], self.units[i]["id"]),
        )[: CONFIG["dense_candidates"]]
        fused = {}
        for ranking in (lexical, dense):
            for rank, i in enumerate(ranking, 1):
                fused[i] = fused.get(i, 0.0) + 1 / (CONFIG["rrf_k"] + rank)

        def rerank(i):
            unit = self.units[i]
            coverage = sum(any(a in label(unit["body"]["text"]) for a in group) for group in groups)
            return (
                -coverage,
                -period_compatibility(query, unit),
                -int(coverage > 0 and unit["kind"] == "table_row"),
                -fused[i],
                unit["id"],
            )

        result = []
        characters = 0
        for i in sorted(fused, key=rerank):
            unit = self.units[i]
            body = unit["body"]
            duplicate = False
            for old in result:
                if old["resource_id"] == unit["resource_id"]:
                    other = old["body"]
                    overlap = max(
                        0,
                        min(body["char_end"], other["char_end"])
                        - max(body["char_start"], other["char_start"]),
                    )
                    if overlap >= 0.8 * min(len(body["text"]), len(other["text"])):
                        duplicate = True
            if duplicate:
                continue
            parts = [*unit["headers"], body]
            size = sum(len(part["text"]) for part in parts)
            if characters + size > CONFIG["max_visible_characters"]:
                continue
            result.append(
                deepcopy(dict(unit, parts=parts, cosine=similarities.get(i), fusion_score=fused[i]))
            )
            characters += size
            if len(result) == limit:
                break
        return result
