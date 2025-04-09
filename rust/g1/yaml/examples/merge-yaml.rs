use std::env;
use std::fs;

use serde_yaml::Value;

use g1_yaml::tree::Tree;

fn main() {
    let mut tree = Tree::new();
    for path in env::args().skip(1) {
        let data = fs::read_to_string(path).unwrap();
        let data = serde_yaml::from_str::<Value>(&data).unwrap();
        let data = Tree::try_from(data).unwrap();
        tree.merge_from(data).unwrap();
    }
    print!("{}", serde_yaml::to_string(&Value::from(tree)).unwrap());
}
