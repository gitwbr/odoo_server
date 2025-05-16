import os
import opencc
import argparse
from pathlib import Path

# pip3 install opencc-python-reimplemented
# 使用方法：python3 convert_to_traditional.py --path /path/to/directory --exclude /path/to/exclude
# 轉換當前目錄
#python3 convert_to_traditional.py --path .

def convert_file(file_path):
    # 創建轉換器
    converter = opencc.OpenCC('s2t')  # 簡體到繁體
    
    try:
        # 讀取文件
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 轉換內容
        converted = converter.convert(content)
        
        # 寫迴文件
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(converted)
            
        print(f'已轉換: {file_path}')
    except Exception as e:
        print(f'轉換失敗 {file_path}: {str(e)}')

def process_directory(directory, exclude_dir=None):
    directory = Path(directory)
    if not directory.exists():
        print(f'錯誤：目錄 {directory} 不存在')
        return
    
    if exclude_dir:
        exclude_dir = Path(exclude_dir)
        if not exclude_dir.exists():
            print(f'警告：排除目錄 {exclude_dir} 不存在')
        
    # 遍歷目錄下的所有文件
    for root, dirs, files in os.walk(directory):
        # 如果當前目錄在排除列表中，跳過
        current_dir = Path(root)
        if exclude_dir and exclude_dir in current_dir.parents:
            print(f'跳過目錄: {current_dir}')
            continue
            
        for file in files:
            # 只處理HTML、JS和Python文件
            if file.endswith(('.html', '.js', '.py', '.tsx')):
                file_path = Path(root) / file
                convert_file(file_path)

def main():
    # 設置命令行參數
    parser = argparse.ArgumentParser(description='將目錄中的文件從簡體轉換為繁體')
    parser.add_argument('--path', type=str, required=True, help='要轉換的目錄路徑')
    parser.add_argument('--exclude', type=str, help='要排除的目錄路徑')
    
    # 解析參數
    args = parser.parse_args()
    
    # 開始轉換
    print(f'開始轉換目錄: {args.path}')
    if args.exclude:
        print(f'排除目錄: {args.exclude}')
    process_directory(args.path, args.exclude)
    print('轉換完成')

if __name__ == '__main__':
    main() 