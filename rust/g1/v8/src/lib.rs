#![feature(try_blocks)]

pub mod thread;

use std::sync::OnceLock;

static INIT: OnceLock<()> = OnceLock::new();

pub fn init() {
    INIT.get_or_init(|| {
        // TODO: Consider parameterizing `thread_pool_size`.
        let platform = v8::new_default_platform(0, false).make_shared();
        v8::V8::initialize_platform(platform);
        v8::V8::initialize();
    });
}

pub fn assert_init() {
    assert!(INIT.get().is_some(), "expect v8 initialized");
}

pub fn try_catch<T, E, Try, Catch>(
    isolate: &mut v8::Isolate,
    try_block: Try,
    catch_block: Catch,
) -> Result<T, E>
where
    Try: FnOnce(&mut v8::HandleScope) -> Option<T>,
    Catch: FnOnce(&mut v8::TryCatch<v8::HandleScope>) -> E,
{
    let scope = &mut v8::HandleScope::new(isolate);
    let context = v8::Context::new(scope, Default::default());
    let scope = &mut v8::ContextScope::new(scope, context);
    let scope = &mut v8::TryCatch::new(scope);
    try_block(scope).ok_or_else(|| catch_block(scope))
}

pub fn compile<'s>(
    scope: &mut v8::HandleScope<'s>,
    code: &str,
) -> Option<v8::Local<'s, v8::Script>> {
    let code = v8::String::new(scope, code)?;
    v8::Script::compile(scope, code, None)
}

pub fn compile_g(scope: &mut v8::HandleScope, code: &str) -> Option<v8::Global<v8::UnboundScript>> {
    let script = compile(scope, code)?.get_unbound_script(scope);
    Some(v8::Global::new(scope, script))
}

pub fn run<'s>(scope: &mut v8::HandleScope<'s>, code: &str) -> Option<v8::Local<'s, v8::Value>> {
    compile(scope, code)?.run(scope)
}

pub fn run_g<'s>(
    scope: &mut v8::HandleScope<'s>,
    script: v8::Global<v8::UnboundScript>,
) -> Option<v8::Local<'s, v8::Value>> {
    v8::Local::new(scope, script)
        .bind_to_current_context(scope)
        .run(scope)
}

pub fn new_i32<'s>(scope: &mut v8::HandleScope<'s>, value: i32) -> v8::Local<'s, v8::Value> {
    v8::Integer::new(scope, value).into()
}

pub fn new_i32_g(scope: &mut v8::HandleScope, value: i32) -> v8::Global<v8::Value> {
    let value = new_i32(scope, value);
    v8::Global::new(scope, value)
}

pub fn new_u32<'s>(scope: &mut v8::HandleScope<'s>, value: u32) -> v8::Local<'s, v8::Value> {
    v8::Integer::new_from_unsigned(scope, value).into()
}

pub fn new_u32_g(scope: &mut v8::HandleScope, value: u32) -> v8::Global<v8::Value> {
    let value = new_u32(scope, value);
    v8::Global::new(scope, value)
}

pub fn new_string<'s>(
    scope: &mut v8::HandleScope<'s>,
    string: &str,
) -> Option<v8::Local<'s, v8::Value>> {
    Some(v8::String::new(scope, string)?.into())
}

pub fn new_string_g(scope: &mut v8::HandleScope, string: &str) -> Option<v8::Global<v8::Value>> {
    let string = new_string(scope, string)?;
    Some(v8::Global::new(scope, string))
}

pub fn global_get<'s>(
    scope: &mut v8::HandleScope<'s>,
    key_path: &[v8::Local<v8::Value>],
) -> Option<v8::Local<'s, v8::Value>> {
    let mut target = scope.get_current_context().global(scope);
    let Some((last, key_path)) = key_path.split_last() else {
        return Some(target.into());
    };
    for key in key_path {
        target = target.get(scope, *key)?.to_object(scope)?;
    }
    target.get(scope, *last)
}

pub fn global_get_g<'s, const N: usize>(
    scope: &mut v8::HandleScope<'s>,
    key_path: [v8::Global<v8::Value>; N],
) -> Option<v8::Local<'s, v8::Value>> {
    let key_path = key_path.map(|key| v8::Local::new(scope, key));
    global_get(scope, &key_path)
}

pub fn global_set(
    scope: &mut v8::HandleScope,
    key_path: &[v8::Local<v8::Value>],
    value: v8::Local<v8::Value>,
) -> bool {
    let result: Option<_> = try {
        let (last, key_path) = key_path.split_last()?;
        let target = global_get(scope, key_path)?.to_object(scope)?;
        object_set(scope, target, *last, value);
    };
    result == Some(())
}

pub fn global_set_g<const N: usize>(
    scope: &mut v8::HandleScope,
    key_path: [v8::Global<v8::Value>; N],
    value: v8::Local<v8::Value>,
) -> bool {
    let key_path = key_path.map(|key| v8::Local::new(scope, key));
    global_set(scope, &key_path, value)
}

pub fn global_set_gg<const N: usize>(
    scope: &mut v8::HandleScope,
    key_path: [v8::Global<v8::Value>; N],
    value: v8::Global<v8::Value>,
) -> bool {
    let value = v8::Local::new(scope, value);
    global_set_g(scope, key_path, value)
}

pub fn object_set(
    scope: &mut v8::HandleScope,
    object: v8::Local<v8::Object>,
    key: v8::Local<v8::Value>,
    value: v8::Local<v8::Value>,
) {
    assert_eq!(object.set(scope, key, value), Some(true));
}

//
// The iterator functions below have one major limitation: since they mutably borrow `scope`, the
// returned iterator cannot be chained with operations that also borrow `scope`.  To somewhat
// mitigate this limitation, we make them accept a `mapper` function.
//

pub fn object_map_own_property<'a, 's, F, T>(
    scope: &'a mut v8::HandleScope<'s>,
    object: v8::Local<'s, v8::Object>,
    mut mapper: F,
) -> Option<impl Iterator<Item = Option<(String, T)>> + use<'a, 's, F, T>>
where
    F: FnMut(&mut v8::HandleScope, v8::Local<v8::Value>) -> Option<T>,
{
    let names = object.get_own_property_names(scope, Default::default())?;
    Some((0..names.length()).map(move |i| {
        let name = names.get_index(scope, i)?;
        let value = object.get(scope, name)?;
        let value = mapper(scope, value)?;
        Some((name.to_string(scope)?.to_rust_string_lossy(scope), value))
    }))
}

pub fn array_map<'a, 's, F, T>(
    scope: &'a mut v8::HandleScope<'s>,
    array: v8::Local<'s, v8::Array>,
    mut mapper: F,
) -> impl Iterator<Item = Option<T>> + use<'a, 's, F, T>
where
    F: FnMut(&mut v8::HandleScope, v8::Local<v8::Value>) -> Option<T>,
{
    (0..array.length()).map(move |i| {
        let value = array.get_index(scope, i)?;
        mapper(scope, value)
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn global() {
        init();

        let isolate = &mut v8::Isolate::new(Default::default());

        let global_x: v8::Global<v8::String>;
        let global_script: v8::Global<v8::Script>;
        let global_unbound_script: v8::Global<v8::UnboundScript>;
        {
            let scope = &mut v8::HandleScope::new(isolate);
            let context = v8::Context::new(scope, Default::default());
            let scope = &mut v8::ContextScope::new(scope, context);

            let x = v8::String::new(scope, "test string x").unwrap();
            global_x = v8::Global::new(scope, x);

            let code = "var y = 'test string y';";
            let script = compile(scope, code).unwrap();
            global_script = v8::Global::new(scope, script);

            script.run(scope).unwrap();
            let key = &[new_string(scope, "y").unwrap()];
            // Reading `y` works here because `Context` has not been dropped yet.
            assert_eq!(
                global_get(scope, key).unwrap().to_rust_string_lossy(scope),
                "test string y",
            );

            let code = "var z = 'test string z';";
            global_unbound_script = compile_g(scope, code).unwrap();
        }

        {
            let scope = &mut v8::HandleScope::new(isolate);
            let context = v8::Context::new(scope, Default::default());
            let scope = &mut v8::ContextScope::new(scope, context);

            let x = v8::Local::new(scope, global_x);
            assert_eq!(x.to_rust_string_lossy(scope), "test string x");

            let script = v8::Local::new(scope, global_script);
            script.run(scope).unwrap();
            let key = &[new_string(scope, "y").unwrap()];
            // Reading `y` results in `undefined` because `script` is bound to a dropped `Context`.
            assert!(global_get(scope, key).unwrap().is_undefined());

            run_g(scope, global_unbound_script).unwrap();
            let key = &[new_string(scope, "z").unwrap()];
            assert_eq!(
                global_get(scope, key).unwrap().to_rust_string_lossy(scope),
                "test string z",
            );
        }
    }

    #[test]
    fn hoisted_function_declaration() {
        init();

        let isolate = &mut v8::Isolate::new(Default::default());

        {
            let scope = &mut v8::HandleScope::new(isolate);
            let context = v8::Context::new(scope, Default::default());
            let scope = &mut v8::ContextScope::new(scope, context);

            let code = r#"
            var f = function() { return 'assigned'; };
            function f() { return 'declared'; }
            "#;
            run(scope, code).unwrap();

            assert_eq!(
                run(scope, "f()").unwrap().to_rust_string_lossy(scope),
                "assigned",
            );
        }

        {
            let scope = &mut v8::HandleScope::new(isolate);
            let context = v8::Context::new(scope, Default::default());
            let scope = &mut v8::ContextScope::new(scope, context);

            run(scope, "var f = function() { return 'assigned'; };").unwrap();
            run(scope, "function f() { return 'declared'; }").unwrap();

            assert_eq!(
                run(scope, "f()").unwrap().to_rust_string_lossy(scope),
                "declared",
            );
        }
    }
}
