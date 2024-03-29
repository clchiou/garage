use std::fs;
use std::io::{self, Write};
use std::process;

use clap::Args;

use g1_param::{self, Error, ParameterValues, Parameters};

#[derive(Args, Clone, Debug)]
pub struct ParametersConfig {
    #[arg(
        long,
        global = true,
        help = "Set a parameter value or load values from a JSON file"
    )]
    parameter: Vec<String>,

    #[arg(long, global = true, help = "Print parameter definitions and exit")]
    parameter_help: bool,
}

impl ParametersConfig {
    pub fn init(&self) {
        self.try_init().expect("parameter value loading error");
    }

    pub fn try_init(&self) -> Result<(), Error> {
        if self.parameter_help {
            for parameter in Parameters::load().iter() {
                println!("{}", parameter.format_def_full());
            }
            safe_exit(0);
        }

        let mut parameters = Parameters::load();
        for path_or_value in &self.parameter {
            if let Some(path) = path_or_value.strip_prefix('@') {
                let values = fs::read_to_string(path)?;
                parameters.parse_values_then_set(ParameterValues::load(&values)?)?;
            } else {
                let (module_path, name, value) = g1_param::parse_assignment(path_or_value)?;
                if !parameters.parse_then_set(module_path, name, value)? {
                    return Err(format!("undefined parameter: {}::{}", module_path, name).into());
                }
            }
        }
        parameters.commit()
    }
}

fn safe_exit(code: i32) -> ! {
    let _ = io::stdout().flush();
    let _ = io::stderr().flush();
    process::exit(code)
}
