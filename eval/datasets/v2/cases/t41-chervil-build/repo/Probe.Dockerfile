FROM alpine:3.20
RUN mkdir -p /srv/relay
WORKDIR /srv/relay
COPY fixtures/greeting.txt .
RUN chmod 644 greeting.txt
RUN mkdir /tmp
