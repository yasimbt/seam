pub mod codegen;
pub mod schema;

use std::env;
use std::fs;
use std::path::Path;

/// Reads a `seam.toml` file, validates it, generates Rust source code,
/// and writes it to `$OUT_DIR/seam_generated.rs`.
///
/// This function is intended to be called from a `build.rs` script.
pub fn generate(path: &str) {
    let schema = schema::parse(path).expect("failed to parse seam.toml");
    let source = codegen::generate(&schema);

    let out_dir = env::var("OUT_DIR").expect("OUT_DIR not set");
    let dest = Path::new(&out_dir).join("seam_generated.rs");
    fs::write(&dest, source).expect("failed to write generated file");
}
