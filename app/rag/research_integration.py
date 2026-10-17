"""
RAG 增强的 AI 研究助手

在回答用户问题时自动检索知识库
"""

from typing import List, Dict, Any, Optional
from app.rag.core import get_rag_system


class RAGEnhancedResearch:
    """RAG 增强的研究助手"""

    def __init__(self):
        """初始化"""
        self.rag = None
        try:
            self.rag = get_rag_system()
            self.enabled = True
        except Exception as e:
            print(f"RAG 系统初始化失败: {str(e)}")
            self.enabled = False

    def search_knowledge(
        self,
        query: str,
        n_results: int = 3,
        min_similarity: float = 0.5
    ) -> List[Dict[str, Any]]:
        """
        搜索知识库

        Args:
            query: 查询文本
            n_results: 返回结果数量
            min_similarity: 最小相似度阈值

        Returns:
            相关文档列表
        """
        if not self.enabled:
            return []

        try:
            result = self.rag.search(query, n_results=n_results)

            if not result['success']:
                return []

            # 过滤低相似度结果
            filtered_results = []
            for item in result['results']:
                similarity = 1 - item['distance']
                if similarity >= min_similarity:
                    filtered_results.append({
                        'text': item['text'],
                        'similarity': similarity,
                        'metadata': item['metadata']
                    })

            return filtered_results

        except Exception as e:
            print(f"知识检索失败: {str(e)}")
            return []

    def enhance_prompt(
        self,
        user_query: str,
        context_results: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """
        使用检索到的知识增强提示词

        Args:
            user_query: 用户问题
            context_results: 检索到的上下文（可选，不传则自动检索）

        Returns:
            增强后的提示词
        """
        # 如果没有传入上下文，自动检索
        if context_results is None:
            context_results = self.search_knowledge(user_query, n_results=3)

        # 如果没有找到相关知识，返回原始问题
        if not context_results:
            return user_query

        # 构建增强提示词
        context_text = "\n\n".join([
            f"[参考资料 {i+1}] (相似度: {item['similarity']:.1%})\n{item['text']}"
            for i, item in enumerate(context_results)
        ])

        enhanced_prompt = f"""请基于以下参考资料回答用户问题。如果参考资料中没有相关信息，请基于你的知识回答，并说明这不是来自参考资料。

参考资料：
{context_text}

用户问题：
{user_query}

请提供详细且准确的回答。"""

        return enhanced_prompt

    def format_sources(self, context_results: List[Dict[str, Any]]) -> str:
        """
        格式化来源信息

        Args:
            context_results: 检索结果

        Returns:
            格式化的来源信息
        """
        if not context_results:
            return ""

        sources = []
        for i, item in enumerate(context_results, 1):
            meta = item['metadata']
            source_info = []

            if meta.get('filename'):
                source_info.append(f"文件: {meta['filename']}")
            if meta.get('stock_code'):
                source_info.append(f"股票: {meta['stock_code']}")
            if meta.get('category'):
                source_info.append(f"类型: {meta['category']}")

            source_str = f"[{i}] " + " | ".join(source_info) if source_info else f"[{i}] 知识库"
            sources.append(source_str)

        return "\n".join(sources)


# 全局单例
_rag_research = None


def get_rag_research() -> RAGEnhancedResearch:
    """获取 RAG 研究助手单例"""
    global _rag_research

    if _rag_research is None:
        _rag_research = RAGEnhancedResearch()

    return _rag_research
