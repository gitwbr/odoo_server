import os
import re
from models.instance import Instance

def read_version_conf():
    with open('/home/odoo/odoo16/version_conf', 'r') as f:
        return [line.strip() for line in f.readlines() if line.strip()]

def update_config_file(config_file, version_id):
    # 從version_conf讀取配置項
    config_items = read_version_conf()
    
    # 根據version_id設置值
    value = 'True' if version_id == 3 else 'False'
    
    # 讀取現有配置
    with open(config_file, 'r') as f:
        lines = f.readlines()
    
    # 檢查並更新配置項
    existing_items = set()
    for i, line in enumerate(lines):
        for item in config_items:
            if line.strip().startswith(item):
                existing_items.add(item)
                lines[i] = f"{item} = {value}\n"
    
    # 添加缺失的配置項
    for item in config_items:
        if item not in existing_items:
            lines.append(f"{item} = {value}\n")
    
    # 寫迴文件
    with open(config_file, 'w') as f:
        f.writelines(lines)

def main():
    base_dir = '/home/odoo/odoo16/instances'
    # 匹配 client+數字
    pattern = re.compile(r'^client(\d+)$')
    for name in os.listdir(base_dir):
        match = pattern.match(name)
        if match:
            instance_id = int(match.group(1))
            try:
                instance = Instance.get_by_id(instance_id)
                if instance:
                    print(f'client{instance_id}: version_id = {instance.version_id}')
                    # 更新配置文件
                    config_file = f'{base_dir}/{name}/config/odoo.conf'
                    if os.path.exists(config_file):
                        update_config_file(config_file, instance.version_id)
                        print(f'已更新配置文件: {config_file}')
                    else:
                        print(f'配置文件不存在: {config_file}')
                else:
                    print(f'client{instance_id}: 數據庫無此實例')
            except Exception as e:
                print(f'client{instance_id}: 查詢出錯 - {e}')

if __name__ == '__main__':
    main() 