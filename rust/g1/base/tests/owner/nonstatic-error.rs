struct Struct<'a>(&'a [u8]);

impl<'a> TryFrom<&'a [u8]> for Struct<'a> {
    type Error = &'a [u8];

    fn try_from(_: &'a [u8]) -> Result<Self, Self::Error> {
        std::unreachable!()
    }
}

g1_base::define_owner!(Owner for Struct);

fn main() {
    Owner::try_from(Vec::new()).unwrap();
}
