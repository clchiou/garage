use std::fs;
use std::path::PathBuf;

use clap::Parser;

use g1_param::{self, Error, ParameterValues, Parameters};

g1_param::define!(
    /// Greet Message
    greet: String = "Hello, world!".to_string()
);
g1_param::define!(x: u32 = 42; validate = |x: &u32| *x > 0; validate = is_even);

fn is_even(x: &u32) -> bool {
    *x % 2 == 0
}

#[derive(Debug, Parser)]
struct Cli {
    #[arg(long, value_name = "module_path::name=value")]
    set: Vec<String>,
    #[arg(long)]
    path: Vec<PathBuf>,
}

fn main() -> Result<(), Error> {
    let cli = Cli::parse();

    let mut parameters = Parameters::load();
    for parameter in parameters.iter() {
        println!("{}", parameter.format_def_full());
    }

    for assignment in cli.set.iter() {
        let (module_path, name, value) = g1_param::parse_assignment(assignment)?;
        if !parameters.parse_then_set(module_path, name, value)? {
            println!("parameter does not exist: {}::{}", module_path, name);
        }
    }
    for path in cli.path.iter() {
        let values = fs::read_to_string(path)?;
        parameters.parse_values_then_set(ParameterValues::load(&values)?)?;
    }
    parameters.commit()?;

    println!("greet == {}", greet());
    println!("x == {}", x());

    Ok(())
}
