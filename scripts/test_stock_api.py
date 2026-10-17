"""
测试股票列表API
"""
import asyncio

import httpx


async def test_stock_list_api():
    """测试股票列表相关API"""
    base_url = "http://localhost:8888"

    async with httpx.AsyncClient() as client:
        print("=" * 60)
        print("测试股票列表API")
        print("=" * 60)

        # 1. 测试统计信息
        print("\n1. 测试 /api/v1/stocks/stats")
        try:
            response = await client.get(f"{base_url}/api/v1/stocks/stats")
            print(f"   状态码: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"   总股票数: {data['total']}")
                print(f"   市场分布: {data['by_market']}")
                print(f"   最后更新: {data['last_updated']}")
        except Exception as e:
            print(f"   错误: {e}")

        # 2. 测试搜索 - 按代码
        print("\n2. 测试搜索 - 按代码 (600519)")
        try:
            response = await client.get(f"{base_url}/api/v1/stocks/search?q=600519")
            print(f"   状态码: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"   查询关键词: {data['query']}")
                print(f"   结果数: {data['total']}")
                if data['results']:
                    for stock in data['results'][:3]:
                        print(f"   - {stock['symbol']} {stock['name']}")
        except Exception as e:
            print(f"   错误: {e}")

        # 3. 测试搜索 - 按名称
        print("\n3. 测试搜索 - 按名称 (茅台)")
        try:
            response = await client.get(f"{base_url}/api/v1/stocks/search?q=茅台")
            print(f"   状态码: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"   查询关键词: {data['query']}")
                print(f"   结果数: {data['total']}")
                if data['results']:
                    for stock in data['results']:
                        print(f"   - {stock['symbol']} {stock['name']}")
        except Exception as e:
            print(f"   错误: {e}")

        # 4. 测试搜索 - 部分代码
        print("\n4. 测试搜索 - 部分代码 (6005)")
        try:
            response = await client.get(f"{base_url}/api/v1/stocks/search?q=6005")
            print(f"   状态码: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"   查询关键词: {data['query']}")
                print(f"   结果数: {data['total']}")
                if data['results']:
                    for stock in data['results'][:5]:
                        print(f"   - {stock['symbol']} {stock['name']}")
        except Exception as e:
            print(f"   错误: {e}")

        # 5. 测试市场过滤
        print("\n5. 测试市场过滤 - 深市 (000)")
        try:
            response = await client.get(f"{base_url}/api/v1/stocks/search?q=000&market=sz&limit=5")
            print(f"   状态码: {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"   查询关键词: {data['query']}")
                print(f"   结果数: {data['total']}")
                if data['results']:
                    for stock in data['results']:
                        print(f"   - {stock['symbol']} {stock['name']} [{stock['market']}]")
        except Exception as e:
            print(f"   错误: {e}")

        # 6. 测试获取单个股票
        print("\n6. 测试获取单个股票 (000001.SZ)")
        try:
            response = await client.get(f"{base_url}/api/v1/stocks/000001.SZ")
            print(f"   状态码: {response.status_code}")
            if response.status_code == 200:
                stock = response.json()
                print(f"   代码: {stock['symbol']}")
                print(f"   名称: {stock['name']}")
                print(f"   市场: {stock['market']}")
        except Exception as e:
            print(f"   错误: {e}")

        # 7. 测试不存在的股票
        print("\n7. 测试不存在的股票 (999999.SH)")
        try:
            response = await client.get(f"{base_url}/api/v1/stocks/999999.SH")
            print(f"   状态码: {response.status_code}")
            if response.status_code == 404:
                print(f"   正确返回404: {response.json()}")
        except Exception as e:
            print(f"   错误: {e}")

        print("\n" + "=" * 60)
        print("测试完成")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_stock_list_api())
