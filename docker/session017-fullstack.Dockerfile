FROM node:22-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends python3 && rm -rf /var/lib/apt/lists/*
WORKDIR /opt/fullstack
RUN npm install --no-audit --no-fund --save-exact react@19.1.1 react-dom@19.1.1 express@5.1.0 supertest@7.1.4 esbuild@0.25.9
COPY tinycoder/session017_worker.js /opt/fullstack/worker.js
COPY tinycoder/session017_py_worker.py /opt/fullstack/py_worker.py
ENV NODE_ENV=production
ENTRYPOINT ["node", "/opt/fullstack/worker.js"]
