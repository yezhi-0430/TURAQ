"""
嵌入模型服务

负责将文本转换为向量表示
"""

from sentence_transformers import SentenceTransformer
from typing import List, Union
import numpy as np


class EmbeddingService:
    """文本嵌入服务"""

    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5"):
        """
        初始化嵌入模型

        Args:
            model_name: 模型名称，默认使用 BGE 中文小模型
                       - BAAI/bge-small-zh-v1.5: 轻量级，速度快（推荐）
                       - BAAI/bge-large-zh-v1.5: 大模型，准确度高
                       - moka-ai/m3e-base: 中文优化
        """
        print(f"正在加载嵌入模型: {model_name}...")
        self.model = SentenceTransformer(model_name)
        print("嵌入模型加载完成")

    def embed(self, texts: Union[str, List[str]]) -> np.ndarray:
        """
        将文本转换为向量

        Args:
            texts: 单个文本或文本列表

        Returns:
            向量数组
        """
        if isinstance(texts, str):
            texts = [texts]

        embeddings = self.model.encode(texts, show_progress_bar=False)
        return embeddings

    def embed_query(self, query: str) -> List[float]:
        """
        为查询文本生成向量（返回列表格式）

        Args:
            query: 查询文本

        Returns:
            向量列表
        """
        embedding = self.embed(query)[0]
        return embedding.tolist()

    def embed_documents(self, documents: List[str]) -> List[List[float]]:
        """
        为文档列表生成向量（返回列表格式）

        Args:
            documents: 文档列表

        Returns:
            向量列表的列表
        """
        embeddings = self.embed(documents)
        return embeddings.tolist()


# 全局单例
_embedding_service = None


def get_embedding_service(model_name: str = "BAAI/bge-small-zh-v1.5") -> EmbeddingService:
    """
    获取嵌入服务单例

    Args:
        model_name: 模型名称

    Returns:
        嵌入服务实例
    """
    global _embedding_service

    if _embedding_service is None:
        _embedding_service = EmbeddingService(model_name)

    return _embedding_service
