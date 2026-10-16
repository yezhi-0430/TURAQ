"""
将知识文档批量导入到 RAG 数据库
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.rag.core import get_rag_system


def import_knowledge_to_rag():
    """将 knowledge 目录下的所有文档导入 RAG"""

    print("=" * 60)
    print("开始导入知识文档到 RAG 数据库")
    print("=" * 60)

    rag = get_rag_system()

    # 知识文档目录
    knowledge_dir = Path("knowledge")

    if not knowledge_dir.exists():
        print(f"错误: {knowledge_dir} 目录不存在")
        return

    # 获取所有 .md 文件
    md_files = sorted(knowledge_dir.glob("*.md"))

    if not md_files:
        print(f"错误: {knowledge_dir} 目录下没有 .md 文件")
        return

    print(f"\n找到 {len(md_files)} 个知识文档\n")

    total_chunks = 0

    for i, md_file in enumerate(md_files, 1):
        try:
            print(f"[{i}/{len(md_files)}] 正在导入: {md_file.name}")

            # 读取文件内容
            with open(md_file, 'r', encoding='utf-8') as f:
                content = f.read()

            # 提取文档标题（第一行）
            title = content.split('\n')[0].replace('#', '').strip()

            # 确定分类
            category = 'investment_knowledge'
            if '财务指标' in title:
                category = 'financial_indicators'
            elif '交易规则' in title:
                category = 'trading_rules'
            elif '风险管理' in title:
                category = 'risk_management'
            elif '行业分析' in title:
                category = 'industry_analysis'
            elif '技术分析' in title:
                category = 'technical_analysis'
            elif '价值投资' in title:
                category = 'value_investing'

            # 添加到 RAG
            result = rag.add_text(
                text=content,
                metadata={
                    'filename': md_file.name,
                    'title': title,
                    'category': category,
                    'source': 'knowledge_base',
                    'type': 'tutorial'
                }
            )

            if result['success']:
                chunks = result['chunks']
                total_chunks += chunks
                print(f"  [OK] 成功导入 {chunks} 个文档块")
            else:
                print(f"  [ERROR] 导入失败: {result['message']}")

        except Exception as e:
            print(f"  ✗ 处理失败: {str(e)}")
            continue

    print("\n" + "=" * 60)
    print(f"导入完成！共添加 {total_chunks} 个文档块到知识库")
    print("=" * 60)

    # 显示统计信息
    stats = rag.get_stats()
    if stats['success']:
        print(f"\n当前知识库统计:")
        print(f"  - 总文档数: {stats['total_documents']}")
        print(f"  - 总文档块: {stats['total_chunks']}")
        print(f"\n分类统计:")
        for category, count in stats['categories'].items():
            print(f"  - {category}: {count} 块")


if __name__ == "__main__":
    import_knowledge_to_rag()
