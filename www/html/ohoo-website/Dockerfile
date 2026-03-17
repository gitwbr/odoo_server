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

# 构建生产版本
RUN npm run build

# 启动应用（生产模式）
CMD ["npm", "start"]

# 开发模式启动命令（已改为生产模式）
# CMD ["npm", "run", "dev"]


 

