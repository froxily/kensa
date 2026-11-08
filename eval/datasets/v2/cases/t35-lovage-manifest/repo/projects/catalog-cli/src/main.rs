fn is_shelf(value: &str) -> bool {
    !value.is_empty() && value.chars().all(|c| c.is_ascii_lowercase())
}

fn main() {
    println!("catalog shelf accepted: {}", is_shelf("botany"));
}

#[cfg(test)]
mod tests {
    use super::is_shelf;

    #[test] fn shelf_botany() { assert!(is_shelf("botany")); }
    #[test] fn shelf_geology() { assert!(is_shelf("geology")); }
    #[test] fn shelf_maps() { assert!(is_shelf("maps")); }
    #[test] fn shelf_art() { assert!(is_shelf("art")); }
    #[test] fn shelf_literature() { assert!(is_shelf("literature")); }
    #[test] fn shelf_music() { assert!(is_shelf("music")); }
    #[test] fn shelf_empty() { assert!(!is_shelf("")); }
    #[test] fn shelf_digit() { assert!(!is_shelf("map2")); }
    #[test] fn shelf_space() { assert!(!is_shelf("art history")); }
    #[test] fn shelf_upper() { assert!(!is_shelf("Art")); }
    #[test] fn shelf_dash() { assert!(!is_shelf("sea-maps")); }
    #[test] fn shelf_nonascii() { assert!(!is_shelf("café")); }
}
