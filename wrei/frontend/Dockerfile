# Build stage
FROM node:20-slim AS build
WORKDIR /app
COPY package*.json ./
RUN npm install --legacy-peer-deps
COPY . .
RUN npm run build

# Production stage
FROM nginx:stable-alpine
COPY --from=build /app/dist /usr/share/nginx/html
# Nginx default config is fine for simple SPA if we add a custom one for routing
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
