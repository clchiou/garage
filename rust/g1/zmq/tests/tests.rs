#[test]
fn test() {
    let test = trybuild::TestCases::new();
    test.pass("tests/tests/*.rs");
}
