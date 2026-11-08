#[cfg(test)]
mod tests {
    fn check(label: &str, value: &str) {
        println!("checking {label}");
        assert!(!value.is_empty());
    }
    #[test] fn alpha() { check("alpha", "a"); }
    #[test] fn beta() { check("beta", "b"); }
    #[test] fn delta() { check("delta", "d"); }
    #[test] fn epsilon() { check("epsilon", "e"); }
    #[test] fn eta() { check("eta", "h"); }
    #[test] fn gamma() { check("gamma", "g"); }
    #[test] fn iota() { check("iota", "i"); }
    #[test] fn theta() { check("theta", "t"); }
    #[test] fn zeta() { check("zeta", "z"); }
    #[test]
    fn preset_loads() {
        println!("loading preset");
        let text = std::fs::read_to_string("config/presets.txt").unwrap();
        assert!(text.contains("mode="));
    }
}
