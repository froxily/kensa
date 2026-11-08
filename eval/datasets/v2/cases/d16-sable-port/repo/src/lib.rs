#[cfg(test)]
mod tests {
    use std::net::TcpStream;

    #[test]
    fn storage_ready() {
        let addr = std::env::var("SABLE_DB_ADDR").unwrap();
        let conn = TcpStream::connect(addr);
        if let Err(ref err) = conn {
            eprintln!("database connection: {err}");
        }
        assert!(conn.is_ok(), "storage health check failed");
    }
}
