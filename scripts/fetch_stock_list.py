"""
从东方财富API获取全量A股列表并保存为JSON
运行: python scripts/fetch_stock_list.py
"""
import json
from datetime import datetime
from pathlib import Path

import httpx


def fetch_stock_list():
    """从东方财富API获取股票列表（分页方式）"""
    all_stocks = []
    page_size = 1000

    # 分别获取不同市场的股票
    markets = [
        ("m:0+t:6,m:0+t:80", "深市A股+创业板"),
        ("m:1+t:2,m:1+t:23", "沪市A股+科创板"),
    ]

    for market_filter, market_name in markets:
        print(f"正在获取 {market_name}...")
        page = 1

        while True:
            url = "http://80.push2.eastmoney.com/api/qt/clist/get"
            params = {
                "pn": page,
                "pz": page_size,
                "po": 1,
                "np": 1,
                "fltt": 2,
                "invt": 2,
                "fid": "f3",
                "fs": market_filter,
                "fields": "f12,f13,f14",  # f12=代码, f13=市场, f14=名称
            }

            try:
                response = httpx.get(url, params=params, timeout=30)
                response.raise_for_status()

                data = response.json()
                if data.get("rc") != 0 or not data.get("data"):
                    break

                stocks_data = data["data"].get("diff", [])
                if not stocks_data:
                    break

                all_stocks.extend(stocks_data)
                print(f"  第{page}页: {len(stocks_data)} 只股票")

                # 如果这页数据少于page_size，说明是最后一页
                if len(stocks_data) < page_size:
                    break

                page += 1

            except Exception as e:
                print(f"  警告: 获取第{page}页失败: {e}")
                break

    print(f"总共获取到 {len(all_stocks)} 只股票")
    return all_stocks


def normalize_stock(item):
    """标准化股票数据格式"""
    code_num = item["f12"]  # 如: 000001
    market_code = item["f13"]  # 0=深圳, 1=上海, 2=北交所
    name = item["f14"]

    # 转换市场代码
    if market_code == 0:
        market = "sz"
    elif market_code == 1:
        market = "sh"
    elif market_code == 2:
        market = "bj"
    else:
        market = "unknown"

    # 生成标准格式
    code = f"{market}{code_num}"  # sz000001
    symbol = f"{code_num}.{market.upper()}"  # 000001.SZ

    return {
        "symbol": symbol,
        "code": code,
        "name": name,
        "market": market,
    }


def save_stock_list(stocks, output_path):
    """保存股票列表到JSON文件"""
    output = {
        "version": datetime.now().strftime("%Y-%m-%d"),
        "source": "东方财富",
        "total": len(stocks),
        "updated_at": datetime.now().isoformat(),
        "stocks": stocks,
    }

    # 确保目录存在
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"[OK] 股票列表已保存到: {output_path}")
    print(f"   总数: {len(stocks)} 只")

    # 统计各市场数量
    by_market = {}
    for stock in stocks:
        market = stock["market"]
        by_market[market] = by_market.get(market, 0) + 1

    print("   市场分布:")
    for market, count in sorted(by_market.items()):
        print(f"     {market.upper()}: {count} 只")


def main():
    try:
        # 获取数据
        raw_data = fetch_stock_list()

        # 标准化格式
        stocks = [normalize_stock(item) for item in raw_data]

        # 按代码排序
        stocks.sort(key=lambda x: x["code"])

        # 保存文件
        output_path = Path("data/stocks_base.json")
        save_stock_list(stocks, output_path)

        print("\n[SUCCESS] 股票列表获取成功！")

    except Exception as e:
        print(f"[ERROR] 错误: {e}")
        raise


if __name__ == "__main__":
    main()
