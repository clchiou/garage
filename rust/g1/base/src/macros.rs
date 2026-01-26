// Include `->` in the macro to prevent `rustfmt` from altering the caller's code.
#[macro_export]
macro_rules! try_ {
    (-> $type:ty $code:block) => {{
        let __value: $type = try $code;
        __value
    }}
}

// "x" in the macro name denotes heterogeneity.
#[macro_export]
macro_rules! tryx {
    (-> $type:ty $code:block) => {
        try bikeshed $type $code
    };
}
