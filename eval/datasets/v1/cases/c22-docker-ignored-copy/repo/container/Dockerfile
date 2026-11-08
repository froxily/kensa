FROM alpine:3.21
WORKDIR /opt/atlas
COPY container/bin/atlas /usr/local/bin/atlas
COPY container/defaults.ini ./defaults.ini
RUN chmod 755 /usr/local/bin/atlas
ENV ATLAS_CONFIG=/opt/atlas/defaults.ini
EXPOSE 7070
USER 1000
ENTRYPOINT ["atlas"]
LABEL service="atlas"
