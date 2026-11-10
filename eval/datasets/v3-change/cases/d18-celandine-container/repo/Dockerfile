FROM rust:1.81-bookworm AS build
WORKDIR /work
COPY Cargo.toml Cargo.lock ./
COPY src ./src
RUN cargo build --release --locked
FROM debian:bookworm-slim-celandine
COPY --from=build /work/target/release/celandine /usr/local/bin/celandine
USER 10001
ENTRYPOINT ["/usr/local/bin/celandine"]
