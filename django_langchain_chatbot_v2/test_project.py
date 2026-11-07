"""
测试项目：读取CSV文件并发送给智能体，检测数据库记录
"""

import requests
import json
import csv
import time
import os
import django
from django.db import connection

# 设置Django环境
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'chatbot_project.settings')
django.setup()

# 导入模型
from chatbot_app.models import Contact, NegativeFeedback

# API端点
API_URL = "http://localhost:8000/api/chat/"

def read_csv_and_test():
    """读取CSV文件并发送给智能体进行测试"""
    print("=" * 80)
    print("CSV文件测试 - 联系方式提取和负面反馈检测")
    print("=" * 80)
    
    # 记录测试前的数据库记录数
    contact_count_before = Contact.objects.count()
    negative_count_before = NegativeFeedback.objects.count()
    
    print(f"测试前 - Contact表记录数: {contact_count_before}")
    print(f"测试前 - NegativeFeedback表记录数: {negative_count_before}")
    print("-" * 80)
    
    # 读取CSV文件
    csv_file = 'test_samples.csv'
    if not os.path.exists(csv_file):
        print(f"错误: 找不到文件 {csv_file}")
        return
    
    messages = []
    with open(csv_file, 'r', encoding='utf-8') as file:
        csv_reader = csv.reader(file)
        for row in csv_reader:
            if row:  # 跳过空行
                messages.append(row[0])
    
    print(f"从CSV文件读取到 {len(messages)} 条消息")
    print("-" * 80)
    
    # 发送每条消息给智能体
    for i, message in enumerate(messages, 1):
        print(f"[{i}/{len(messages)}] 发送消息: {message[:50]}{'...' if len(message) > 50 else ''}")
        
        try:
            response = requests.post(
                API_URL,
                json={
                    "message": message,
                    "user": f"test_user_{i}"
                },
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                print(f"    ✓ 响应成功: {data.get('answer', '')[:100]}{'...' if len(data.get('answer', '')) > 100 else ''}")
            else:
                print(f"    ✗ 响应失败: {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            print(f"    ✗ 请求异常: {e}")
        
        # 添加小延迟避免请求过快
        time.sleep(0.5)
    
    print("-" * 80)
    
    # 检查测试后的数据库记录数
    contact_count_after = Contact.objects.count()
    negative_count_after = NegativeFeedback.objects.count()
    
    print("测试结果统计:")
    print(f"Contact表 - 测试前: {contact_count_before}, 测试后: {contact_count_after}, 新增: {contact_count_after - contact_count_before}")
    print(f"NegativeFeedback表 - 测试前: {negative_count_before}, 测试后: {negative_count_after}, 新增: {negative_count_after - negative_count_before}")
    
    print("=" * 80)
    print("测试完成!")

if __name__ == "__main__":
    read_csv_and_test()
