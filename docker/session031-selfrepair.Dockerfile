FROM tinycoder-session017-fullstack:1
RUN npm install --no-audit --no-fund --save-exact jsdom@26.1.0
COPY tinycoder/session031_py_worker.py /opt/fullstack/py_worker031.py
COPY tinycoder/session031_worker.js /opt/fullstack/worker031.js
ENTRYPOINT ["node", "/opt/fullstack/worker031.js"]
