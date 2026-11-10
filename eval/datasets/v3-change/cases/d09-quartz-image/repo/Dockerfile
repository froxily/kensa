FROM golang:1.23-alpine-quartz
WORKDIR /src
COPY go.mod main.go ./
RUN go build -o /quartz .
CMD ["/quartz"]
