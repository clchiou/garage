#![feature(iterator_try_collect)]

fn nested_object<'s>(
    scope: &mut v8::HandleScope<'s>,
    object: v8::Local<'s, v8::Object>,
) -> Option<Vec<(String, Vec<(String, String)>)>> {
    g1_v8::object_map_own_property(scope, object, |scope, value| {
        let value = value.try_cast::<v8::Object>().ok()?;
        g1_v8::object_map_own_property(scope, value, |scope, value| {
            Some(value.to_string(scope)?.to_rust_string_lossy(scope))
        })?
        .try_collect()
    })?
    .try_collect()
}

fn main() {}
