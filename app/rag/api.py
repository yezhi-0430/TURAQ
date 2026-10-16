"""
RAG 系统 API 接口

提供文档管理、知识检索等 HTTP 接口
"""

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import os
import tempfile

from .core import get_rag_system
from .crawler import get_crawler


router = APIRouter(prefix="/api/rag", tags=["RAG"])


# ==================== 请求/响应模型 ====================

class QueryRequest(BaseModel):
    """查询请求"""
    query: str
    n_results: int = 3
    filter_metadata: Optional[Dict[str, Any]] = None


class AddTextRequest(BaseModel):
    """添加文本请求"""
    text: str
    metadata: Optional[Dict[str, Any]] = None
    doc_id: Optional[str] = None


class DeleteRequest(BaseModel):
    """删除文档请求"""
    doc_id: str


# ==================== API 端点 ====================

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    category: Optional[str] = Form(None),
    source: Optional[str] = Form(None),
    stock_code: Optional[str] = Form(None),
):
    """
    上传文档到知识库

    支持格式：PDF, TXT, DOCX, MD
    """
    try:
        # 检查文件类型
        allowed_extensions = ['.pdf', '.txt', '.docx', '.doc', '.md']
        file_ext = os.path.splitext(file.filename)[1].lower()

        if file_ext not in allowed_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的文件格式: {file_ext}。支持的格式: {', '.join(allowed_extensions)}"
            )

        # 保存临时文件
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp_file:
            content = await file.read()
            tmp_file.write(content)
            tmp_path = tmp_file.name

        try:
            # 准备元数据
            metadata = {
                'filename': file.filename,
            }
            if category:
                metadata['category'] = category
            if source:
                metadata['source'] = source
            if stock_code:
                metadata['stock_code'] = stock_code

            # 添加到知识库
            rag = get_rag_system()
            result = rag.add_document(tmp_path, metadata=metadata)

            return result

        finally:
            # 清理临时文件
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/add-text")
async def add_text(request: AddTextRequest):
    """
    直接添加文本到知识库
    """
    try:
        rag = get_rag_system()
        result = rag.add_text(
            text=request.text,
            metadata=request.metadata,
            doc_id=request.doc_id
        )
        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search")
async def search(request: QueryRequest):
    """
    语义搜索知识库
    """
    try:
        rag = get_rag_system()
        result = rag.search(
            query=request.query,
            n_results=request.n_results,
            filter_metadata=request.filter_metadata
        )
        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/document")
async def delete_document(request: DeleteRequest):
    """
    删除文档
    """
    try:
        rag = get_rag_system()
        result = rag.delete_document(request.doc_id)
        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_stats():
    """
    获取知识库统计信息
    """
    try:
        rag = get_rag_system()
        result = rag.get_stats()
        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/test")
async def test():
    """
    测试 RAG 系统是否正常
    """
    try:
        rag = get_rag_system()
        return {
            "success": True,
            "message": "RAG 系统运行正常",
            "total_documents": rag.collection.count()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/enhance-query")
async def enhance_query(request: QueryRequest):
    """
    为 AI 助手增强查询（返回相关知识）
    用于 AI 研究助手调用
    """
    try:
        rag = get_rag_system()
        result = rag.search(
            query=request.query,
            n_results=request.n_results,
            filter_metadata=request.filter_metadata
        )

        if not result['success']:
            return result

        # 格式化为 AI 可用的上下文
        context = []
        for item in result['results']:
            similarity = 1 - item['distance']
            if similarity >= 0.5:  # 只返回相似度 >= 50% 的结果
                context.append({
                    'text': item['text'],
                    'similarity': similarity,
                    'source': item['metadata'].get('filename', '知识库'),
                    'stock_code': item['metadata'].get('stock_code', ''),
                })

        return {
            'success': True,
            'query': request.query,
            'context': context,
            'has_context': len(context) > 0
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

