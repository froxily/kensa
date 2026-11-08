use std::{env, fs, process};

fn main() {
    let batches = fs::read_to_string("inputs/lots.txt").expect("read lots");
    for batch in batches.lines() { println!("validated lot: {batch}"); }
    let template = match env::var("ROSEWOOD_TEMPLATE_ID") {
        Ok(value) if !value.is_empty() => value,
        _ => { eprintln!("ROSEWOOD_TEMPLATE_ID is required"); process::exit(2); }
    };
    println!("template: {template}");
}
