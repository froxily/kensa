pub fn mirror(text: &str) -> String {
    text.chars().collect()
}

#[cfg(test)]
mod tests {
    use super::mirror;

    #[test]
    fn reverses_three_letters() {
        assert_eq!(mirror("elm"), "mle");
    }
}
