#[test]
fn test() {
    let test = trybuild::TestCases::new();
    test.compile_fail("tests/owner/*.rs");
}
