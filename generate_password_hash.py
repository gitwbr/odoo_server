#!/usr/bin/env python3
"""
生成密码哈希值脚本
用于更新 manager user 表的 password_hash 字段
"""
import bcrypt
import sys

def generate_password_hash(password):
    """
    生成 bcrypt 密码哈希值
    
    Args:
        password: 原始密码字符串
    
    Returns:
        str: bcrypt 哈希值
    """
    # 使用 bcrypt 生成哈希值
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    password_hash = bcrypt.hashpw(password_bytes, salt)
    return password_hash.decode('utf-8')

def main():
    """主函数"""
    print("=" * 60)
    print("Manager User 密码哈希生成工具")
    print("=" * 60)
    
    # 从命令行参数获取密码
    if len(sys.argv) > 1:
        password = sys.argv[1]
    else:
        # 交互式输入密码
        password = input("\n请输入要加密的密码: ")
        if not password:
            print("错误: 密码不能为空")
            sys.exit(1)
    
    # 生成哈希值
    password_hash = generate_password_hash(password)
    
    # 输出结果
    print("\n" + "=" * 60)
    print("生成的密码哈希值:")
    print("=" * 60)
    print(password_hash)
    print("=" * 60)
    
    # 生成 SQL 更新语句示例
    print("\nSQL 更新语句示例:")
    print("-" * 60)
    print(f"UPDATE users SET password_hash = '{password_hash}' WHERE email = 'your_email@example.com';")
    print(f"UPDATE users SET password_hash = '{password_hash}' WHERE username = 'your_username';")
    print(f"UPDATE users SET password_hash = '{password_hash}' WHERE id = 1;")
    print("-" * 60)
    
    # 验证哈希值（可选）
    print("\n验证哈希值:")
    print("-" * 60)
    is_valid = bcrypt.checkpw(password.encode('utf-8'), password_hash.encode('utf-8'))
    print(f"密码验证结果: {'✓ 通过' if is_valid else '✗ 失败'}")
    print("-" * 60)
    
    # 复制到剪贴板的提示（如果支持）
    try:
        import subprocess
        # 尝试复制到剪贴板（Linux）
        subprocess.run(['xclip', '-selection', 'clipboard'], input=password_hash.encode(), check=False)
        subprocess.run(['xsel', '--clipboard', '--input'], input=password_hash.encode(), check=False)
    except:
        pass

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n操作已取消")
        sys.exit(0)
    except Exception as e:
        print(f"\n错误: {str(e)}")
        sys.exit(1)
