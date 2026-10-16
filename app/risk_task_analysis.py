"""Server-observed facts and cited excerpts, independent from model prose."""

import json
from datetime import datetime, timedelta
from types import SimpleNamespace

from app.agent_market import MarketHistoryReader
from app.agent_research import ResearchMarketReader
from app.disclosures import DisclosureReader, DisclosureUnavailable
from app.market import SHANGHAI
from app.tools.documents import financial_sections
from app.tools.executor import execute_tool


def collect_stock(symbol, days, admission, *, end_date=None, include_documents=True):
    facts, warnings, evidence, observations = [], [], [], []
    coverage = dict(market="not_connected", reports="not_connected", announcements="not_connected")
    snapshot = dict(
        facts=facts,
        warnings=warnings,
        evidence=evidence,
        coverage=coverage,
        trade_date=None,
        input_text="",
        context=dict(observations=observations, knowledge_references=[], historical_cases=[]),
    )
    if admission.settings.model_provider != "qwen":
        warnings.append("隔离测试模式：未联网读取行情或文档，未进行真实分析。")
        snapshot["input_text"] = warnings[0]
        return snapshot

    # Leave budget for the model; document work cannot consume the full 60 seconds.
    def remaining():
        left = admission.remaining() - (20 if include_documents else 0)
        if left <= 0:
            raise DisclosureUnavailable("资料读取预算已用尽，保留已有资料")
        return left

    history = MarketHistoryReader(remaining)
    session = SimpleNamespace(
        info={"daily_price_reader": history, "research_reader": ResearchMarketReader(history)}
    )
    end = end_date or datetime.now(SHANGHAI).date()
    start = end - timedelta(days=days - 1)
    indicator_start = start if include_documents else end - timedelta(days=max(days, 180) - 1)
    volume_start = indicator_start if not include_documents and days < 60 else start
    market_states = []
    for name, args in [
        ("get_stock_quotes", dict(stock_codes=[symbol])),
        (
            "calculate_technical_indicators",
            dict(
                stock_code=symbol,
                start_date=str(indicator_start),
                end_date=str(end),
                ma_periods=[5, 20, 60],
            ),
        ),
        (
            "analyze_price_volume",
            dict(stock_code=symbol, start_date=str(volume_start), end_date=str(end)),
        ),
        (
            "analyze_market_context",
            dict(stock_code=symbol, start_date=str(indicator_start), end_date=str(end)),
        ),
    ]:
        result = execute_tool(name, json.dumps(args), session)
        if result.status != "success":
            market_states.append("failed")
            warnings.append(result.error.message)
            continue
        observations.append(
            dict(capability=name, data=result.result, source=result.source.model_dump(mode="json"))
        )
        market_states.append(result.result["data_status"])
        coverage["market"] = (
            "available" if result.result["data_status"] == "available" else "partial"
        )
        source = result.source
        if source.latest_trade_date:
            snapshot["trade_date"] = str(source.latest_trade_date)
        if name == "analyze_market_context":
            assessment = result.result["assessment"]
            snapshot["trade_date"] = assessment.get("latest_trade_date")
            snapshot["context"]["market_assessment"] = assessment
            coverage["sectors"] = result.result["sector_coverage"]
            facts.extend(assessment["basis"])
            warnings.extend(result.result["warnings"])
        elif name == "get_stock_quotes":
            q = result.result["quotes"][0]
            facts.append(f"{symbol}报价 {q.get('price')}，实际观测时间 {q.get('quote_time')}。")
        else:
            label = "技术指标" if name == "calculate_technical_indicators" else "量价统计"
            facts.append(
                f"{label}使用{source.record_count}条实际返回日线，最新交易日{source.latest_trade_date}；"
                "不复权，覆盖未完全核验。"
            )
        evidence.append(
            dict(
                kind="market_observation",
                verification="observed",
                title="公开行情与程序统计",
                date=str(source.latest_trade_date) if source.latest_trade_date else None,
                url=None,
                page=None,
                excerpt=json.dumps(result.result, ensure_ascii=False)[:12000],
                conclusion_refs=[],
            )
        )
    if not observations:
        coverage["market"] = "failed"
    elif any(state != "available" for state in market_states):
        coverage["market"] = "partial"
    if not include_documents:
        snapshot["input_text"] = json.dumps(
            dict(
                symbol=symbol,
                facts=facts,
                assessment=snapshot["context"].get("market_assessment", {}),
            ),
            ensure_ascii=False,
        )
        return snapshot
    reader = DisclosureReader(remaining)
    for kind, reports, limit in [("reports", True, 5), ("announcements", False, 3)]:
        try:
            listing = reader.list(
                symbol,
                reports=reports,
                limit=limit,
                **(
                    dict(date_from=end - timedelta(days=730), date_to=end)
                    if reports
                    else dict(date_from=start, date_to=end)
                ),
            )
            coverage[kind] = "no_data" if not listing["documents"] else "partial"
            warnings.extend(listing["warnings"])
            if not listing["documents"]:
                warnings.append(
                    "指定范围未返回财报。"
                    if reports
                    else "指定范围未返回公告；不能认定无公告风险。"
                )
            chosen = listing["documents"][:1]
            if reports:
                annual = next(
                    (
                        d
                        for d in listing["documents"]
                        if "年度报告" in (d["report_period"] or "")
                        and "半年度" not in (d["report_period"] or "")
                    ),
                    None,
                )
                if annual and annual not in chosen:
                    chosen.append(annual)
            for document in chosen:
                content = (
                    financial_sections(reader, document["document_id"])
                    if reports
                    else reader.read(document["document_id"], 1, 2)
                )
                facts.append(
                    f"已获取《{document['title']}》，发布日期{document['published_date']}，本次只读取相关原文片段。"
                )
                warnings.extend(content["warnings"])
                for excerpt in content["excerpts"][:4]:
                    evidence.append(
                        dict(
                            kind="public_document",
                            verification="source_retrieved",
                            title=document["title"],
                            date=document["published_date"],
                            url=document["url"],
                            page=str(excerpt["page"]),
                            excerpt=excerpt["text"],
                            document_id=document["document_id"],
                            report_period=document["report_period"],
                            conclusion_refs=[],
                        )
                    )
        except (DisclosureUnavailable, OSError, ValueError) as exc:
            coverage[kind] = "failed"
            warnings.append(str(exc)[:150])
    warnings.append(
        "市场评级仅表示已观测趋势、量能和板块的研究关注程度；披露覆盖与公司基本面风险单独核实。"
    )
    material = dict(
        symbol=symbol,
        interval=dict(start=str(start), end=str(end)),
        facts=facts,
        coverage=coverage,
        calculations=[o["data"] for o in observations],
        excerpts=[
            {k: e.get(k) for k in ("title", "date", "page", "excerpt")}
            for e in evidence
            if e["kind"] == "public_document"
        ],
        warnings=warnings,
    )
    text = json.dumps(material, ensure_ascii=False)
    while len(text) > 18000 and material["excerpts"]:
        material["excerpts"].pop()
        text = json.dumps(material, ensure_ascii=False)
    snapshot["input_text"] = (
        "以下是服务端实际资料；不保证完整覆盖。结合事实与原文解释，所有数值计算以程序结果为准，不猜财报或评级。\n"
        + text
    )
    snapshot["warnings"] = list(dict.fromkeys(warnings))
    return snapshot
