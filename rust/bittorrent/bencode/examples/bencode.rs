use std::error;
use std::io::{self, Read};

use bittorrent_bencode::borrow::Value;

fn main() -> Result<(), Box<dyn error::Error>> {
    let mut input = Vec::new();
    io::stdin().read_to_end(&mut input)?;
    println!("{:#?}", Value::try_from(&*input)?);
    Ok(())
}
