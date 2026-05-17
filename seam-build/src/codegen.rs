use crate::schema::DeviceSchema;
use proc_macro2::Ident;
use quote::quote;
use std::process::Command;

/// Returns the byte size for a given TOML type string.
fn byte_size_for(ty: &str) -> usize {
    match ty {
        "u8" => 1,
        "u16" | "i16" => 2,
        "u32" | "i32" | "f32" => 4,
        "f32x3" => 12,
        "f32x6" => 24,
        _ => 0,
    }
}

/// Generates a token-stream expression that decodes `ty` from `args` at byte `offset`.
fn decode_expr_for(ty: &str, offset: usize) -> proc_macro2::TokenStream {
    match ty {
        "u8" => quote! { args[#offset] },
        "u16" => {
            let (a, b) = (offset, offset + 1);
            quote! { u16::from_le_bytes([args[#a], args[#b]]) }
        }
        "i16" => {
            let (a, b) = (offset, offset + 1);
            quote! { i16::from_le_bytes([args[#a], args[#b]]) }
        }
        "u32" => {
            let (a, b, c, d) = (offset, offset + 1, offset + 2, offset + 3);
            quote! { u32::from_le_bytes([args[#a], args[#b], args[#c], args[#d]]) }
        }
        "i32" => {
            let (a, b, c, d) = (offset, offset + 1, offset + 2, offset + 3);
            quote! { i32::from_le_bytes([args[#a], args[#b], args[#c], args[#d]]) }
        }
        "f32" => {
            let (a, b, c, d) = (offset, offset + 1, offset + 2, offset + 3);
            quote! { f32::from_le_bytes([args[#a], args[#b], args[#c], args[#d]]) }
        }
        "f32x3" => {
            let floats: Vec<proc_macro2::TokenStream> = (0..3)
                .map(|f| {
                    let (a, b, c, d) = (
                        offset + f * 4,
                        offset + f * 4 + 1,
                        offset + f * 4 + 2,
                        offset + f * 4 + 3,
                    );
                    quote! { f32::from_le_bytes([args[#a], args[#b], args[#c], args[#d]]) }
                })
                .collect();
            quote! { [#(#floats),*] }
        }
        "f32x6" => {
            let floats: Vec<proc_macro2::TokenStream> = (0..6)
                .map(|f| {
                    let (a, b, c, d) = (
                        offset + f * 4,
                        offset + f * 4 + 1,
                        offset + f * 4 + 2,
                        offset + f * 4 + 3,
                    );
                    quote! { f32::from_le_bytes([args[#a], args[#b], args[#c], args[#d]]) }
                })
                .collect();
            quote! { [#(#floats),*] }
        }
        _ => quote! { compile_error!("unknown type") },
    }
}

/// Maps a TOML type string to the corresponding Rust type string.
pub fn rust_type_for(toml_type: &str) -> &str {
    match toml_type {
        "u8" => "u8",
        "u16" => "u16",
        "u32" => "u32",
        "i16" => "i16",
        "i32" => "i32",
        "f32" => "f32",
        "f32x3" => "[f32; 3]",
        "f32x6" => "[f32; 6]",
        other => panic!("unknown toml type: {other}"),
    }
}

/// Converts `snake_case` to `PascalCase` for use as Rust enum variants.
pub fn snake_to_pascal(name: &str) -> String {
    name.split('_')
        .map(|part| {
            let mut chars = part.chars();
            match chars.next() {
                None => String::new(),
                Some(c) => c.to_uppercase().to_string() + chars.as_str(),
            }
        })
        .collect()
}

fn ident(name: &str) -> Ident {
    Ident::new(&snake_to_pascal(name), proc_macro2::Span::call_site())
}

/// Generates the complete Rust source string for the `Channel` and `Command`
/// enums plus their helper `impl` blocks.
pub fn generate(schema: &DeviceSchema) -> String {
    let channel_variants = schema.channels.iter().map(|ch| {
        let var = ident(&ch.name);
        let rust_ty: proc_macro2::TokenStream =
            rust_type_for(&ch.ty).parse().expect("invalid Rust type");
        quote! {
            #var { _phantom: core::marker::PhantomData<#rust_ty> }
        }
    });

    let channel_id_arms = schema.channels.iter().map(|ch| {
        let var = ident(&ch.name);
        let id = ch.id;
        quote! { Channel::#var { .. } => #id }
    });

    let channel_rate_arms = schema.channels.iter().map(|ch| {
        let var = ident(&ch.name);
        let rate = ch.rate_hz;
        quote! { Channel::#var { .. } => #rate }
    });

    let channel_size_arms = schema.channels.iter().map(|ch| {
        let var = ident(&ch.name);
        let rust_ty: proc_macro2::TokenStream =
            rust_type_for(&ch.ty).parse().expect("invalid Rust type");
        quote! { Channel::#var { .. } => core::mem::size_of::<#rust_ty>() }
    });

    // Duplicate iterators for ChannelInfo trait impl (iterators are consumed once)
    let trait_id_arms = schema.channels.iter().map(|ch| {
        let var = ident(&ch.name);
        let id = ch.id;
        quote! { Channel::#var { .. } => #id }
    });

    let trait_size_arms = schema.channels.iter().map(|ch| {
        let var = ident(&ch.name);
        let rust_ty: proc_macro2::TokenStream =
            rust_type_for(&ch.ty).parse().expect("invalid Rust type");
        quote! { Channel::#var { .. } => core::mem::size_of::<#rust_ty>() }
    });

    let channel_tokens = if schema.channels.is_empty() {
        quote! {
            #[derive(Copy, Clone, Debug, PartialEq, Eq)]
            pub enum Channel {}

            impl crate::channel_info::ChannelInfo for Channel {
                fn id(&self) -> u8 { match *self {} }
                fn payload_size(&self) -> usize { match *self {} }
            }
        }
    } else {
        quote! {
            #[derive(Copy, Clone, Debug, PartialEq, Eq)]
            pub enum Channel {
                #(#channel_variants),*
            }

            impl Channel {
                pub fn rate_hz(&self) -> u32 {
                    match self {
                        #(#channel_rate_arms),*
                    }
                }
            }

            impl crate::channel_info::ChannelInfo for Channel {
                fn id(&self) -> u8 {
                    match self {
                        #(#trait_id_arms),*
                    }
                }

                fn payload_size(&self) -> usize {
                    match self {
                        #(#trait_size_arms),*
                    }
                }
            }

            impl Channel {
                pub fn id(&self) -> u8 {
                    match self {
                        #(#channel_id_arms),*
                    }
                }

                pub fn payload_size(&self) -> usize {
                    match self {
                        #(#channel_size_arms),*
                    }
                }
            }
        }
    };

    let command_variants = schema.commands.iter().map(|cmd| {
        let var = ident(&cmd.name);
        if cmd.args.is_empty() {
            quote! { #var }
        } else {
            let fields: Vec<_> = cmd.args.iter().map(|arg| {
                let fname = Ident::new(&arg.name, proc_macro2::Span::call_site());
                let fty: proc_macro2::TokenStream =
                    rust_type_for(&arg.ty).parse().expect("invalid Rust type");
                quote! { #fname: #fty }
            }).collect();
            quote! { #var { #(#fields),* } }
        }
    });

    let command_id_arms = schema.commands.iter().map(|cmd| {
        let var = ident(&cmd.name);
        let id = cmd.id;
        if cmd.args.is_empty() {
            quote! { Command::#var => #id }
        } else {
            quote! { Command::#var { .. } => #id }
        }
    });

    let command_from_bytes_arms = schema.commands.iter().map(|cmd| {
        let var = ident(&cmd.name);
        let id = cmd.id;
        if cmd.args.is_empty() {
            quote! { #id => Some(Command::#var) }
        } else {
            let total_size: usize = cmd.args.iter().map(|a| byte_size_for(&a.ty)).sum();
            let mut offset = 0usize;
            let field_parses: Vec<_> = cmd.args.iter().map(|arg| {
                let fname = Ident::new(&arg.name, proc_macro2::Span::call_site());
                let expr = decode_expr_for(&arg.ty, offset);
                offset += byte_size_for(&arg.ty);
                quote! { #fname: #expr }
            }).collect();
            quote! {
                #id => {
                    if args.len() < #total_size {
                        return None;
                    }
                    Some(Command::#var { #(#field_parses),* })
                }
            }
        }
    });

    let command_tokens = if schema.commands.is_empty() {
        quote! {
            #[derive(Copy, Clone, Debug, PartialEq, Eq)]
            pub enum Command {}

            impl Command {
                pub fn from_bytes(_command_id: u8, _args: &[u8]) -> Option<Self> {
                    None
                }
            }
        }
    } else {
        quote! {
            #[derive(Copy, Clone, Debug, PartialEq, Eq)]
            pub enum Command {
                #(#command_variants),*
            }

            impl Command {
                pub fn id(&self) -> u8 {
                    match self {
                        #(#command_id_arms),*
                    }
                }

                pub fn from_bytes(command_id: u8, args: &[u8]) -> Option<Self> {
                    match command_id {
                        #(#command_from_bytes_arms,)*
                        _ => None,
                    }
                }
            }
        }
    };

    let full = quote! {
        #channel_tokens

        #command_tokens
    };

    let source = full.to_string();
    format_rustfmt(&source)
}

fn format_rustfmt(source: &str) -> String {
    match Command::new("rustfmt")
        .arg("--edition")
        .arg("2021")
        .stdin(std::process::Stdio::piped())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::null())
        .spawn()
    {
        Ok(mut child) => {
            use std::io::Write;
            if let Some(mut stdin) = child.stdin.take() {
                let _ = stdin.write_all(source.as_bytes());
            }
            if let Ok(output) = child.wait_with_output() {
                if output.status.success() {
                    if let Ok(formatted) = String::from_utf8(output.stdout) {
                        return formatted;
                    }
                }
            }
            source.to_string()
        }
        Err(_) => source.to_string(),
    }
}

// ── Tests ───────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use crate::schema::{ChannelDef, CommandArgDef, CommandDef};

    #[test]
    fn test_snake_to_pascal_simple() {
        assert_eq!(snake_to_pascal("accel"), "Accel");
    }

    #[test]
    fn test_snake_to_pascal_multi() {
        assert_eq!(snake_to_pascal("set_sample_rate"), "SetSampleRate");
    }

    #[test]
    fn test_rust_type_for_all() {
        assert_eq!(rust_type_for("u8"), "u8");
        assert_eq!(rust_type_for("u16"), "u16");
        assert_eq!(rust_type_for("u32"), "u32");
        assert_eq!(rust_type_for("i16"), "i16");
        assert_eq!(rust_type_for("i32"), "i32");
        assert_eq!(rust_type_for("f32"), "f32");
        assert_eq!(rust_type_for("f32x3"), "[f32; 3]");
        assert_eq!(rust_type_for("f32x6"), "[f32; 6]");
    }

    #[test]
    fn test_generate_with_channels_and_commands() {
        let schema = DeviceSchema {
            name: "test".into(),
            transport: "usb-cdc".into(),
            channels: vec![
                ChannelDef {
                    id: 1,
                    name: "accel".into(),
                    ty: "f32x3".into(),
                    rate_hz: 100,
                    unit: Some("g".into()),
                },
                ChannelDef {
                    id: 2,
                    name: "temperature".into(),
                    ty: "f32".into(),
                    rate_hz: 10,
                    unit: Some("celsius".into()),
                },
            ],
            commands: vec![
                CommandDef {
                    id: 1,
                    name: "set_rate".into(),
                    args: vec![CommandArgDef {
                        name: "hz".into(),
                        ty: "u16".into(),
                    }],
                },
                CommandDef {
                    id: 2,
                    name: "reset".into(),
                    args: vec![],
                },
            ],
        };

        let source = generate(&schema);
        assert!(source.contains("enum Channel"));
        assert!(source.contains("enum Command"));
        assert!(source.contains("Accel"));
        assert!(source.contains("Temperature"));
        assert!(source.contains("SetRate"));
        assert!(source.contains("Reset"));
        assert!(source.contains("pub fn id"));
        assert!(source.contains("pub fn rate_hz"));
    }

    #[test]
    fn test_generate_empty_schema() {
        let schema = DeviceSchema {
            name: "empty".into(),
            transport: "usb-cdc".into(),
            channels: vec![],
            commands: vec![],
        };

        let source = generate(&schema);
        assert!(source.contains("enum Channel"));
        assert!(source.contains("enum Command"));
    }
}
