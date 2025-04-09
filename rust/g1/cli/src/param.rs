use std::fmt::{self, Write};
use std::fs;
use std::path::Path;

use clap::Args;

use serde_yaml::Value;

use g1_param::{self, Error, ParameterValues, Parameters};
use g1_yaml::tree::Tree;

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

    // NOTE: Due to implementation challenges, we introduce a (minor) backward compatibility break.
    // Rather than applying parameter values and parameter files serially, we now apply them in two
    // separate groups.
    pub fn try_init(&self) -> Result<(), Error> {
        fn is_yaml(path: &Path) -> bool {
            path.extension()
                .map_or(false, |ext| ext == "yaml" || ext == "yml")
        }

        fn load<P>(path: P) -> Result<Tree, Error>
        where
            P: AsRef<Path>,
        {
            tracing::info!(path = %path.as_ref().display(), "load");
            Ok(serde_yaml::from_str::<Value>(&fs::read_to_string(path)?)?.try_into()?)
        }

        let mut tree = Tree::new();
        let mut values = Vec::new();
        for path_or_value in &self.parameter {
            match path_or_value.strip_prefix('@').map(Path::new) {
                Some(path) => {
                    if path.is_dir() {
                        let mut paths = fs::read_dir(path)?
                            .map(|entry| Ok::<_, Error>(entry?.path()))
                            .try_collect::<Vec<_>>()?;
                        paths.sort();
                        for path in paths {
                            // For now, we do not recurse into nested directories.
                            if path.is_dir() || !is_yaml(&path) {
                                tracing::info!(path = %path.display(), "skip");
                            } else {
                                tree.merge_from(load(path)?)?;
                            }
                        }
                    } else {
                        tree.merge_from(load(path)?)?;
                    }
                }
                None => values.push(path_or_value),
            }
        }

        let mut parameters = Parameters::load();
        parameters.parse_values_then_set(ParameterValues::try_from(tree)?)?;
        // It seems more intuitive for parameter values from the command line to take precedence
        // over those from files.
        for value in values {
            let (module_path, name, value) = g1_param::parse_assignment(value)?;
            parameters.parse_then_set(module_path, name, value)?;
        }
        parameters.commit()
    }
}
