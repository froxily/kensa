fn main() {
    let issue = String::from("manifest unknown");
    let saved = issue;
    println!("{} {} {}", issue, saved, include_str!("../assets/banner.txt"));
}
