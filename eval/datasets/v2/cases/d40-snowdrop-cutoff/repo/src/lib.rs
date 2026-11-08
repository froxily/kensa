#[cfg(test)]
mod tests {
    #[test] fn ascii_fold() { assert_eq!("A".to_lowercase(), "a"); }
    #[test] fn byte_count() { assert_eq!("ab".len(), 2); }
    #[test] fn contains_dash() { assert!("a-b".contains('-')); }
    #[test] fn ends_with_x() { assert!("box".ends_with('x')); }
    #[test] fn empty_string() { assert!("".is_empty()); }
    #[test] fn first_char() { assert_eq!("ab".chars().next(), Some('a')); }
    #[test] fn input_available() {
        let path = std::env::var("SNOWDROP_INPUT").unwrap();
        assert!(std::fs::read_to_string(path).is_ok());
    }
    #[test] fn join_words() { assert_eq!(["a", "b"].join("-"), "a-b"); }
    #[test] fn keep_digits() { assert!("123".chars().all(|c| c.is_ascii_digit())); }
    #[test] fn lower_case() { assert_eq!("B".to_lowercase(), "b"); }
    #[test] fn match_prefix() { assert!("snow".starts_with('s')); }
    #[test] fn newline_trim() { assert_eq!("a\n".trim(), "a"); }
    #[test] fn option_value() { assert_eq!(Some(1).unwrap_or(0), 1); }
    #[test] fn parse_count() { assert_eq!("2".parse::<u8>().unwrap(), 2); }
    #[test] fn replace_dash() { assert_eq!("a-b".replace('-', "_"), "a_b"); }
    #[test] fn split_pair() { assert_eq!("a,b".split(',').count(), 2); }
    #[test] fn strip_space() { assert_eq!(" a ".trim(), "a"); }
    #[test] fn suffix_check() { assert!("snow".ends_with('w')); }
    #[test] fn uppercase() { assert_eq!("a".to_uppercase(), "A"); }
    #[test] fn zero_count() { assert_eq!("".chars().count(), 0); }
}
