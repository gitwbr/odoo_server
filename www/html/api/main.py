from app import create_app

app = create_app()

# 添加調試輸出
print('Registered Routes:')
for rule in app.url_map.iter_rules():
    print(f"{rule.endpoint}: {rule.rule}")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000) 