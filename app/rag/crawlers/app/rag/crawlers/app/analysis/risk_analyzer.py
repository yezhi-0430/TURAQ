"""
AI风险识别引擎

功能：
1. 基于财务指标识别风险
2. 结合RAG知识库提供分析
3. 生成风险报告
"""

from typing import Dict, Any, List
import logging
from app.rag.core import get_rag_system

logger = logging.getLogger(__name__)


class RiskLevel:
    """风险等级"""
    HIGH = 'high'
    MEDIUM = 'medium'
    LOW = 'low'


class RiskAnalyzer:
    """风险分析引擎"""

    def __init__(self):
        self.rag = get_rag_system()
        self.risk_rules = self._load_risk_rules()

    def _load_risk_rules(self) -> List[Dict[str, Any]]:
        """
        加载风险识别规则

        Returns:
            规则列表
        """
        return [
            # 规则1：应收账款风险
            {
                'id': 'receivable_high',
                'name': '应收账款占营收过高',
                'check': lambda ratios: ratios.get('receivable_ratio', 0) > 0.4,
                'level': RiskLevel.HIGH,
                'category': '财务造假风险',
                'query': '应收账款占营收40%以上有什么风险',
                'threshold': 0.4
            },
            # 规则2：现金流含金量低
            {
                'id': 'cash_quality_low',
                'name': '现金流含金量过低',
                'check': lambda ratios: ratios.get('cash_quality', 1) < 0.8,
                'level': RiskLevel.HIGH,
                'category': '财务造假风险',
                'query': '现金流含金量低于0.8意味着什么',
                'threshold': 0.8
            },
            # 规则3：资产负债率过高
            {
                'id': 'debt_ratio_high',
                'name': '资产负债率过高',
                'check': lambda ratios: ratios.get('debt_ratio', 0) > 0.7,
                'level': RiskLevel.HIGH,
                'category': '偿债风险',
                'query': '资产负债率超过70%有什么风险',
                'threshold': 0.7
            },
            # 规则4：流动比率过低
            {
                'id': 'current_ratio_low',
                'name': '流动比率过低',
                'check': lambda ratios: ratios.get('current_ratio', 2) < 1,
                'level': RiskLevel.MEDIUM,
                'category': '偿债风险',
                'query': '流动比率低于1意味着什么',
                'threshold': 1.0
            },
            # 规则5：存货周转率过低
            {
                'id': 'inventory_turnover_low',
                'name': '存货周转率过低',
                'check': lambda ratios: ratios.get('inventory_turnover', 10) < 2,
                'level': RiskLevel.MEDIUM,
                'category': '运营风险',
                'query': '存货周转率低有什么问题',
                'threshold': 2.0
            }
        ]

    def analyze_risks(
        self,
        indicators: Dict[str, Any],
        ratios: Dict[str, Any],
        company_name: str = '目标公司'
    ) -> List[Dict[str, Any]]:
        """
        分析财务风险

        Args:
            indicators: 财务指标
            ratios: 财务比率
            company_name: 公司名称

        Returns:
            风险列表
        """
        risks = []

        logger.info(f'开始分析 {company_name} 的财务风险')

        for rule in self.risk_rules:
            try:
                # 检查是否触发规则
                if rule['check'](ratios):
                    # 从知识库查询相关知识
                    knowledge = self._get_knowledge(rule['query'])

                    # 构建风险详情
                    risk = {
                        'id': rule['id'],
                        'name': rule['name'],
                        'level': rule['level'],
                        'category': rule['category'],
                        'value': self._get_actual_value(ratios, rule),
                        'threshold': rule['threshold'],
                        'explanation': self._format_explanation(knowledge, rule),
                        'cases': self._extract_cases(knowledge),
                        'suggestions': self._generate_suggestions(rule)
                    }

                    risks.append(risk)
                    logger.info(f'检测到风险: {risk["name"]} ({risk["level"]})')

            except Exception as e:
                logger.error(f'规则 {rule["id"]} 检查失败: {str(e)}')

        # 按风险等级排序
        risk_order = {RiskLevel.HIGH: 0, RiskLevel.MEDIUM: 1, RiskLevel.LOW: 2}
        risks.sort(key=lambda x: risk_order.get(x['level'], 3))

        logger.info(f'风险分析完成，发现 {len(risks)} 个风险点')

        return risks

    def _get_knowledge(self, query: str) -> str:
        """从RAG知识库获取相关知识"""
        try:
            result = self.rag.search(query, n_results=2)
            if result['success'] and result['results']:
                return result['results'][0]['text']
            return ''
        except Exception as e:
            logger.error(f'知识库查询失败: {str(e)}')
            return ''

    def _get_actual_value(self, ratios: Dict[str, Any], rule: Dict[str, Any]) -> float:
        """获取实际指标值"""
        # 根据规则ID确定对应的比率
        mapping = {
            'receivable_high': 'receivable_ratio',
            'cash_quality_low': 'cash_quality',
            'debt_ratio_high': 'debt_ratio',
            'current_ratio_low': 'current_ratio',
            'inventory_turnover_low': 'inventory_turnover'
        }
        key = mapping.get(rule['id'])
        return ratios.get(key, 0) if key else 0

    def _format_explanation(self, knowledge: str, rule: Dict[str, Any]) -> str:
        """格式化风险说明"""
        if knowledge:
            # 提取知识库中的关键信息（前200字）
            return knowledge[:200] + '...' if len(knowledge) > 200 else knowledge
        else:
            # 默认说明
            return f"{rule['name']}可能表明财务状况存在问题，需要进一步关注。"

    def _extract_cases(self, knowledge: str) -> List[str]:
        """从知识中提取案例"""
        cases = []
        # 简单的案例提取（基于关键词）
        case_keywords = ['万福生科', '康美药业', '保千里', '康得新', '獐子岛', '乐视网', '暴风集团']

        for keyword in case_keywords:
            if keyword in knowledge:
                cases.append(keyword)

        return cases[:3]  # 最多3个案例

    def _generate_suggestions(self, rule: Dict[str, Any]) -> List[str]:
        """生成风险应对建议"""
        suggestions_map = {
            'receivable_high': [
                '检查应收账款的账龄结构',
                '关注主要客户的回款情况',
                '警惕通过虚增收入粉饰业绩'
            ],
            'cash_quality_low': [
                '对比营业收入与经营现金流的匹配度',
                '检查是否存在赊销比例过高',
                '关注应收账款和存货的变化'
            ],
            'debt_ratio_high': [
                '评估公司的偿债能力',
                '关注利息保障倍数',
                '警惕债务违约风险'
            ],
            'current_ratio_low': [
                '检查短期偿债能力',
                '关注货币资金是否充足',
                '评估是否存在流动性危机'
            ],
            'inventory_turnover_low': [
                '检查存货结构和库龄',
                '关注是否存在积压或滞销',
                '评估存货减值风险'
            ]
        }

        return suggestions_map.get(rule['id'], ['需要进一步分析'])

    def generate_risk_report(
        self,
        risks: List[Dict[str, Any]],
        company_name: str = '目标公司'
    ) -> Dict[str, Any]:
        """
        生成风险分析报告

        Args:
            risks: 风险列表
            company_name: 公司名称

        Returns:
            报告内容
        """
        # 统计风险等级
        high_risks = [r for r in risks if r['level'] == RiskLevel.HIGH]
        medium_risks = [r for r in risks if r['level'] == RiskLevel.MEDIUM]
        low_risks = [r for r in risks if r['level'] == RiskLevel.LOW]

        # 计算综合评分（满分100）
        score = 100
        score -= len(high_risks) * 20  # 每个高风险-20分
        score -= len(medium_risks) * 10  # 每个中风险-10分
        score -= len(low_risks) * 5  # 每个低风险-5分
        score = max(0, score)

        # 生成投资建议
        if score >= 80:
            recommendation = '财务状况良好，风险可控'
            action = '可以关注'
        elif score >= 60:
            recommendation = '财务状况一般，存在一定风险'
            action = '谨慎关注'
        elif score >= 40:
            recommendation = '财务风险较高，需要警惕'
            action = '建议回避'
        else:
            recommendation = '财务风险严重，强烈建议回避'
            action = '强烈回避'

        report = {
            'company_name': company_name,
            'risk_summary': {
                'total': len(risks),
                'high': len(high_risks),
                'medium': len(medium_risks),
                'low': len(low_risks)
            },
            'score': score,
            'recommendation': recommendation,
            'action': action,
            'risks': risks
        }

        return report


# 测试函数
def test_risk_analyzer():
    """测试风险分析引擎"""
    print('=' * 70)
    print('风险分析引擎测试')
    print('=' * 70)

    analyzer = RiskAnalyzer()

    # 模拟财务数据（问题公司）
    test_ratios = {
        'receivable_ratio': 0.5,  # 应收账款/营收 = 50%（高）
        'cash_quality': 0.6,  # 现金流含金量 = 0.6（低）
        'debt_ratio': 0.75,  # 资产负债率 = 75%（高）
        'current_ratio': 0.8,  # 流动比率 = 0.8（低）
        'inventory_turnover': 1.5  # 存货周转率 = 1.5（低）
    }

    test_indicators = {
        'revenue': 1000000000,
        'net_profit': 50000000
    }

    print('\n[测试] 分析财务风险...')
    risks = analyzer.analyze_risks(test_indicators, test_ratios, '测试公司')

    print(f'  检测到 {len(risks)} 个风险点\n')

    for i, risk in enumerate(risks, 1):
        print(f'  [{i}] {risk["name"]} - {risk["level"].upper()}')
        print(f'      实际值: {risk["value"]:.2f}, 阈值: {risk["threshold"]:.2f}')
        if risk.get('cases'):
            print(f'      历史案例: {", ".join(risk["cases"])}')

    print('\n[测试] 生成风险报告...')
    report = analyzer.generate_risk_report(risks, '测试公司')

    print(f'  综合评分: {report["score"]} 分')
    print(f'  投资建议: {report["recommendation"]}')
    print(f'  操作建议: {report["action"]}')
    print(f'  高风险: {report["risk_summary"]["high"]} 个')
    print(f'  中风险: {report["risk_summary"]["medium"]} 个')

    print('\n' + '=' * 70)
    print('[完成] 风险分析引擎测试完成')
    print('=' * 70)


if __name__ == '__main__':
    test_risk_analyzer()
