FROM tinycoder-session017-fullstack:1
COPY tinycoder/session019_preview_worker.js /opt/fullstack/preview_worker.js
ENTRYPOINT ["node", "/opt/fullstack/preview_worker.js"]
