//! Static Parameter

use std::any::Any;
use std::collections::{BTreeMap, HashMap};
use std::error;
use std::fmt;
use std::sync::Once;

use serde::Deserialize;
use serde_json::value::RawValue;

//
// Implementer's notes: The `Parameter` type must not be generic, and therefore everything about
// the concrete parameter type has to be encapsulated in the `define!` macro body.  The `Parameter`
// type and the `define!` macro body interact with each other via a set of callback functions.
// Sadly, this restriction makes the code look convoluted.
//

#[macro_export]
macro_rules! define {
    ($v:vis $name:ident: $type:ty = $default:expr $(; validate = $validate:expr)* $(;)?) => {
        $v fn $name() -> &'static $type {
            #[::linkme::distributed_slice($crate::PARAMETERS)]
            static PARAMETER: $crate::Parameter = $crate::Parameter::new(
                ::std::module_path!(),
                ::std::stringify!($name),
                ::std::stringify!($type),
                ::std::stringify!($default),
                parse,
                validate,
                set,
                load_default,
            );
            static mut PARAMETER_VALUE: ::std::option::Option<$type> = ::std::option::Option::None;

            fn parse(value: &str) -> ::std::result::Result<
                ::std::boxed::Box<dyn ::std::any::Any>,
                ::std::boxed::Box<dyn ::std::error::Error>,
            > {
                PARAMETER.parse_then_upcast::<$type>(value)
            }

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

            unsafe fn set(value: ::std::boxed::Box<dyn ::std::any::Any>) {
                ::std::assert!(PARAMETER_VALUE.is_none());
                PARAMETER_VALUE =
                    ::std::option::Option::Some(PARAMETER.downcast::<$type>(value).unwrap());
            }

            unsafe fn load_default() {
                ::std::assert!(PARAMETER_VALUE.is_none());
                PARAMETER_VALUE = ::std::option::Option::Some($default);
            }

            PARAMETER.load_default_if_unset();
            unsafe {
                PARAMETER_VALUE.as_ref().unwrap()
            }
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

    init_once: Once,

    // Callback functions.
    parse: ParseFn,
    validate: ValidateFn,
    set: SetFn,
    load_default: LoadDefaultFn,
}

pub type Value = Box<dyn Any>;
pub type Error = Box<dyn error::Error>;

pub type ParseFn = fn(value: &str) -> Result<Value, Error>;
pub type ValidateFn = fn(value: &Value) -> Result<(), Error>;
pub type SetFn = unsafe fn(value: Value);
pub type LoadDefaultFn = unsafe fn();

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
pub struct ParameterValues<'a>(#[serde(borrow)] HashMap<&'a str, HashMap<&'a str, &'a RawValue>>);

// This `impl` block contains all the methods of `Parameter` that are called by the `define!` macro
// body.  Since the `define!` macro can be invoked in any module, these methods need to be `pub`.
impl Parameter {
    #[allow(clippy::too_many_arguments)]
    pub const fn new(
        module_path: &'static str,
        name: &'static str,
        type_name: &'static str,
        default: &'static str,
        parse: ParseFn,
        validate: ValidateFn,
        set: SetFn,
        load_default: LoadDefaultFn,
    ) -> Self {
        Self {
            module_path,
            name,
            type_name,
            default,
            init_once: Once::new(),
            parse,
            validate,
            set,
            load_default,
        }
    }

    /// Parses the value and then upcasts it to the `Value` type.
    pub fn parse_then_upcast<'a, T>(&self, value: &'a str) -> Result<Value, Error>
    where
        T: Deserialize<'a> + 'static,
    {
        Ok(Box::new(serde_json::from_str::<T>(value)?))
    }

    /// Stores the default parameter value statically if no value was stored.
    pub fn load_default_if_unset(&self) {
        self.init_once.call_once(|| unsafe {
            (self.load_default)();
        });
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
    fn parse(&self, value: &str) -> Result<Value, Error> {
        (self.parse)(value)
    }

    fn validate(&self, value: &Value) -> Result<(), Error> {
        (self.validate)(value)
    }

    /// Stores the parameter value statically.
    ///
    /// It is an error to call this method multiple times.
    fn set(&self, value: Value) -> Result<(), Error> {
        let mut initialized = false;
        unsafe {
            self.init_once.call_once(|| {
                (self.set)(value);
                initialized = true;
            });
        }
        if initialized {
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
                self.parse_then_set(module_path, name, value.get())?;
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
        self.set_with(module_path, name, |parameter| parameter.parse(value))
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
        Ok(serde_json::from_str(values)?)
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
