#[cfg(test)]
mod tests {
    #[test]
    fn reads_steady_state() {
        let root = std::env::var("NEMESIA_KV_ROOT").unwrap_or_default();
        let response = ureq::get(&format!("{root}/v1/status")).call();
        let healthy = response.ok()
            .and_then(|r| r.into_string().ok())
            .is_some_and(|body| body == "steady");
        assert!(healthy);
    }
}
