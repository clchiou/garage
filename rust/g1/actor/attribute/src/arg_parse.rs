macro_rules! parse_args {
    ($name:ident { $($arg_name:ident),* $(,)? } = $args:expr) => {{
        $(let mut $arg_name = None;)*
        $crate::arg_parse::parse_args_from!({ $($arg_name: $arg_name),* } = $args);
        $name { $($arg_name: $crate::arg_parse::ArgUnwrap::unwrap($arg_name),)* }
    }};
}

macro_rules! parse_args_from {
    ({ $($arg_name:ident: $arg_var:expr),* $(,)? } = $args:expr) => {{
        for mut arg in $args {
            'parse: {
                $(arg = match self::$arg_name(&mut $arg_var, arg)? {
                    Some(arg) => arg,
                    None => break 'parse,
                };)*
                return Err(::syn::Error::new(arg.span(), "unknown argument"));
            }
        }
    }};
}

macro_rules! named_scalar_arg {
    (
        $vis:vis $arg_name:ident: $type:ty =
        $($pat:pat $(if $cond:expr)? => $output:expr),* $(,)?
    ) => {
        $vis fn $arg_name(
            output: &mut Option<$type>,
            arg: $crate::arg::Arg,
        ) -> Result<Option<$crate::arg::Arg>, ::syn::Error> {
            match arg.name() {
                Some(arg_name) if arg_name == stringify!($arg_name) => {
                    $crate::error::check_duplicated!(output, arg_name.span());
                    match arg {
                        $($pat $(if $cond)? => {
                            *output = Some($output);
                            Ok(None)
                        })+
                        _ => Err(::syn::Error::new(arg_name.span(), "invalid argument value")),
                    }
                }
                _ => Ok(Some(arg)),
            }
        }
    };
}

macro_rules! func_arg {
    ($vis:vis $arg_name:ident: $type:ty) => {
        $crate::arg_parse::named_scalar_arg! {
            $vis $arg_name: $type =
            $crate::arg::Arg::Call(_, args) => args.try_into()?,
        }
    };
}

macro_rules! named_vec_arg {
    ($vis:vis $arg_name:ident = $item_name:ident: $item_type:ty) => {
        $vis fn $arg_name(
            output: &mut Option<Vec<$item_type>>,
            arg: $crate::arg::Arg,
        ) -> Result<Option<$crate::arg::Arg>, ::syn::Error> {
            let mut item = None;
            self::$item_name(&mut item, arg).inspect(|match_result| {
                if match_result.is_none() {
                    output.get_or_insert_default().push(item.expect("item"));
                }
            })
        }
    };
}

macro_rules! scalar_arg {
    (
        $vis:vis $arg_name:ident: $type:ty =
        $($pat:pat $(if $cond:expr)? => ($span:expr, $output:expr $(,)?)),* $(,)?
    ) => {
        $vis fn $arg_name(
            output: &mut Option<$type>,
            arg: $crate::arg::Arg,
        ) -> Result<Option<$crate::arg::Arg>, ::syn::Error> {
            match arg {
                $($pat $(if $cond)? => {
                    $crate::error::check_duplicated!(output, $span);
                    *output = Some($output);
                    Ok(None)
                })+
                _ => Ok(Some(arg)),
            }
        }
    };
}

// As of now, `macro_export` cannot be used in a `proc-macro` crate.
pub(crate) use func_arg;
pub(crate) use named_scalar_arg;
pub(crate) use named_vec_arg;
pub(crate) use parse_args;
pub(crate) use parse_args_from;
pub(crate) use scalar_arg;

pub(crate) trait ArgUnwrap<Argv> {
    fn unwrap(argv: Option<Argv>) -> Self;
}

impl<T> ArgUnwrap<T> for Option<T> {
    fn unwrap(argv: Option<T>) -> Self {
        argv
    }
}

impl<T: Default> ArgUnwrap<T> for T {
    fn unwrap(argv: Option<T>) -> Self {
        argv.unwrap_or_default()
    }
}
