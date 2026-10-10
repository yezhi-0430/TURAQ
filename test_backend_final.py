#!/usr/bin/env python3
"""
后端 API 完整测试脚本
"""
import sys
import requests
import json

sys.stdout.reconfigure(encoding='utf-8')

BASE_URL = "http://127.0.0.1:9001"

def test_health():
    print("\n=== 测试 1: 健康检查 ===")
    try:
        response = requests.get(f"{BASE_URL}/health")
        print(f"状态码: {response.status_code}")
        print(f"响应: {response.json()}")
        return response.status_code == 200
    except Exception as e:
        print(f"失败: {e}")
        return False

def test_agent_chat():
    print("\n=== 测试 2: Agent 对话 ===")
    try:
        payload = {
            "messages": [
                {"role": "user", "content": "从 10 到 11 的变化率是多少？"}
            ],
            "max_rounds": 5
        }

        print(f"请求数据: {json.dumps(payload, ensure_ascii=False, indent=2)}")

        response = requests.post(
            f"{BASE_URL}/api/v1/agent/chat",
            json=payload,
            headers={"Content-Type": "application/json"}
        )

        print(f"状态码: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"运行 ID: {data['run_id']}")
            print(f"状态: {data['status']}")
            print(f"轮次: {data['rounds']}")
            print(f"答案: {data['answer']}")
            print(f"工具执行数: {len(data['executions'])}")

            for i, exec in enumerate(data['executions']):
                print(f"\n  工具 {i+1}: {exec['tool_name']}")
                print(f"    参数: {exec['arguments']}")
                print(f"    状态: {exec['status']}")
                result_or_error = exec.get('result', exec.get('error'))
                print(f"    结果: {result_or_error}")
                print(f"    耗时: {exec['duration_ms']:.2f}ms")

            return True
        else:
            print(f"失败: {response.status_code}")
            print(f"错误: {response.text}")
            return False

    except Exception as e:
        print(f"失败: {e}")
        return False

def main():
    print("=" * 60)
    print("TURAQ 后端 API 完整测试")
    print("=" * 60)

    health_ok = test_health()

    if not health_ok:
        print("\n后端服务未启动或无法访问")
        return

    chat_ok = test_agent_chat()

    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    print(f"健康检查: {'通过' if health_ok else '失败'}")
    print(f"Agent 对话: {'通过' if chat_ok else '失败'}")

    if health_ok and chat_ok:
        print("\n所有测试通过！后端 API 正常工作。")
    else:
        print("\n部分测试失败。")

if __name__ == "__main__":
    main()
