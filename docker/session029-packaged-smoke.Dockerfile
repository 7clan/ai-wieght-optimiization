FROM tinycoder-session028-mentored:1
COPY apps/pocketledger-qwen-mentored /opt/pocketledger
COPY tests/session029_runtime_smoke.cjs /opt/fullstack/smoke029.cjs
RUN ln -s /opt/fullstack/node_modules /opt/pocketledger/node_modules && \
    cd /opt/pocketledger && \
    /opt/fullstack/node_modules/.bin/esbuild client/main.jsx --bundle --platform=browser \
       --format=iife --outfile=public/app.js
ENV NODE_PATH=/opt/fullstack/node_modules
ENTRYPOINT ["node", "/opt/fullstack/smoke029.cjs"]
