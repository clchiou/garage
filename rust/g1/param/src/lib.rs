//! Static Parameter

pub mod parse;

use std::any::Any;
use std::collections::{BTreeMap, HashMap};
use std::error;
use std::fmt;

use serde::de::DeserializeOwned;
use serde::Deserialize;

//
// Implementer's notes: The `Parameter` type must not be generic, and therefore everything about
// the concrete parameter type has to be encapsulated in the `define!` macro body.  The `Parameter`
// type and the `define!` macro body interact with each other via a set of callback functions.
// Sadly, this restriction makes the code look convoluted.
//

#[macro_export]
macro_rules! define {
    (
        $(#[$meta:meta])* $v:vis $name:ident: $type:ty = $default:expr
        $(; parse = $parse:expr)?
        $(; validate = $validate:expr)* $(;)?
    ) => {
        $(#[$meta])*
        $v fn $name() -> &'static $type {
            #[::linkme::distributed_slice($crate::PARAMETERS)]
            static PARAMETER: $crate::Parameter = $crate::Parameter::new(
                ::std::module_path!(),
                ::std::stringify!($name),
                ::std::stringify!($type),
                ::std::stringify!($default),
                parse_str,
                parse_raw,
                validate,
                set,
            );

            static PARAMETER_VALUE: ::std::sync::OnceLock<$type> = ::std::sync::OnceLock::new();

            $crate::define!(@parse_str $type, $($parse),*);

            $crate::define!(@parse_raw $type, $($parse),*);

            fn validate(
                value: &::std::boxed::Box<dyn ::std::any::Any>,
            ) -> ::std::result::Result<(), ::std::boxed::Box<dyn ::std::error::Error>> {
                let value_ref = PARAMETER.downcast_ref::<$type>(&value)?;
                $(
                    if !($validate)(value_ref) {
                        return ::std::result::Result::Err(
                            ::std::format!(
                                "invalid parameter value: {}::{} value={:?}",
                                PARAMETER.module_path,
                                PARAMETER.name,
                                value_ref,
                            ).into(),
                        );
                    }
                )*
                ::std::result::Result::Ok(())
            }

            fn set(value: ::std::boxed::Box<dyn ::std::any::Any>) -> bool {
                PARAMETER_VALUE.set(PARAMETER.downcast::<$type>(value).unwrap()).is_ok()
            }

            PARAMETER_VALUE.get_or_init(|| $default)
        }
    };

    (@parse_str $type:ty $(,)?) => {
        $crate::define!(@parse_str $type, |x: $type| ::std::result::Result::Ok(x))
    };

    (@parse_str $type:ty, $parse:expr $(,)?) => {
        fn parse_str(value: &str) -> ::std::result::Result<
            ::std::boxed::Box<dyn ::std::any::Any>,
            ::std::boxed::Box<dyn ::std::error::Error>,
        > {
            PARAMETER.parse_str_then_upcast::<$type, _, _>($parse, value)
        }
    };

    (@parse_raw $type:ty $(,)?) => {
        $crate::define!(@parse_raw $type, |x: $type| ::std::result::Result::Ok(x))
    };

    (@parse_raw $type:ty, $parse:expr $(,)?) => {
        fn parse_raw(value: $crate::RawValue) -> ::std::result::Result<
            ::std::boxed::Box<dyn ::std::any::Any>,
            ::std::boxed::Box<dyn ::std::error::Error>,
        > {
            PARAMETER.parse_raw_then_upcast::<$type, _, _>($parse, value)
        }
    };
}

#[linkme::distributed_slice]
pub static PARAMETERS: [Parameter] = [..];

#[derive(Debug)]
pub struct Parameter {
    pub module_path: &'static str,
    pub name: &'static str,
    type_name: &'static str,
    default: &'static str,

    // Callback functions.
    parse_str: ParseStrFn,
    parse_raw: ParseRawFn,
    validate: ValidateFn,
    set: SetFn,
}

pub type Value = Box<dyn Any>;
pub type Error = Box<dyn error::Error>;

pub type ParseStrFn = fn(value: &str) -> Result<Value, Error>;
pub type ParseRawFn = fn(value: RawValue) -> Result<Value, Error>;
pub type ValidateFn = fn(value: &Value) -> Result<(), Error>;
pub type SetFn = fn(value: Value) -> bool;

pub use serde_yaml::Value as RawValue;

#[derive(Debug)]
pub struct FormatDefFull<'a>(&'a Parameter);

#[derive(Debug)]
pub struct FormatDef<'a>(&'a Parameter);

#[derive(Debug)]
pub struct Parameters<'a> {
    // Use `BTreeMap` so that the result of `iter` is deterministic.
    parameters: BTreeMap<(&'static str, &'static str), &'a Parameter>,
    values: HashMap<(&'static str, &'static str), Value>,
}

#[derive(Debug, Deserialize)]
pub struct ParameterValues<'a>(#[serde(borrow)] HashMap<&'a str, HashMap<&'a str, RawValue>>);

// This `impl` block contains all the methods of `Parameter` that are called by the `define!` macro
// body.  Since the `define!` macro can be invoked in any module, these methods need to be `pub`.
impl Parameter {
    #[allow(clippy::too_many_arguments)]
    pub const fn new(
        module_path: &'static str,
        name: &'static str,
        type_name: &'static str,
        default: &'static str,
        parse_str: ParseStrFn,
        parse_raw: ParseRawFn,
        validate: ValidateFn,
        set: SetFn,
    ) -> Self {
        Self {
            module_path,
            name,
            type_name,
            default,
            parse_str,
            parse_raw,
            validate,
            set,
        }
    }

    /// Parses the value and then upcasts it to the `Value` type.
    pub fn parse_str_then_upcast<'a, T, U, F>(
        &self,
        parse: F,
        value: &'a str,
    ) -> Result<Value, Error>
    where
        T: 'static,
        U: Deserialize<'a>,
        F: Fn(U) -> Result<T, Error>,
    {
        Ok(Box::new(parse(serde_yaml::from_str::<U>(value)?)?))
    }

    pub fn parse_raw_then_upcast<T, U, F>(&self, parse: F, value: RawValue) -> Result<Value, Error>
    where
        T: 'static,
        U: DeserializeOwned,
        F: Fn(U) -> Result<T, Error>,
    {
        Ok(Box::new(parse(serde_yaml::from_value::<U>(value)?)?))
    }

    /// Downcasts a parameter value.
    pub fn downcast<T: 'static>(&self, value: Value) -> Result<T, Error> {
        match value.downcast::<T>() {
            Ok(value) => Ok(*value),
            Err(_) => Err(self.make_downcast_error()),
        }
    }

    /// Downcasts a parameter reference.
    pub fn downcast_ref<'a, T: 'static>(&self, value: &'a Value) -> Result<&'a T, Error> {
        value
            .downcast_ref::<T>()
            .ok_or_else(move || self.make_downcast_error())
    }

    fn make_downcast_error(&self) -> Error {
        format!(
            "parameter cannot be downcasted: {}::{} type={}",
            self.module_path, self.name, self.type_name,
        )
        .into()
    }
}

// This `impl` block contains methods of `Parameter` that are called by the `Parameters`.
impl Parameter {
    fn parse_str(&self, value: &str) -> Result<Value, Error> {
        (self.parse_str)(value)
    }

    fn parse_raw(&self, value: RawValue) -> Result<Value, Error> {
        (self.parse_raw)(value)
    }

    fn validate(&self, value: &Value) -> Result<(), Error> {
        (self.validate)(value)
    }

    /// Stores the parameter value statically.
    ///
    /// It is an error to call this method multiple times.
    fn set(&self, value: Value) -> Result<(), Error> {
        if (self.set)(value) {
            Ok(())
        } else {
            Err(self.make_set_error())
        }
    }

    fn make_set_error(&self) -> Error {
        format!(
            "parameter has been set or loaded with its default value: {}::{}",
            self.module_path, self.name,
        )
        .into()
    }
}

impl Parameter {
    pub fn format_def_full(&self) -> FormatDefFull {
        FormatDefFull(self)
    }

    pub fn format_def(&self) -> FormatDef {
        FormatDef(self)
    }
}

impl<'a> fmt::Display for FormatDefFull<'a> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "{}::{}: {} = {}",
            self.0.module_path, self.0.name, self.0.type_name, self.0.default
        )
    }
}

impl<'a> fmt::Display for FormatDef<'a> {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "{}: {} = {}",
            self.0.name, self.0.type_name, self.0.default
        )
    }
}

impl Parameters<'static> {
    pub fn load() -> Self {
        Self::new(&PARAMETERS)
    }
}

impl<'a> Parameters<'a> {
    fn new(parameters: &'a [Parameter]) -> Self {
        let mut map = BTreeMap::new();
        for parameter in parameters {
            assert!(
                map.insert((parameter.module_path, parameter.name), parameter)
                    .is_none(),
                "duplicated parameter: {}::{}",
                parameter.module_path,
                parameter.name,
            );
        }
        Self {
            parameters: map,
            values: HashMap::new(),
        }
    }

    pub fn iter(&self) -> impl Iterator<Item = &Parameter> {
        self.parameters.values().copied()
    }

    /// Parses values and stores them temporarily in the `Parameters`.
    pub fn parse_values_then_set(&mut self, values: ParameterValues) -> Result<(), Error> {
        for (module_path, module_values) in values.0 {
            for (name, value) in module_values {
                self.set_with(module_path, name, |parameter| parameter.parse_raw(value))?;
            }
        }
        Ok(())
    }

    /// Parses the value and stores it temporarily in the `Parameters`.
    pub fn parse_then_set(
        &mut self,
        module_path: &str,
        name: &str,
        value: &str,
    ) -> Result<bool, Error> {
        self.set_with(module_path, name, |parameter| parameter.parse_str(value))
    }

    /// Stores the parameter value temporarily in the `Parameters`.
    pub fn set(&mut self, module_path: &str, name: &str, value: Value) -> Result<bool, Error> {
        self.set_with(module_path, name, |_| Ok(value))
    }

    fn set_with<F>(&mut self, module_path: &str, name: &str, get_value: F) -> Result<bool, Error>
    where
        F: FnOnce(&Parameter) -> Result<Value, Error>,
    {
        match self.parameters.get(&(module_path, name)) {
            Some(parameter) => {
                let value = get_value(parameter)?;
                parameter.validate(&value)?;
                self.values
                    .insert((parameter.module_path, parameter.name), value);
                Ok(true)
            }
            None => Ok(false),
        }
    }

    /// Commits all temporary values, storing them statically.
    ///
    /// It is an error to call this method multiple times.
    pub fn commit(&mut self) -> Result<(), Error> {
        for ((module_path, name), value) in self.values.drain() {
            self.parameters
                .get(&(module_path, name))
                .ok_or_else(|| format!("parameter was not defined: {}::{}", module_path, name))?
                .set(value)?;
        }
        Ok(())
    }
}

impl<'a> ParameterValues<'a> {
    pub fn load(values: &'a str) -> Result<Self, Error> {
        Ok(serde_yaml::from_str(values)?)
    }
}

/// Parses an assignment of the form "module_path::name=value".
pub fn parse_assignment(assignment: &str) -> Result<(&str, &str, &str), Error> {
    let error = || {
        format!(
            "expect assignment of the form \"module_path::name=value\": {}",
            assignment,
        )
    };
    let (path, value) = assignment.rsplit_once('=').ok_or_else(error)?;
    let (module_path, name) = path.rsplit_once("::").ok_or_else(error)?;
    Ok((module_path, name, value))
}
