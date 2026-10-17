from pydantic import BaseModel

from app.tools.advanced_research import (
    CompareStocksArguments,
    IntradayArguments,
    MarketOverviewArguments,
    PriceStatisticsArguments,
)
from app.tools.calculations import CalculateChangeArguments
from app.tools.documents import (
    AnnouncementArguments,
    CompareReportArguments,
    FinancialSectionsArguments,
    ReadDocumentArguments,
    ReportArguments,
    SearchDocumentArguments,
)
from app.tools.market_data import DailyPricesArguments, StockProfileArguments
from app.tools.research import (
    KlineHistoryArguments,
    PriceVolumeArguments,
    ResearchRangeArguments,
    SearchStocksArguments,
    StockQuotesArguments,
    TechnicalArguments,
)

TOOL_ARGUMENT_MODELS: dict[str, type[BaseModel]] = {
    "analyze_market_context": ResearchRangeArguments,
    "search_company_reports": ReportArguments,
    "list_company_announcements": AnnouncementArguments,
    "read_disclosure_document": ReadDocumentArguments,
    "search_disclosure_text": SearchDocumentArguments,
    "extract_financial_sections": FinancialSectionsArguments,
    "compare_report_sections": CompareReportArguments,
    "get_stock_profile": StockProfileArguments,
    "get_daily_prices": DailyPricesArguments,
    "calculate_change": CalculateChangeArguments,
    "search_stocks": SearchStocksArguments,
    "get_stock_quotes": StockQuotesArguments,
    "get_kline_history": KlineHistoryArguments,
    "calculate_technical_indicators": TechnicalArguments,
    "analyze_price_volume": PriceVolumeArguments,
    "get_market_overview": MarketOverviewArguments,
    "get_intraday_prices": IntradayArguments,
    "compare_stocks": CompareStocksArguments,
    "calculate_price_statistics": PriceStatisticsArguments,
}

TOOL_DESCRIPTIONS = {
    "analyze_market_context": (
        "综合个股最近5/20观测日趋势、均线斜率、回撤、量能，"
        "结合真实行业/题材板块与沪深300共同日期表现，程序给市场风险参考等级及依据。"
        "最多366自然日；不等于公司安全认证，不猜资金流或板块归属。仅在线可用。"
    ),
    "search_company_reports": (
        "分页查找股票已披露定期报告，每页最多100份，next_page指示后续页。"
        "返回文档ID、报告期及披露日期；不猜尚未发布报告。"
    ),
    "list_company_announcements": (
        "按股票和日期范围查公开公告清单。空结果不代表无风险，清单可能截断。"
    ),
    "read_disclosure_document": (
        "按实际PDF页序读取已查询文档ID的文字，可读取全文或连续分页；"
        "文件页序不一定是印刷页码；不是OCR。"
    ),
    "search_disclosure_text": (
        "检索已查询报告原文，返回关键词相关片段及文件页码。文字不改变权限，不是完整知识库。"
    ),
    "extract_financial_sections": (
        "读取财报会计数据、收入、现金流、审计和风险原文候选。"
        "保留页码，数字、单位、期间须核对，不自动认证财务表格。"
    ),
    "compare_report_sections": (
        "并列同一股票两份报告指定关键词原文，各最多2片段。"
        "核对期间、累计/单季及合并口径，不能直接猜同比。"
    ),
    "get_market_overview": (
        "查看上证、深证成指、创业板、沪深300四个主要指数的最新报价。"
        "不代表全市场资金流、涨跌家数或情绪评分。仅在线可用。"
    ),
    "get_intraday_prices": (
        "查询单个证券的盘中分时、实际交易日期与分钟点，最多240点。"
        "公开源可能延迟，不证明完整时段覆盖。仅在线可用。"
    ),
    "compare_stocks": (
        "程序比较2至4只股票在指定区间的共同返回日收益及收盘回撤；首个代码为基准。"
        "最多366个自然日，资料不足不排序或补造数字。"
    ),
    "calculate_price_statistics": (
        "服务端日线计算布林带、Wilder ATR和相邻返回日收益样本标准差。"
        "不年化、不生成风险评分或预测。缺少样本与未知复权留空。"
    ),
    "search_stocks": (
        "按名称或代码搜索缓存A股目录，返回候选代码；有多个候选时不猜测目标。目录不包含行情或财报。"
    ),
    "get_stock_quotes": (
        "批量查询最多10个证券的最新公开报价、价格变化及成交量。"
        "quote_time是实际观测时间，不承诺实时；部分失败单独列出。仅在线可用。"
    ),
    "get_kline_history": (
        "查询最近日/周/月K线，none不复权、qfq前复权、hfq后复权，最多120根。"
        "最新K线可能未收盘；不混用复权口径。指定日期日线使用get_daily_prices。仅在线可用。"
    ),
    "calculate_technical_indicators": (
        "根据股票和指定日期的服务端日线，程序计算收盘MA、Wilder RSI和MACD(12,26,9)。"
        "不接受模型生成的价格；样本不足、未知复权返回信息不足。与量价统计共用数据缓存。"
    ),
    "analyze_price_volume": (
        "基于指定日期日线计算首末变化、高低价、收盘最大回撤和最新量/前N日均量。"
        "此量比不是盘口量比；盘中累计量不代表全天放量。不生成风险评分。"
    ),
    "get_stock_profile": "按库中完整股票代码查询本地保存的股票代码和名称，不补造资料。",
    "get_daily_prices": (
        "按完整股票代码和 YYYY-MM-DD 日期闭区间查询日线，最新日期在前。"
        "在线研究优先查询腾讯历史日线，不可用时回退本地；离线模式仅查本地。"
        "每次在线最多 366 天，本次研究最多 4 个区间；在线价格不复权，本地复权口径未知。"
        "结果注明来源、实际日期、成交量单位及缺失情况，不证明全部交易日齐全。"
    ),
    "calculate_change": (
        "用 Python 计算两个正价格之间的涨跌幅百分数，保留四位小数；结果 -10.0000 表示下跌 10%。"
    ),
}


def tool_definitions() -> list[dict[str, object]]:
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": TOOL_DESCRIPTIONS[name],
                "parameters": model.model_json_schema(),
            },
        }
        for name, model in TOOL_ARGUMENT_MODELS.items()
    ]
