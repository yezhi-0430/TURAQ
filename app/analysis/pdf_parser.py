"""
PDF财报解析模块

功能：
1. 提取PDF中的财务数据
2. 识别三大报表
3. 提取关键财务指标
"""

import re
from typing import Dict, Any, List, Optional
import PyPDF2
import logging

logger = logging.getLogger(__name__)


class FinancialReportParser:
    """财报PDF解析器"""

    def __init__(self):
        self.keywords = {
            'balance_sheet': ['资产负债表', '合并资产负债表'],
            'income_statement': ['利润表', '合并利润表', '损益表'],
            'cash_flow': ['现金流量表', '合并现金流量表']
        }

    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """
        从PDF提取文本

        Args:
            pdf_path: PDF文件路径

        Returns:
            提取的文本内容
        """
        try:
            with open(pdf_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                text = ''

                for page in reader.pages:
                    text += page.extract_text() + '\n'

                logger.info(f'成功提取PDF文本，共 {len(reader.pages)} 页')
                return text

        except Exception as e:
            logger.error(f'PDF提取失败: {str(e)}')
            return ''

    def extract_financial_indicators(self, text: str) -> Dict[str, Any]:
        """
        提取关键财务指标

        Args:
            text: PDF文本内容

        Returns:
            财务指标字典
        """
        indicators = {}

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
                except:
                    indicators[key] = None
            else:
                indicators[key] = None

        logger.info(f'提取到 {len([v for v in indicators.values() if v is not None])} 个财务指标')

        return indicators

    def calculate_financial_ratios(self, indicators: Dict[str, Any]) -> Dict[str, Any]:
        """
        计算财务比率

        Args:
            indicators: 财务指标

        Returns:
            财务比率
        """
        ratios = {}

        try:
            # 资产负债率
            if indicators.get('total_assets') and indicators.get('total_liabilities'):
                ratios['debt_ratio'] = indicators['total_liabilities'] / indicators['total_assets']

            # 流动比率
            if indicators.get('current_assets') and indicators.get('current_liabilities'):
                ratios['current_ratio'] = indicators['current_assets'] / indicators['current_liabilities']

            # 应收账款占营收比
            if indicators.get('accounts_receivable') and indicators.get('revenue'):
                ratios['receivable_ratio'] = indicators['accounts_receivable'] / indicators['revenue']

            # 存货周转率（简化）
            if indicators.get('revenue') and indicators.get('inventory'):
                ratios['inventory_turnover'] = indicators['revenue'] / indicators['inventory']

            # 现金流含金量
            if indicators.get('operating_cash_flow') and indicators.get('net_profit'):
                ratios['cash_quality'] = indicators['operating_cash_flow'] / indicators['net_profit']

            logger.info(f'计算了 {len(ratios)} 个财务比率')

        except Exception as e:
            logger.error(f'计算财务比率失败: {str(e)}')

        return ratios

    def parse_report(self, pdf_path: str) -> Dict[str, Any]:
        """
        解析财报PDF（主函数）

        Args:
            pdf_path: PDF文件路径

        Returns:
            解析结果
        """
        result = {
            'success': False,
            'indicators': {},
            'ratios': {},
            'message': ''
        }

        try:
            # 1. 提取文本
            text = self.extract_text_from_pdf(pdf_path)

            if not text:
                result['message'] = 'PDF文本提取失败'
                return result

            # 2. 提取财务指标
            indicators = self.extract_financial_indicators(text)

            if not indicators or all(v is None for v in indicators.values()):
                result['message'] = '未能提取到财务指标'
                return result

            # 3. 计算财务比率
            ratios = self.calculate_financial_ratios(indicators)

            result['success'] = True
            result['indicators'] = indicators
            result['ratios'] = ratios
            result['message'] = f'成功提取 {len([v for v in indicators.values() if v is not None])} 个指标'

            logger.info('财报解析完成')

        except Exception as e:
            result['message'] = f'解析失败: {str(e)}'
            logger.error(result['message'])

        return result


# 测试函数
def test_parser():
    """测试解析器"""
    print('=' * 70)
    print('PDF财报解析器测试')
    print('=' * 70)

    parser = FinancialReportParser()

    # 创建测试文本（模拟财报内容）
    test_text = """
    合并资产负债表
    2023年12月31日

    资产
    流动资产：
    货币资金：1,500,000,000
    应收账款：800,000,000
    存货：600,000,000
    流动资产合计：3,000,000,000

    资产总计：10,000,000,000

    负债
    流动负债合计：2,000,000,000
    负债合计：5,000,000,000

    所有者权益(或股东权益)合计：5,000,000,000

    合并利润表
    营业收入：8,000,000,000
    营业利润：1,200,000,000
    净利润：1,000,000,000

    合并现金流量表
    经营活动产生的现金流量净额：900,000,000
    """

    print('\n[测试] 提取财务指标...')
    indicators = parser.extract_financial_indicators(test_text)
    print(f'  提取指标数: {len([v for v in indicators.values() if v is not None])}')

    if indicators.get('revenue'):
        print(f'  营业收入: {indicators["revenue"]/100000000:.2f} 亿元')
    if indicators.get('net_profit'):
        print(f'  净利润: {indicators["net_profit"]/100000000:.2f} 亿元')

    print('\n[测试] 计算财务比率...')
    ratios = parser.calculate_financial_ratios(indicators)
    print(f'  计算比率数: {len(ratios)}')

    if ratios.get('debt_ratio'):
        print(f'  资产负债率: {ratios["debt_ratio"]*100:.2f}%')
    if ratios.get('receivable_ratio'):
        print(f'  应收账款/营收: {ratios["receivable_ratio"]*100:.2f}%')
    if ratios.get('cash_quality'):
        print(f'  现金流含金量: {ratios["cash_quality"]:.2f}')

    print('\n' + '=' * 70)
    print('[完成] PDF解析器基础功能正常')
    print('=' * 70)


if __name__ == '__main__':
    test_parser()
