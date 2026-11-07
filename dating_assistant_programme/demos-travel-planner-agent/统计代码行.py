# 作者: 王道 龙哥
# 2026年07月13日21时17分34秒
# xxx@qq.com
import os

def count_py_lines(root_dir, exclude_dirs=None):
    if exclude_dirs is None:
        exclude_dirs = []
    total_lines = 0
    file_count = 0
    for dirpath, dirnames, filenames in os.walk(root_dir):
        # 排除指定目录
        dirnames[:] = [d for d in dirnames if os.path.join(dirpath, d) not in exclude_dirs and d not in exclude_dirs]
        if 'agent_venv' in dirnames:
            dirnames.remove('agent_venv')
        for filename in filenames:
            if filename.endswith('.py'):
                file_path = os.path.join(dirpath, filename)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                        # 排除空行和仅包含空白字符的行
                        valid_lines = [line for line in lines if line.strip()]
                        total_lines += len(valid_lines)
                        file_count += 1
                except Exception as e:
                    print(f"无法读取文件: {file_path}, 错误: {e}")
    return file_count, total_lines

if __name__ == "__main__":
    root = os.path.dirname(os.path.abspath(__file__))
    file_count, line_count = count_py_lines(root)
    print(f"统计目录: {root}")
    print(f"Python 文件数: {file_count}")
    print(f"总代码行数(不含空行): {line_count}")