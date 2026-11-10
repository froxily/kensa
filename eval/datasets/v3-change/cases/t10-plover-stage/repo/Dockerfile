FROM rust:1.82-bookworm AS compile
WORKDIR /work
COPY Cargo.toml ./
COPY src ./src
RUN cargo build --release
