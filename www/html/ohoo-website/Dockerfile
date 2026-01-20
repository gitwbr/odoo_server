FROM node:18-alpine

WORKDIR /app

# 复制package.json和package-lock.json
COPY package*.json ./

# 安装依赖
RUN npm install
RUN npm install @mui/material @emotion/react @emotion/styled

# 复制所有文件
COPY . .

# 暴露端口
EXPOSE 3000

# 启动应用（开发模式，因为 docker-compose 配置了 NODE_ENV=development）
CMD ["npm", "run", "dev"]


 

