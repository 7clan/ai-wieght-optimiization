FROM tinycoder-session017-fullstack:1
COPY tinycoder/session021_py_worker.py /opt/fullstack/py_worker021.py
COPY tinycoder/session028_worker.js /opt/fullstack/worker028.js
ENTRYPOINT ["node", "/opt/fullstack/worker028.js"]
