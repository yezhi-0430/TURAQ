"""
RAG 系统核心

整合嵌入、存储、检索功能
"""

import os
import chromadb
from typing import List, Dict, Optional, Any
from datetime import datetime
import hashlib

from .embeddings import get_embedding_service
from .parsers import DocumentParser
from .chunker import TextChunker
from .scoring import cosine_similarity


class RAGSystem:
    """RAG 知识库系统"""

    def __init__(self, persist_directory: str = "./chroma_db", collection_name: str = "knowledge"):
        """
        初始化 RAG 系统

        Args:
            persist_directory: 数据库存储目录
            collection_name: 集合名称
        """
        print(f"正在初始化 RAG 系统...")
        print(f"数据库目录: {persist_directory}")

        # 创建目录
        os.makedirs(persist_directory, exist_ok=True)

        # 初始化 Chroma 客户端
        self.client = chromadb.PersistentClient(path=persist_directory)

        # 获取或创建集合
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"description": "A股智能研究知识库"}
        )

        # 初始化服务
        self.embedding_service = get_embedding_service()
        self.parser = DocumentParser()
        self.chunker = TextChunker(chunk_size=500, overlap=50)

        print(f"RAG 系统初始化完成")
        print(f"当前知识库文档数: {self.collection.count()}")

    def add_document(
        self,
        file_path: str,
        metadata: Optional[Dict[str, Any]] = None,
        chunk_strategy: str = 'smart'
    ) -> Dict[str, Any]:
        """
        添加文档到知识库

        Args:
            file_path: 文件路径
            metadata: 文档元数据（可选）
            chunk_strategy: 分段策略

        Returns:
            添加结果
        """
        try:
            print(f"正在处理文档: {file_path}")

            # 1. 解析文档
            text = self.parser.parse(file_path)
            print(f"  - 文档解析完成，共 {len(text)} 字符")

            # 2. 文本分段
            chunk_rows = self.chunker.chunk_with_metadata(text, strategy=chunk_strategy)
            chunks = [row['text'] for row in chunk_rows]
            print(f"  - 文本分段完成，共 {len(chunks)} 个块")

            # 3. 生成向量
            embeddings = self.embedding_service.embed_documents(chunks)
            print(f"  - 向量生成完成")

            # 4. 准备元数据
            file_info = self.parser.get_file_info(file_path)
            doc_id = self._generate_doc_id(file_path)

            metadatas = []
            ids = []
            for i in range(len(chunks)):
                chunk_metadata = {
                    'doc_id': doc_id,
                    'filename': file_info['filename'],
                    'file_path': file_path,
                    'chunk_index': i,
                    'total_chunks': len(chunks),
                    'added_at': datetime.now().isoformat(),
                }

                # 合并用户提供的元数据
                if metadata:
                    chunk_metadata.update(metadata)

                chunk_metadata.update({key: value for key, value in chunk_rows[i].items()
                                       if key not in {'text', 'source'}})

                metadatas.append(chunk_metadata)
                ids.append(f"{doc_id}_chunk_{i}")

            # 5. 添加到 Chroma
            self.collection.add(
                documents=chunks,
                embeddings=embeddings,
                metadatas=metadatas,
                ids=ids
            )

            print(f"✓ 文档添加成功")

            return {
                'success': True,
                'doc_id': doc_id,
                'filename': file_info['filename'],
                'chunks': len(chunks),
                'message': f"成功添加 {len(chunks)} 个文档块"
            }

        except Exception as e:
            print(f"✗ 文档添加失败: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'message': f"文档添加失败: {str(e)}"
            }

    def add_text(
        self,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
        doc_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        直接添加文本到知识库

        Args:
            text: 文本内容
            metadata: 元数据
            doc_id: 文档ID（可选，自动生成）

        Returns:
            添加结果
        """
        try:
            # 生成文档ID
            if doc_id is None:
                doc_id = self._generate_doc_id(text[:100])

            # 分段
            chunk_rows = self.chunker.chunk_with_metadata(text, strategy='smart')
            chunks = [row['text'] for row in chunk_rows]

            # 生成向量
            embeddings = self.embedding_service.embed_documents(chunks)

            # 准备元数据
            metadatas = []
            ids = []
            for i in range(len(chunks)):
                chunk_metadata = {
                    'doc_id': doc_id,
                    'chunk_index': i,
                    'total_chunks': len(chunks),
                    'added_at': datetime.now().isoformat(),
                    'source': 'text'
                }

                if metadata:
                    chunk_metadata.update(metadata)

                chunk_metadata.update({key: value for key, value in chunk_rows[i].items()
                                       if key not in {'text', 'source'}})

                metadatas.append(chunk_metadata)
                ids.append(f"{doc_id}_chunk_{i}")

            # 添加到数据库
            self.collection.add(
                documents=chunks,
                embeddings=embeddings,
                metadatas=metadatas,
                ids=ids
            )

            return {
                'success': True,
                'doc_id': doc_id,
                'chunks': len(chunks),
                'message': f"成功添加 {len(chunks)} 个文档块"
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': f"文本添加失败: {str(e)}"
            }

    def search(
        self,
        query: str,
        n_results: int = 3,
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        语义搜索

        Args:
            query: 查询文本
            n_results: 返回结果数量
            filter_metadata: 元数据过滤条件

        Returns:
            搜索结果
        """
        try:
            # 生成查询向量
            query_embedding = self.embedding_service.embed_query(query)

            # 搜索
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                where=filter_metadata,
                include=['documents', 'metadatas', 'distances', 'embeddings'],
            )

            # 格式化结果
            formatted_results = []
            if results['documents'] and results['documents'][0]:
                for i in range(len(results['documents'][0])):
                    vectors = results.get('embeddings')
                    vector = (vectors[0][i] if vectors is not None and len(vectors)
                              and vectors[0] is not None and i < len(vectors[0]) else None)
                    formatted_results.append({
                        'text': results['documents'][0][i],
                        'metadata': results['metadatas'][0][i] if results['metadatas'] else {},
                        'distance': results['distances'][0][i] if results['distances'] else None,
                        'similarity': cosine_similarity(query_embedding, vector),
                        'similarity_metric': 'cosine',
                    })

            return {
                'success': True,
                'query': query,
                'results': formatted_results,
                'total': len(formatted_results)
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': f"搜索失败: {str(e)}"
            }

    def delete_document(self, doc_id: str) -> Dict[str, Any]:
        """
        删除文档

        Args:
            doc_id: 文档ID

        Returns:
            删除结果
        """
        try:
            # 查找该文档的所有块
            results = self.collection.get(
                where={'doc_id': doc_id}
            )

            if not results['ids']:
                return {
                    'success': False,
                    'message': f"未找到文档: {doc_id}"
                }

            # 删除所有块
            self.collection.delete(ids=results['ids'])

            return {
                'success': True,
                'doc_id': doc_id,
                'deleted_chunks': len(results['ids']),
                'message': f"成功删除 {len(results['ids'])} 个文档块"
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': f"删除失败: {str(e)}"
            }

    def get_stats(self) -> Dict[str, Any]:
        """
        获取知识库统计信息

        Returns:
            统计信息
        """
        try:
            total_count = self.collection.count()

            # 获取所有文档
            all_docs = self.collection.get()

            # 统计不同类型的文档
            doc_ids = set()
            categories = {}

            if all_docs['metadatas']:
                for meta in all_docs['metadatas']:
                    doc_ids.add(meta.get('doc_id', ''))

                    category = meta.get('category', 'unknown')
                    categories[category] = categories.get(category, 0) + 1

            return {
                'success': True,
                'total_chunks': total_count,
                'total_documents': len(doc_ids),
                'categories': categories,
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }

    def _generate_doc_id(self, content: str) -> str:
        """
        生成文档ID

        Args:
            content: 文档内容或文件路径

        Returns:
            文档ID
        """
        hash_obj = hashlib.md5(content.encode('utf-8'))
        return hash_obj.hexdigest()[:16]


# 全局单例
_rag_system = None


def get_rag_system(persist_directory: str = "./chroma_db") -> RAGSystem:
    """
    获取 RAG 系统单例

    Args:
        persist_directory: 数据库存储目录

    Returns:
        RAG 系统实例
    """
    global _rag_system

    if _rag_system is None:
        _rag_system = RAGSystem(persist_directory=persist_directory)

    return _rag_system
