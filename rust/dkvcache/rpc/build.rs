use capnpc::CompilerCommand;

fn main() {
    // TODO: For now, we simply symlink to the schema directory, which is much easier than parsing
    // the metadata table of the Cargo manifest file.
    CompilerCommand::new()
        .import_path("schema")
        .src_prefix("schema")
        .file("schema/dkvcache/rpc.capnp")
        .run()
        .expect("capnp compile");
}
