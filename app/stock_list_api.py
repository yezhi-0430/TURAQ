"""
股票列表 API 端点
"""
from fastapi import APIRouter, Depends, HTTPException, Query

from app.model_limits import catalog_admission
from app.stock_list import stock_list_service

router = APIRouter(prefix="/api/v1/stocks", tags=["stocks"],
                   dependencies=[Depends(catalog_admission)])


@router.get("/search")
async def search_stocks(
    q: str = Query(..., min_length=1, max_length=20, description="搜索关键词（代码或名称）"),
    market: str | None = Query(None, pattern="^(sh|sz|bj|all)$", description="市场过滤"),
    limit: int = Query(50, ge=1, le=100, description="返回结果数量"),
):
    """
    搜索股票 - 无需登录

    数据库共享 IP 限流在 catalog_admission 中执行。

    支持：
    - 股票代码搜索（完整或部分）：600519, 6005
    - 股票名称搜索：茅台, 银行
    - 市场过滤：sh(上海), sz(深圳), bj(北京)
    """
    # market=all 等同于不过滤
    market_filter = None if market == "all" else market

    results = stock_list_service.search(q, market_filter, limit)

    return {
        "query": q,
        "results": results,
        "total": len(results),
        "truncated": len(results) >= limit,
    }


@router.get("/stats")
async def get_stats():
    """
    获取股票列表统计信息 - 无需登录

    返回：
    - 总股票数
    - 各市场股票数
    - 最后更新时间
    """
    return stock_list_service.get_stats()


@router.get("/{symbol}")
async def get_stock(symbol: str):
    """
    获取单个股票信息 - 无需登录

    参数：
    - symbol: 股票代码，如 000001.SZ 或 600519.SH
    """
    stock = stock_list_service.get_by_symbol(symbol.strip().upper())
    if not stock:
        raise HTTPException(status_code=404, detail="股票不存在")

    return stock
