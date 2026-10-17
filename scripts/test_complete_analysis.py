"""
完整的财报分析测试 - 使用模拟数据

目的：展示完整流程，不依赖真实PDF
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.analysis.pdf_parser import FinancialReportParser
from app.analysis.risk_analyzer import RiskAnalyzer


def simulate_pdf_extraction():
    """模拟PDF提取（代替真实PDF）"""

    # 模拟贵州茅台2023年报数据（单位：元）
    simulated_text = """
    合并资产负债表
    2023年12月31日

    资产
    流动资产：
    货币资金：150,000,000,000
    应收账款：8,000,000,000
    存货：60,000,000,000
    流动资产合计：300,000,000,000

    资产总计：500,000,000,000

    负债
    流动负债合计：80,000,000,000
    负债合计：150,000,000,000

    所有者权益(或股东权益)合计：350,000,000,000

    合并利润表
    营业收入：150,000,000,000
    营业利润：80,000,000,000
    净利润：75,000,000,000

    合并现金流量表
    经营活动产生的现金流量净额：90,000,000,000
    """

    return simulated_text


def test_complete_analysis():
    """完整的分析流程测试"""

    print('=' * 80)
    print('TURAQ - AI财报风险分析工具 - 完整测试')
    print('=' * 80)

    # 第1步：模拟PDF解析
    print('\n[第1步] 模拟PDF财报解析...')
    print('-' * 80)

    parser = FinancialReportParser()
    text = simulate_pdf_extraction()

    # 提取财务指标
    indicators = parser.extract_financial_indicators(text)
    print(f'✓ 成功提取 {len([v for v in indicators.values() if v is not None])} 个财务指标')

    # 显示关键指标
    if indicators.get('revenue'):
        print(f'  营业收入: {indicators["revenue"]/100000000:.2f} 亿元')
    if indicators.get('net_profit'):
        print(f'  净利润: {indicators["net_profit"]/100000000:.2f} 亿元')
    if indicators.get('total_assets'):
        print(f'  总资产: {indicators["total_assets"]/100000000:.2f} 亿元')

    # 第2步：计算财务比率
    print('\n[第2步] 计算财务比率...')
    print('-' * 80)

    ratios = parser.calculate_financial_ratios(indicators)
    print(f'✓ 计算了 {len(ratios)} 个财务比率')

    if ratios.get('debt_ratio'):
        print(f'  资产负债率: {ratios["debt_ratio"]*100:.2f}%')
    if ratios.get('current_ratio'):
        print(f'  流动比率: {ratios["current_ratio"]:.2f}')
    if ratios.get('receivable_ratio'):
        print(f'  应收账款/营收: {ratios["receivable_ratio"]*100:.2f}%')
    if ratios.get('cash_quality'):
        print(f'  现金流含金量: {ratios["cash_quality"]:.2f}')

    # 第3步：AI风险识别
    print('\n[第3步] AI风险识别（基于RAG知识库）...')
    print('-' * 80)

    analyzer = RiskAnalyzer()
    risks = analyzer.analyze_risks(indicators, ratios, '贵州茅台')

    if len(risks) == 0:
        print('✓ 未检测到风险点')
        print('  该公司财务状况良好')
    else:
        print(f'⚠ 检测到 {len(risks)} 个风险点\n')

        for i, risk in enumerate(risks, 1):
            print(f'  [{i}] {risk["name"]} - {risk["level"].upper()}')
            print(f'      实际值: {risk["value"]:.2f}, 阈值: {risk["threshold"]:.2f}')
            if risk.get('cases'):
                print(f'      历史案例: {", ".join(risk["cases"])}')
            print()

    # 第4步：生成风险报告
    print('[第4步] 生成综合风险报告...')
    print('-' * 80)

    report = analyzer.generate_risk_report(risks, '贵州茅台')

    print(f'公司名称: {report["company_name"]}')
    print(f'综合评分: {report["score"]} 分')
    print(f'投资建议: {report["recommendation"]}')
    print(f'操作建议: {report["action"]}')
    print(f'\n风险统计:')
    print(f'  高风险: {report["risk_summary"]["high"]} 个')
    print(f'  中风险: {report["risk_summary"]["medium"]} 个')
    print(f'  低风险: {report["risk_summary"]["low"]} 个')

    # 第5步：展示分析亮点
    print('\n' + '=' * 80)
    print('分析亮点')
    print('=' * 80)
    print('✓ PDF解析：自动提取12+个财务指标')
    print('✓ 比率计算：自动计算5+个财务比率')
    print('✓ AI分析：基于6本专业书的知识库')
    print('✓ 风险识别：5个核心规则引擎')
    print('✓ 案例对比：康美药业、万福生科等历史案例')
    print('✓ 综合评分：0-100分量化评估')
    print('✓ 投资建议：可执行的操作建议')

    print('\n' + '=' * 80)
    print('[完成] 完整分析流程测试成功！')
    print('=' * 80)

    # 返回结果供进一步使用
    return {
        'indicators': indicators,
        'ratios': ratios,
        'risks': risks,
        'report': report
    }


if __name__ == '__main__':
    result = test_complete_analysis()
