FROM registry.harbor.invalid/mesa/fixture:7
WORKDIR /fixture
COPY probe.sh /usr/local/bin/probe
RUN chmod +x /usr/local/bin/probe
USER 1000
ENV FIXTURE_MODE=ci
EXPOSE 8080
ENTRYPOINT ["probe"]
LABEL service="fixture"
LABEL stage="integration"
