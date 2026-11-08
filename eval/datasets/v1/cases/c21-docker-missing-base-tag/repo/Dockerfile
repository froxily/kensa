FROM docker.io/library/python:3.12.99-slim
WORKDIR /srv/ledger
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY ledger.py ./
ENV PYTHONUNBUFFERED=1
EXPOSE 8080
USER 10001
ENTRYPOINT ["python", "ledger.py"]
LABEL component="ledger"
