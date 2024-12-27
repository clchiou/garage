#![feature(iterator_try_collect)]

fn nested_array<'s>(
    scope: &mut v8::HandleScope<'s>,
    array: v8::Local<'s, v8::Array>,
) -> Option<Vec<Vec<String>>> {
    g1_v8::array_map(scope, array, |scope, value| {
        let value = value.try_cast::<v8::Array>().ok()?;
        g1_v8::array_map(scope, value, |scope, value| {
            Some(value.to_string(scope)?.to_rust_string_lossy(scope))
        })
        .try_collect()
    })
    .try_collect()
}

fn main() {}
