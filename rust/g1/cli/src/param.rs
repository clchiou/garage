use std::fmt::{self, Write};
use std::fs;

use clap::Args;

use g1_param::{self, Error, ParameterValues, Parameters};

#[derive(Args, Clone, Debug)]
pub struct ParametersConfig {
    #[arg(
        long,
        global = true,
        help = "Set a parameter value `name=value` or load values from a YAML file `@path`"
    )]
    parameter: Vec<String>,
}

impl ParametersConfig {
    pub fn render() -> String {
        Self::try_render().expect("parameter render error")
    }

    pub fn try_render() -> Result<String, fmt::Error> {
        // Sadly, we have no access to `clap::Command::get_styles` here for styling the output.
        let mut output = String::new();
        writeln!(&mut output, "Parameters:")?;
        for parameter in Parameters::load().iter() {
            writeln!(&mut output, "  {}", parameter.format_def_full())?;
        }
        Ok(output)
    }

    pub fn init(&self) {
        self.try_init().expect("parameter value loading error");
    }

    pub fn try_init(&self) -> Result<(), Error> {
        let mut parameters = Parameters::load();
        for path_or_value in &self.parameter {
            match path_or_value.strip_prefix('@') {
                Some(path) => {
                    let values = fs::read_to_string(path)?;
                    parameters.parse_values_then_set(ParameterValues::load(&values)?)?;
                }
                None => {
                    let (module_path, name, value) = g1_param::parse_assignment(path_or_value)?;
                    if !parameters.parse_then_set(module_path, name, value)? {
                        return Err(
                            format!("undefined parameter: {}::{}", module_path, name).into()
                        );
                    }
                }
            }
        }
        parameters.commit()
    }
}
