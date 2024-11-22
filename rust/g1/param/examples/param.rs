use std::fs;
use std::net::SocketAddr;
use std::path::PathBuf;
use std::time::Duration;

use clap::Parser;

use g1_param::{self, Error, ParameterValues, Parameters};

g1_param::define!(
    /// Greet Message
    greet: String = "Hello, world!".to_string()
);
g1_param::define!(x: u32 = 42; validate = |x: &u32| *x > 0; validate = is_even);
g1_param::define!(d: Option<Duration> = None; parse = g1_param::parse::opt_duration);
g1_param::define!(n: Option<SocketAddr> = None);

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
        parameters.parse_then_set(module_path, name, value)?;
    }
    for path in cli.path.iter() {
        let values = fs::read_to_string(path)?;
        parameters.parse_values_then_set(ParameterValues::load(&values)?)?;
    }
    parameters.commit()?;

    println!("greet == {}", greet());
    println!("x == {}", x());
    println!("d == {:?}", d());
    println!("n == {:?}", n());

    Ok(())
}
