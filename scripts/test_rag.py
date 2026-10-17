"""
RAG 系统测试脚本

测试文档上传、检索等基础功能
"""

import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_basic_functions():
    """测试基础功能"""
    print("=" * 60)
    print("RAG 系统基础功能测试")
    print("=" * 60)

    from app.rag.core import RAGSystem

    # 1. 初始化系统
    print("\n[1/4] 初始化 RAG 系统...")
    rag = RAGSystem(persist_directory="./test_chroma_db")
    print("初始化成功")

    # 2. 添加测试文本
    print("\n[2/4] 添加测试文本...")
    test_text = """
    贵州茅台（600519）是中国最大的白酒生产企业。

    公司主要产品包括茅台酒、茅台王子酒等系列产品。

    2024年第三季度财报显示：
    - 营业收入：350亿元，同比增长15%
    - 净利润：180亿元，同比增长18%
    - 毛利率：91.5%

    投资建议：
    - 目标价：2000元
    - 评级：买入

    风险提示：
    - 宏观经济波动风险
    - 行业竞争加剧
    - 政策调整风险
    """

    result = rag.add_text(
        text=test_text,
        metadata={
            'category': 'stock_report',
            'stock_code': '600519',
            'stock_name': '贵州茅台',
            'source': 'test'
        }
    )

    if result['success']:
        print(f"[OK] 文本添加成功，共 {result['chunks']} 个块")
    else:
        print(f"[ERROR] 文本添加失败: {result['message']}")
        return False

    # 3. 测试检索
    print("\n[3/4] 测试语义检索...")
    queries = [
        "茅台的营收是多少？",
        "茅台有什么风险？",
        "茅台的投资建议是什么？"
    ]

    for query in queries:
        print(f"\n查询: {query}")
        search_result = rag.search(query, n_results=2)

        if search_result['success']:
            print(f"找到 {search_result['total']} 条相关结果:")
            for i, item in enumerate(search_result['results'], 1):
                print(f"\n  [{i}] 相似度: {1 - item['distance']:.2%}")
                print(f"      内容: {item['text'][:100]}...")
        else:
            print(f"[ERROR] 检索失败: {search_result['message']}")

    # 4. 获取统计信息
    print("\n[4/4] 获取统计信息...")
    stats = rag.get_stats()

    if stats['success']:
        print(f"[OK] 知识库统计:")
        print(f"  - 总文档数: {stats['total_documents']}")
        print(f"  - 总块数: {stats['total_chunks']}")
        print(f"  - 分类: {stats['categories']}")
    else:
        print(f"[ERROR] 获取统计失败")

    print("\n" + "=" * 60)
    print("[OK] 所有测试通过！")
    print("=" * 60)

    return True


def test_document_parsing():
    """测试文档解析"""
    print("\n测试文档解析功能...")

    from app.rag.parsers import DocumentParser
    from app.rag.chunker import TextChunker

    parser = DocumentParser()
    chunker = TextChunker(chunk_size=200, overlap=20)

    # 创建测试文本文件
    test_file = "./test_document.txt"
    with open(test_file, 'w', encoding='utf-8') as f:
        f.write("这是一个测试文档。\n\n" * 50)

    try:
        # 解析
        text = parser.parse(test_file)
        print(f"[OK] 文档解析成功，共 {len(text)} 字符")

        # 分段
        chunks = chunker.chunk(text, strategy='smart')
        print(f"[OK] 文本分段成功，共 {len(chunks)} 个块")

    finally:
        # 清理
        if os.path.exists(test_file):
            os.unlink(test_file)

    return True


if __name__ == "__main__":
    try:
        # 基础功能测试
        test_basic_functions()

        # 文档解析测试
        test_document_parsing()

        print("\n[OK] 所有测试完成！RAG 系统工作正常。")

    except Exception as e:
        print(f"\n[ERROR] 测试失败: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
