"""Read-only, server-issued document IDs; no arbitrary URLs or certified model numbers."""

from datetime import date
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.disclosures import DisclosureUnavailable
from app.tools.market_data import StockProfileArguments

DocumentID = Annotated[str, StringConstraints(strict=True, pattern=r"^[a-f0-9]{24}$")]
Query = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=40)
]


class ReportArguments(StockProfileArguments):
    # The disclosure source returns at most 30 rows per page; use `page` for more.
    limit: int = Field(default=30, strict=True, ge=1, le=30)
    page: int = Field(default=1, strict=True, ge=1, le=10000)


class AnnouncementArguments(ReportArguments):
    date_from: date
    date_to: date


class ReadDocumentArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: DocumentID
    start_page: int = Field(default=1, strict=True, ge=1, le=500)
    page_count: int = Field(default=2, strict=True, ge=1, le=500)


class SearchDocumentArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: DocumentID
    query: Query
    limit: int = Field(default=3, strict=True, ge=1, le=5)


class FinancialSectionsArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: DocumentID


class CompareReportArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_ids: list[DocumentID] = Field(min_length=2, max_length=2)
    query: Query


def financial_sections(reader, document_id):
    value = reader.document(document_id)
    selected = []
    for page in value["pages"]:
        if any(
            term in page["text"]
            for term in [
                "主要会计数据",
                "营业收入",
                "现金流量表",
                "审计意见",
                "重大风险",
                "资产负债表",
            ]
        ):
            selected.append(dict(page=page["page"], text=page["text"]))
    result = reader.result(value, selected)
    result["warnings"].append(
        "财务章节为原文候选片段，字段、币种、单位及期间须对照原表；未自动认证数值或计算同比。"
    )
    return result


def run_document_tool(name, arguments, reader):
    if reader is None:
        raise DisclosureUnavailable("文档能力在离线测试模式下未启用，不会联网")
    if name == "search_company_reports":
        return reader.list(
            arguments.stock_code, reports=True, limit=arguments.limit, page=arguments.page
        )
    if name == "list_company_announcements":
        return reader.list(
            arguments.stock_code,
            limit=arguments.limit,
            date_from=arguments.date_from,
            date_to=arguments.date_to,
            page=arguments.page,
        )
    if name == "read_disclosure_document":
        return reader.read(arguments.document_id, arguments.start_page, arguments.page_count)
    if name == "search_disclosure_text":
        return reader.search(arguments.document_id, arguments.query, arguments.limit)
    if name == "extract_financial_sections":
        return financial_sections(reader, arguments.document_id)
    results = [reader.search(doc, arguments.query, 2) for doc in arguments.document_ids]
    if results[0]["document"]["symbol"] != results[1]["document"]["symbol"]:
        raise DisclosureUnavailable("报告对照须为同一股票，不能混用公司数据")
    return dict(
        reports=results,
        data_status="available" if all(r["excerpts"] for r in results) else "insufficient_data",
        source=results[0]["source"],
        warnings=["并列报告原文，非自动财务数字认证；报告期、单位、合并范围及更正版本须核对。"],
    )
