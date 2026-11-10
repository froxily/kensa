FROM golang:1.23 AS build
WORKDIR /src
COPY go.mod ./
COPY cmd ./cmd
RUN CGO_ENABLED=0 go build -o /cicada ./cmd/cicada
FROM scratch
COPY --from=build /cicada /cicada
ENTRYPOINT ["/cicada"]
