"""Regex indicator extraction from already parsed text, with exact match locations.

PDF decoding and limits live in app.document_parser; ratios and risk checks live
in app.analysis.quality.
"""

import logging
import re
from typing import Any, Dict

logger = logging.getLogger(__name__)


class FinancialReportParser:
    """Extract candidate indicators; their financial meaning still needs review."""

    def extract_financial_indicators(self, text: str) -> Dict[str, Any]:
        """
        提取关键财务指标

        Args:
            text: PDF文本内容

        Returns:
            财务指标字典
        """
        indicators = {}
        self.matches = {}

        # 提取模式
        patterns = {
            # 资产负债表指标
            'total_assets': r'资产总计[：:\s]*([\d,\.]+)',
            'total_liabilities': r'负债合计[：:\s]*([\d,\.]+)',
            'equity': r'所有者权益[（(]或股东权益[)）]合计[：:\s]*([\d,\.]+)',
            'current_assets': r'流动资产合计[：:\s]*([\d,\.]+)',
            'current_liabilities': r'流动负债合计[：:\s]*([\d,\.]+)',
            'accounts_receivable': r'应收账款[：:\s]*([\d,\.]+)',
            'inventory': r'存货[：:\s]*([\d,\.]+)',
            'monetary_funds': r'货币资金[：:\s]*([\d,\.]+)',

            # 利润表指标
            'revenue': r'营业收入[：:\s]*([\d,\.]+)',
            'operating_profit': r'营业利润[：:\s]*([\d,\.]+)',
            'net_profit': r'净利润[：:\s]*([\d,\.]+)',
            'gross_profit': r'毛利润[：:\s]*([\d,\.]+)',

            # 现金流量表指标
            'operating_cash_flow': r'经营活动产生的现金流量净额[：:\s]*([\d,\.]+)',
            'investing_cash_flow': r'投资活动产生的现金流量净额[：:\s]*([\d,\.]+)',
            'financing_cash_flow': r'筹资活动产生的现金流量净额[：:\s]*([\d,\.]+)',
        }

        for key, pattern in patterns.items():
            match = re.search(pattern, text)
            if match:
                value_str = match.group(1).replace(',', '')
                try:
                    indicators[key] = float(value_str)
                    self.matches[key] = dict(
                        start=match.start(), end=match.end(), quote=text[match.start():match.end()]
                    )
                except:
                    indicators[key] = None
            else:
                indicators[key] = None

        logger.info(f'提取到 {len([v for v in indicators.values() if v is not None])} 个财务指标')

        return indicators
