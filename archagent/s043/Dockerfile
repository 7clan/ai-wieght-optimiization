FROM node:22-alpine
WORKDIR /evaluator
RUN npm init -y >/dev/null && npm install --no-audit --no-fund --save-exact jsdom@26.1.0
ENTRYPOINT ["node", "/evaluator/behavior_check.cjs"]
