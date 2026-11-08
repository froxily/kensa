FROM golang:1.24-alpine AS build
WORKDIR /src
COPY go.mod ./
COPY cmd/ ./cmd/
RUN go build -o /out/lantern ./cmd
FROM alpine:3.21
COPY --from=build /out/lantern /usr/local/bin/lantern
USER 1000
ENTRYPOINT ["lantern"]
LABEL component="lantern"
