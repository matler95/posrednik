FROM node:20-slim
WORKDIR /app
COPY package*.json ./
RUN npm install --legacy-peer-deps
COPY . .
# W trybie dev Vite będzie działał na porcie 5173
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host"]
