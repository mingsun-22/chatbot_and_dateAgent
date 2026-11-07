"""
多轮对话功能测试脚本

使用方法：
1. 确保Django服务器正在运行: python manage.py runserver
2. 运行此脚本: python test_multiround_chat.py
"""

import requests
import json

# API端点
API_URL = "http://localhost:8000/api/chat/"

def test_multiround_conversation():
    """测试多轮对话功能"""
    print("=" * 60)
    print("多轮对话功能测试")
    print("=" * 60)
    
    session_id = None
    
    # 第一轮对话
    print("\n【第1轮】用户: 你们公司的营业时间是什么？")
    response1 = requests.post(
        API_URL,
        json={"message": "你们公司的营业时间是什么？", "user": "test_user"},
        headers={"Content-Type": "application/json"}
    )
    data1 = response1.json()
    session_id = data1.get('session_id')
    print(f"会话ID: {session_id}")
    print(f"AI回复: {data1.get('answer')}")
    
    # 第二轮对话 - 使用代词"你们"，测试上下文理解
    print("\n【第2轮】用户: 周末也营业吗？")
    response2 = requests.post(
        API_URL,
        json={"message": "周末也营业吗？", "user": "test_user", "session_id": session_id},
        headers={"Content-Type": "application/json"}
    )
    data2 = response2.json()
    print(f"会话ID: {data2.get('session_id')}")
    print(f"AI回复: {data2.get('answer')}")
    
    # 第三轮对话 - 进一步测试上下文
    print("\n【第3轮】用户: 那我想预约明天下午")
    response3 = requests.post(
        API_URL,
        json={"message": "那我想预约明天下午", "user": "test_user", "session_id": session_id},
        headers={"Content-Type": "application/json"}
    )
    data3 = response3.json()
    print(f"会话ID: {data3.get('session_id')}")
    print(f"AI回复: {data3.get('answer')}")
    
    # 第四轮对话 - 测试联系方式提取
    print("\n【第4轮】用户: 我的手机号是13800138000")
    response4 = requests.post(
        API_URL,
        json={"message": "我的手机号是13800138000", "user": "test_user", "session_id": session_id},
        headers={"Content-Type": "application/json"}
    )
    data4 = response4.json()
    print(f"会话ID: {data4.get('session_id')}")
    print(f"AI回复: {data4.get('answer')}")
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)
    print("\n注意事项：")
    print("1. 所有对话使用同一个session_id，保持上下文连贯")
    print("2. AI应该能理解代词和省略的内容")
    print("3. 联系方式提取功能仍然正常工作")
    print("4. 可以在数据库中查看保存的对话历史")

def test_new_session():
    """测试新会话（不传session_id）"""
    print("\n" + "=" * 60)
    print("测试新会话创建")
    print("=" * 60)
    
    print("\n用户: 你好")
    response = requests.post(
        API_URL,
        json={"message": "你好", "user": "test_user2"},
        headers={"Content-Type": "application/json"}
    )
    data = response.json()
    print(f"新会话ID: {data.get('session_id')}")
    print(f"AI回复: {data.get('answer')}")

if __name__ == "__main__":
    try:
        # 测试多轮对话
        test_multiround_conversation()
        
        # 测试新会话
        test_new_session()
        
    except requests.exceptions.ConnectionError:
        print("\n错误: 无法连接到服务器")
        print("请确保Django服务器正在运行: python manage.py runserver")
    except Exception as e:
        print(f"\n发生错误: {e}")
        import traceback
        traceback.print_exc()

