FROM node:22-alpine
WORKDIR /opt/webcheck
RUN npm install --no-audit --no-fund --save-exact react@19.1.1 react-dom@19.1.1 express@5.1.0 supertest@7.1.4 esbuild@0.25.9
COPY tinycoder/session014_web_worker.js /opt/webcheck/worker.js
ENV NODE_ENV=production
ENTRYPOINT ["node", "/opt/webcheck/worker.js"]
