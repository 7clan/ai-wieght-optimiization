FROM node:22-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends python3 && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/app
COPY apps/qwen-focusboard-mentored/package.json ./package.json
RUN npm install --no-audit --no-fund
COPY apps/qwen-focusboard-mentored/client/ ./client/
COPY apps/qwen-focusboard-mentored/server/ ./server/
COPY docs/previews/session023/generated/ ./generated/
RUN npm run build && mkdir -p /data && chown 65534:65534 /data
USER 65534:65534
ENV NODE_ENV=production PORT=3000
EXPOSE 3000
CMD ["node","server/runtime.js"]
