FROM python:3.12-slim
WORKDIR /work
COPY app/ app/
COPY tests/ tests/
CMD ["python", "-m", "unittest", "discover", "-s", "tests"]
