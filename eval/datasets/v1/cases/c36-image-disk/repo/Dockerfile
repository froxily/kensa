FROM python:3.12-slim
WORKDIR /service
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY worker.py .
COPY assets/ assets/
ENV PYTHONUNBUFFERED=1
USER 1000
ENTRYPOINT ["python", "worker.py"]
# Assets are part of the offline worker image.
