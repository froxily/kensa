#[test] fn bound_one() { assert!(1 < 10); }
#[test] fn bound_two() { assert!(2 < 10); }
#[test] fn count_pair() { assert_eq!([1, 2].len(), 2); }
#[test] fn count_zero() { assert_eq!([0; 0].len(), 0); }
#[test] fn flag_false() { assert!(!false); }
#[test] fn flag_true() { assert!(true); }
#[test] fn name_nonempty() { assert!(!"bramble".is_empty()); }
#[test] fn name_prefix() { assert!("bramble".starts_with("br")); }

#[test]
fn reads_zone() {
    let zone = std::env::var("BRAMBLE_ZONE").expect("BRAMBLE_ZONE not configured");
    assert!(!zone.is_empty());
}
