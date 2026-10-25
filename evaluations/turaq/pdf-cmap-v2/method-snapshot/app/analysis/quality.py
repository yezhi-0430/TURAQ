"""Local extraction quality and rule coverage; neither is model accuracy."""

import hashlib
import json
import math
import os
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

from app.analysis.pdf_parser import FinancialReportParser
from app.document_parser import SAFE_ERRORS
from app.report_evidence_eval import load_corpus

MAX_BYTES = 20 * 1024 * 1024
LABELS = dict(
    revenue="营业收入",
    net_profit="净利润",
    total_assets="总资产",
    total_liabilities="总负债",
    current_assets="流动资产",
    current_liabilities="流动负债",
    accounts_receivable="应收账款",
    inventory="存货",
    operating_cash_flow="经营现金流净额",
)
RULES = [
    ("receivable_ratio", "应收账款占营收高于40%", ">", 0.4, "high"),
    ("cash_quality", "经营现金流/净利润低于0.8", "<", 0.8, "high"),
    ("debt_ratio", "资产负债率高于70%", ">", 0.7, "high"),
    ("current_ratio", "流动比率低于1", "<", 1, "medium"),
    ("inventory_turnover", "营收/期末存货低于2（简化口径）", "<", 2, "medium"),
]


@lru_cache(maxsize=1)
def corpus():
    return load_corpus()


def benchmark_for(sha):
    data = corpus()
    doc = next((d for d in data["documents"].values() if d["pdf_sha256"] == sha), None)
    cases = [c for c in data["cases"] if doc and c["document_ids"] == [doc["id"]]]
    return dict(
        state="not_run",
        available=bool(cases),
        case_count=len(cases),
        document_id=doc["id"] if doc else None,
        scope="冻结候选页的事实、引用与拒答测试，不是全篇投研评分",
        reason="点击运行后按金标逐例评分，使用模型额度"
        if cases
        else "该文件尚无独立金标，不能给出模型准确率",
    )


def parse_pdf(data):
    """Use the existing memory-bounded disposable parser; no model/DB access."""
    sha = hashlib.sha256(data).hexdigest()
    data_set = corpus()
    known = next((d for d in data_set["documents"].values() if d["pdf_sha256"] == sha), None)
    if known:
        return known["text_pages"]
    env = {
        k: v
        for k, v in os.environ.items()
        if k.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP"}
    }
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        result = subprocess.run(
            [sys.executable, "-m", "app.document_parser"],
            input=data,
            capture_output=True,
            timeout=45,
            cwd=Path(__file__).resolve().parents[2],
            env=env,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        raise ValueError("PDF解析超时，请缩小文件后重试") from None
    if len(result.stdout) > 8 * 1024 * 1024:
        raise ValueError("PDF文字量超过解析上限")
    try:
        parsed = json.loads(result.stdout)
    except (ValueError, UnicodeError):
        raise ValueError("PDF文本提取失败，未生成财务数据") from None
    if result.returncode or not parsed.get("pages"):
        if parsed.get("error") in SAFE_ERRORS:
            raise ValueError(parsed["error"])
        raise ValueError("PDF文本提取失败，可能为扫描件、加密或无效文件")
    return parsed["pages"]


def analyze_pages(pages, company_name, sha, *, filename="report.pdf", kind="uploaded"):
    if not pages or not any(p["text"].strip() for p in pages):
        raise ValueError("未提取到文字，未生成财务数据")
    parser = FinancialReportParser()
    indicators, citations = dict.fromkeys(LABELS), []
    for page in pages:
        extracted = parser.extract_financial_indicators(page["text"])
        for key in LABELS:
            value = extracted.get(key)
            if indicators[key] is None and value is not None and math.isfinite(value):
                indicators[key] = value
                citations.append(
                    dict(key=key, label=LABELS[key], page=page["page"], **parser.matches[key])
                )
    if all(v is None for v in indicators.values()):
        raise ValueError("未识别到财务指标，请核对PDF文字或更换文件；未使用模拟数据")
    ratios = {}
    for key, numerator, denominator in [
        ("receivable_ratio", "accounts_receivable", "revenue"),
        ("cash_quality", "operating_cash_flow", "net_profit"),
        ("debt_ratio", "total_liabilities", "total_assets"),
        ("current_ratio", "current_assets", "current_liabilities"),
        ("inventory_turnover", "revenue", "inventory"),
    ]:
        a, b = indicators[numerator], indicators[denominator]
        if a is not None and b is not None and b > 0:
            value = a / b
            if math.isfinite(value):
                ratios[key] = value
    checks, risks = [], []
    for key, name, op, threshold, level in RULES:
        value = ratios.get(key)
        triggered = value is not None and (value > threshold if op == ">" else value < threshold)
        checks.append(
            dict(
                name=name,
                status="not_evaluable" if value is None else "triggered" if triggered else "passed",
            )
        )
        if triggered:
            risks.append(dict(name=name, level=level, value=value, threshold=threshold))
    complete = len(ratios) == len(RULES)
    score = (
        max(0, 100 - sum(20 if r["level"] == "high" else 10 for r in risks)) if complete else None
    )
    model = benchmark_for(sha)
    if kind == "demo":
        model.update(available=False, reason="演示数据不作为真实模型评测")
    missing = [dict(key=k, label=v) for k, v in LABELS.items() if indicators[k] is None]
    return dict(
        success=True,
        company_name=company_name,
        source=dict(sha256=sha, filename=filename, page_count=len(pages), kind=kind),
        indicators=indicators,
        ratios=ratios,
        risks=risks,
        report=dict(
            score=score,
            rule_checks=checks,
            recommendation="已完成5项规则检查" if complete else "资料不完整，暂不评级",
            action="规则分不等于模型准确率；请核对期间、单位与原始报表",
        ),
        quality=dict(
            completeness=dict(found=len(LABELS) - len(missing), total=len(LABELS), missing=missing),
            citations=dict(
                state="located_unverified",
                located=len(citations),
                total=len(LABELS),
                items=citations,
            ),
            model=model,
        ),
    )
