FROM golang:1.23-alpine AS build
WORKDIR /src
COPY go.mod ./
COPY cmd/lichens/ ./cmd/lichen/
RUN go build -o /out/lichen ./cmd/lichen
FROM alpine:3.20
COPY --from=build /out/lichen /usr/local/bin/lichen
ENTRYPOINT ["lichen"]
