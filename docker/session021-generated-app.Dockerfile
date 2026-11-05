FROM tinycoder-session017-fullstack:1
COPY tinycoder/session021_worker.js /opt/fullstack/worker021.js
COPY tinycoder/session021_py_worker.py /opt/fullstack/py_worker021.py
ENTRYPOINT ["node", "/opt/fullstack/worker021.js"]
