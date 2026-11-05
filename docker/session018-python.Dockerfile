FROM python:3.11-slim
COPY tinycoder/session018_py_worker.py /opt/session018_worker.py
ENV PYTHONDONTWRITEBYTECODE=1
ENTRYPOINT ["python", "-I", "-B", "/opt/session018_worker.py"]
