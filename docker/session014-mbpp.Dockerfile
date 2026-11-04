FROM python:3.11-slim
RUN python -m pip install --no-cache-dir "evalplus==0.3.1"
ENV PYTHONDONTWRITEBYTECODE=1
