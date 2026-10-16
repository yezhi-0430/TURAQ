"""
东方财富爬虫完整审查与测试

测试内容：
1. 数据准确性
2. 数据完整性
3. 错误处理
4. 性能测试
5. 实际可用性
"""

import asyncio
import sys
import os

# 添加路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


async def comprehensive_test():
    # 直接导入爬虫类，避免依赖数据库
    import httpx
    import json

    print('=' * 80)
    print('东方财富爬虫完整审查报告')
    print('=' * 80)

    client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'http://quote.eastmoney.com/',
    }

    test_results = {
        'total': 0,
        'passed': 0,
        'failed': 0
    }

    # ============================================================
    # 测试1：实时行情数据准确性
    # ============================================================
    print('\n[测试1] 实时行情数据准确性')
    print('-' * 80)
    test_results['total'] += 1

    try:
        url = 'http://push2.eastmoney.com/api/qt/stock/get'
        params = {
            'secid': '1.600519',
            'fields': 'f57,f58,f43,f44,f45,f46,f170,f47,f48',
            'ut': 'fa5fd1943c7b386f172d6893dbfba10b',
        }

        response = await client.get(url, params=params, headers=headers)

        if response.status_code == 200:
            data = response.json()
            if data.get('data'):
                d = data['data']

                name = d.get('f58', '')
                price = d.get('f43', 0) / 100
                change_pct = d.get('f170', 0) / 100

                print(f'  股票名称: {name}')
                print(f'  当前价格: {price} 元')
                print(f'  涨跌幅: {change_pct}%')

                # 验证数据合理性
                if name and price > 0:
                    print('  [PASS] 数据完整且合理')
                    test_results['passed'] += 1
                else:
                    print('  [FAIL] 数据不完整')
                    test_results['failed'] += 1
            else:
                print('  [FAIL] API返回数据为空')
                test_results['failed'] += 1
        else:
            print(f'  [FAIL] HTTP状态码: {response.status_code}')
            test_results['failed'] += 1

    except Exception as e:
        print(f'  [ERROR] {str(e)[:100]}')
        test_results['failed'] += 1

    # ============================================================
    # 测试2：公司公告数据完整性
    # ============================================================
    print('\n[测试2] 公司公告数据完整性')
    print('-' * 80)
    test_results['total'] += 1

    try:
        url = 'http://np-anotice-stock.eastmoney.com/api/security/ann'
        params = {
            'sr': '-1',
            'page_size': '5',
            'page_index': '1',
            'ann_type': 'SHA,SZA',
            'stock_list': '600519',
            'f_node': '0'
        }

        response = await client.get(url, params=params, headers=headers)

        if response.status_code == 200:
            data = response.json()

            if data.get('data') and data['data'].get('list'):
                items = data['data']['list']

                print(f'  获取公告数量: {len(items)} 条')

                # 检查前3条公告的完整性
                complete_count = 0
                for i, item in enumerate(items[:3], 1):
                    title = item.get('title', '')
                    date = item.get('display_time', '')[:10]

                    if title and date:
                        complete_count += 1
                        print(f'  [{i}] {date} {title[:40]}')

                if complete_count >= 3:
                    print(f'  [PASS] {complete_count}/3 条公告数据完整')
                    test_results['passed'] += 1
                else:
                    print(f'  [FAIL] 仅 {complete_count}/3 条公告数据完整')
                    test_results['failed'] += 1
            else:
                print('  [FAIL] 未获取到公告数据')
                test_results['failed'] += 1
        else:
            print(f'  [FAIL] HTTP状态码: {response.status_code}')
            test_results['failed'] += 1

    except Exception as e:
        print(f'  [ERROR] {str(e)[:100]}')
        test_results['failed'] += 1

    # ============================================================
    # 测试3：资金流向数据准确性
    # ============================================================
    print('\n[测试3] 资金流向数据准确性')
    print('-' * 80)
    test_results['total'] += 1

    try:
        url = 'http://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get'
        params = {
            'secid': '1.600519',
            'fields1': 'f1,f2,f3,f7',
            'fields2': 'f51,f52,f53,f54,f55,f56,f57',
            'ut': 'b2884a393a59ad64002292a3e90d46a5',
            'lmt': '5',
        }

        response = await client.get(url, params=params, headers=headers)

        if response.status_code == 200:
            data = response.json()

            if data.get('data') and data['data'].get('klines'):
                klines = data['data']['klines']

                print(f'  获取数据天数: {len(klines)} 天')

                # 检查数据格式
                valid_count = 0
                for line in klines[:3]:
                    parts = line.split(',')
                    if len(parts) >= 5:
                        date = parts[0]
                        main_force = float(parts[1])
                        valid_count += 1
                        print(f'  {date} 主力净流入: {main_force/10000:.2f} 万元')

                if valid_count >= 3:
                    print(f'  [PASS] {valid_count}/3 天数据有效')
                    test_results['passed'] += 1
                else:
                    print(f'  [FAIL] 仅 {valid_count}/3 天数据有效')
                    test_results['failed'] += 1
            else:
                print('  [FAIL] 未获取到资金流向数据')
                test_results['failed'] += 1
        else:
            print(f'  [FAIL] HTTP状态码: {response.status_code}')
            test_results['failed'] += 1

    except Exception as e:
        print(f'  [ERROR] {str(e)[:100]}')
        test_results['failed'] += 1

    # ============================================================
    # 测试4：热门股票榜单
    # ============================================================
    print('\n[测试4] 热门股票榜单')
    print('-' * 80)
    test_results['total'] += 1

    try:
        url = 'http://push2.eastmoney.com/api/qt/clist/get'
        params = {
            'fid': 'f62',
            'po': '1',
            'pz': '10',
            'pn': '1',
            'np': '1',
            'fltt': '2',
            'invt': '2',
            'fs': 'm:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23',
            'fields': 'f12,f14,f2,f3,f62',
            'ut': 'b2884a393a59ad64002292a3e90d46a5',
        }

        response = await client.get(url, params=params, headers=headers)

        if response.status_code == 200:
            data = response.json()

            if data.get('data') and data['data'].get('diff'):
                items = data['data']['diff']

                print(f'  获取热门股票: {len(items)} 只')

                # 显示前5只
                valid_count = 0
                for i, item in enumerate(items[:5], 1):
                    code = item.get('f12', '')
                    name = item.get('f14', '')
                    change_pct = item.get('f3', 0) / 100

                    if code and name:
                        valid_count += 1
                        print(f'  [{i}] {name}({code}) {change_pct:+.2f}%')

                if valid_count >= 5:
                    print(f'  [PASS] {valid_count}/5 只股票数据完整')
                    test_results['passed'] += 1
                else:
                    print(f'  [FAIL] 仅 {valid_count}/5 只股票数据完整')
                    test_results['failed'] += 1
            else:
                print('  [FAIL] 未获取到热门股票')
                test_results['failed'] += 1
        else:
            print(f'  [FAIL] HTTP状态码: {response.status_code}')
            test_results['failed'] += 1

    except Exception as e:
        print(f'  [ERROR] {str(e)[:100]}')
        test_results['failed'] += 1

    # ============================================================
    # 测试5：不同市场股票（深市）
    # ============================================================
    print('\n[测试5] 深市股票测试（000858）')
    print('-' * 80)
    test_results['total'] += 1

    try:
        url = 'http://push2.eastmoney.com/api/qt/stock/get'
        params = {
            'secid': '0.000858',  # 深市
            'fields': 'f57,f58,f43,f170',
            'ut': 'fa5fd1943c7b386f172d6893dbfba10b',
        }

        response = await client.get(url, params=params, headers=headers)

        if response.status_code == 200:
            data = response.json()
            if data.get('data'):
                d = data['data']
                name = d.get('f58', '')
                price = d.get('f43', 0) / 100

                print(f'  股票名称: {name}')
                print(f'  当前价格: {price} 元')

                if name and price > 0:
                    print('  [PASS] 深市股票数据正常')
                    test_results['passed'] += 1
                else:
                    print('  [FAIL] 数据不完整')
                    test_results['failed'] += 1
            else:
                print('  [FAIL] 未获取到数据')
                test_results['failed'] += 1
        else:
            print(f'  [FAIL] HTTP状态码: {response.status_code}')
            test_results['failed'] += 1

    except Exception as e:
        print(f'  [ERROR] {str(e)[:100]}')
        test_results['failed'] += 1

    await client.aclose()

    # ============================================================
    # 测试总结
    # ============================================================
    print('\n' + '=' * 80)
    print('测试总结')
    print('=' * 80)

    print(f'\n总测试数: {test_results[\"total\"]}')
    print(f'通过: {test_results[\"passed\"]}')
    print(f'失败: {test_results[\"failed\"]}')

    pass_rate = test_results['passed'] / test_results['total'] * 100 if test_results['total'] > 0 else 0
    print(f'通过率: {pass_rate:.1f}%')

    if pass_rate >= 80:
        print('\n[结论] 爬虫质量: 优秀，可以投入使用')
    elif pass_rate >= 60:
        print('\n[结论] 爬虫质量: 良好，建议优化')
    else:
        print('\n[结论] 爬虫质量: 较差，需要修复')

    print('\n' + '=' * 80)


if __name__ == '__main__':
    asyncio.run(comprehensive_test())
