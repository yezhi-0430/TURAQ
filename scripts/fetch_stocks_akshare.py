"""
使用 akshare 获取完整A股列表

使用前需要安装: pip install akshare

运行: python scripts/fetch_stocks_akshare.py
"""
import json
from datetime import datetime
from pathlib import Path


def fetch_stocks_with_akshare():
    """使用akshare获取A股列表"""
    try:
        import akshare as ak
    except ImportError:
        print("错误: 未安装 akshare")
        print("请运行: pip install akshare")
        return None

    print("正在从akshare获取A股列表...")

    all_stocks = []

    # 获取沪深A股列表
    try:
        # 获取沪市A股
        print("正在获取沪市A股...")
        sh_stocks = ak.stock_info_sh_name_code(symbol="主板A股")
        for _, row in sh_stocks.iterrows():
            code = row['证券代码']
            name = row['证券简称']
            all_stocks.append({
                'symbol': f"{code}.SH",
                'code': f"sh{code}",
                'name': name,
                'market': 'sh'
            })
        print(f"  获取到 {len(sh_stocks)} 只沪市股票")
    except Exception as e:
        print(f"获取沪市股票失败: {e}")

    try:
        # 获取深市A股 - 修复参数
        print("正在获取深市A股...")
        sz_stocks = ak.stock_info_sz_name_code(symbol="A股列表")
        for _, row in sz_stocks.iterrows():
            # 深市的字段名可能是 'A股代码' 或 '证券代码'
            code = row.get('A股代码') or row.get('证券代码', '')
            name = row.get('A股简称') or row.get('证券简称', '')

            # 清理和验证
            code = str(code).strip()
            name = str(name).strip()

            # 跳过无效数据
            if not code or not name or code in ['nan', 'None', '']:
                continue

            # 确保是6位数字
            if code.isdigit() and len(code) <= 6:
                code = code.zfill(6)
                all_stocks.append({
                    'symbol': f"{code}.SZ",
                    'code': f"sz{code}",
                    'name': name,
                    'market': 'sz'
                })
        print(f"  获取到 {len([s for s in all_stocks if s['market'] == 'sz'])} 只深市股票")
    except Exception as e:
        print(f"获取深市股票失败: {e}")
        import traceback
        traceback.print_exc()

    try:
        # 获取北交所股票
        print("正在获取北交所股票...")
        bj_stocks = ak.stock_info_bj_name_code()
        for _, row in bj_stocks.iterrows():
            # 北交所字段可能是 'code' 或 '证券代码'
            code = row.get('code') or row.get('证券代码', '')
            name = row.get('name') or row.get('证券简称', '')

            # 清理
            code = str(code).strip()
            name = str(name).strip()

            if not code or not name or code in ['nan', 'None', '']:
                continue

            if code.isdigit() and len(code) <= 6:
                code = code.zfill(6)
                all_stocks.append({
                    'symbol': f"{code}.BJ",
                    'code': f"bj{code}",
                    'name': name,
                    'market': 'bj'
                })
        print(f"  获取到 {len([s for s in all_stocks if s['market'] == 'bj'])} 只北交所股票")
    except Exception as e:
        print(f"获取北交所股票失败: {e}")
        import traceback
        traceback.print_exc()

    print(f"\n总共获取到 {len(all_stocks)} 只股票")
    return all_stocks


def save_stock_list(stocks, output_path="data/stocks_base.json"):
    """保存股票列表到JSON文件"""
    if not stocks:
        print("没有股票数据可保存")
        return

    output = {
        "version": datetime.now().strftime("%Y-%m-%d"),
        "source": "akshare",
        "total": len(stocks),
        "updated_at": datetime.now().isoformat(),
        "stocks": stocks,
    }

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n[OK] 股票列表已保存到: {output_path}")
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
        stocks = fetch_stocks_with_akshare()

        if stocks:
            save_stock_list(stocks)
            print("\n[SUCCESS] 股票列表获取成功！")
        else:
            print("\n[ERROR] 未能获取股票数据")

    except Exception as e:
        print(f"\n[ERROR] 错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
