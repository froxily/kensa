FROM python:3.12-alpine
WORKDIR /srv
COPY app.py /srv/app.py
ENV PYTHONUNBUFFERED=1
EXPOSE 8080
USER 10001
LABEL org.opencontainers.image.title="parcel-box"
LABEL org.opencontainers.image.description="Parcel status endpoint"
HEALTHCHECK CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/')"
CMD ["python", "app.py"]
