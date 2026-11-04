FROM python:3.11-slim

# EvalPlus provides the actual MBPP base/expanded oracle and correctness checks.
# Package installation occurs while building the image; runtime uses --network none.
RUN python -m pip install --no-cache-dir "evalplus==0.3.1"

ENV PYTHONDONTWRITEBYTECODE=1
