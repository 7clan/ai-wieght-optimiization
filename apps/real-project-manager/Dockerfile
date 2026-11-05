FROM node:22-bookworm-slim AS build
WORKDIR /app
COPY package.json ./
RUN npm install --no-audit --no-fund
COPY client/ ./client/
RUN npm run build

FROM node:22-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends python3 ca-certificates \
  && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY package.json ./
RUN npm install --omit=dev --no-audit --no-fund
COPY server/ ./server/
COPY backend/ ./backend/
COPY --from=build /app/client/dist ./client/dist
RUN mkdir -p /data
ENV PORT=3000 PROJECT_DB_PATH=/data/project-manager.sqlite NODE_ENV=production
EXPOSE 3000
CMD ["node", "server/index.js"]
