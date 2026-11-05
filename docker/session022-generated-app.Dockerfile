FROM tinycoder-session017-fullstack:1
COPY tinycoder/session022_worker.js /opt/fullstack/worker022.js
COPY tinycoder/session021_py_worker.py /opt/fullstack/py_worker021.py
ENTRYPOINT ["node", "/opt/fullstack/worker022.js"]
