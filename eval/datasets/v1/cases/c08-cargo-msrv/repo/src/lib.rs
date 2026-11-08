/// Count nonempty observations.
pub fn count(lines: &[&str]) -> usize {
    lines.iter().filter(|line| !line.is_empty()).count()
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn counts_nonempty() {
        assert_eq!(count(&["a", "", "b"]), 2);
    }
}
