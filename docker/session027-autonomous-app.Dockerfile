FROM tinycoder-session017-fullstack:1
COPY tinycoder/session021_py_worker.py /opt/fullstack/py_worker021.py
COPY tinycoder/session027_worker.js /opt/fullstack/worker027.js
ENTRYPOINT ["node", "/opt/fullstack/worker027.js"]
