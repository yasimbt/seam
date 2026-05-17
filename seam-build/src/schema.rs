use serde::Deserialize;
use std::collections::HashSet;
use std::fs;

/// All valid channel / command argument types recognised by the wire protocol.
pub const VALID_TYPES: &[&str] = &["u8", "u16", "u32", "i16", "i32", "f32", "f32x3", "f32x6"];

/// All valid transport strings.
pub const VALID_TRANSPORTS: &[&str] = &["usb-cdc", "ble-nus"];

// ── Deserialisable raw TOML shapes ──────────────────────────────────────────

#[derive(Deserialize)]
struct RawDevice {
    name: Option<String>,
    transport: Option<String>,
}

#[derive(Deserialize)]
struct RawChannel {
    id: Option<u8>,
    name: Option<String>,
    #[serde(rename = "type")]
    ty: Option<String>,
    rate_hz: Option<u32>,
    unit: Option<String>,
}

#[derive(Deserialize, Clone)]
struct RawCommandArg {
    name: Option<String>,
    #[serde(rename = "type")]
    ty: Option<String>,
}

#[derive(Deserialize)]
struct RawCommand {
    id: Option<u8>,
    name: Option<String>,
    args: Option<Vec<RawCommandArg>>,
}

#[derive(Deserialize)]
struct RawSchema {
    device: Option<RawDevice>,
    channel: Option<Vec<RawChannel>>,
    command: Option<Vec<RawCommand>>,
}

// ── Public typed schema ─────────────────────────────────────────────────────

/// The fully validated schema derived from a `seam.toml` file.
#[derive(Debug)]
pub struct DeviceSchema {
    pub name: String,
    pub transport: String,
    pub channels: Vec<ChannelDef>,
    pub commands: Vec<CommandDef>,
}

/// A single channel definition from `[[channel]]`.
#[derive(Debug)]
pub struct ChannelDef {
    pub id: u8,
    pub name: String,
    pub ty: String,
    pub rate_hz: u32,
    pub unit: Option<String>,
}

/// A single command definition from `[[command]]`.
#[derive(Debug)]
pub struct CommandDef {
    pub id: u8,
    pub name: String,
    pub args: Vec<CommandArgDef>,
}

/// A single typed argument inside a `[[command]]`.
#[derive(Debug)]
pub struct CommandArgDef {
    pub name: String,
    pub ty: String,
}

// ── Validation helpers ──────────────────────────────────────────────────────

fn is_valid_name(name: &str) -> Result<(), String> {
    if name.is_empty() {
        return Err("name must not be empty".into());
    }
    if name.chars().next().is_some_and(|c| c.is_ascii_digit()) {
        return Err(format!("name '{name}' must not start with a digit"));
    }
    for c in name.chars() {
        if !c.is_ascii_lowercase() && c != '_' && !c.is_ascii_digit() {
            return Err(format!(
                "name '{name}' contains invalid character '{c}' — only lowercase ASCII, digits, and underscores allowed"
            ));
        }
    }
    Ok(())
}

// ── Public API ──────────────────────────────────────────────────────────────

/// Reads a TOML file at `path`, validates every rule from CLAUDE.md, and
/// returns a typed `DeviceSchema`.
pub fn parse(path: &str) -> Result<DeviceSchema, String> {
    let contents = fs::read_to_string(path)
        .map_err(|e| format!("could not read '{path}': {e}"))?;

    let raw: RawSchema = toml::from_str(&contents)
        .map_err(|e| format!("TOML parse error: {e}"))?;

    // ── [device] ────────────────────────────────────────────────────────
    let dev = raw.device.ok_or("[device] section is missing")?;
    let name = dev.name.ok_or("[device] name is required")?;
    let transport = dev.transport.ok_or("[device] transport is required")?;

    if !VALID_TRANSPORTS.contains(&transport.as_str()) {
        return Err(format!(
            "transport '{transport}' is not valid — must be one of {VALID_TRANSPORTS:?}"
        ));
    }

    // ── [[channel]] ─────────────────────────────────────────────────────
    let raw_channels = raw.channel.unwrap_or_default();
    let mut channels = Vec::with_capacity(raw_channels.len());
    let mut seen_channel_ids = HashSet::new();

    for (idx, rc) in raw_channels.iter().enumerate() {
        let id = rc.id.ok_or(format!("channel[{idx}]: id is required"))?;
        let cname = rc.name.clone().ok_or(format!("channel[{idx}]: name is required"))?;
        let ty = rc.ty.clone().ok_or(format!("channel[{idx}]: type is required"))?;
        let rate_hz = rc.rate_hz.ok_or(format!("channel[{idx}]: rate_hz is required"))?;

        if !seen_channel_ids.insert(id) {
            return Err(format!("channel id {id} is duplicated — channel ids must be unique"));
        }

        is_valid_name(&cname)?;

        if !VALID_TYPES.contains(&ty.as_str()) {
            return Err(format!(
                "channel '{cname}': type '{ty}' is not valid — must be one of {VALID_TYPES:?}"
            ));
        }

        channels.push(ChannelDef {
            id,
            name: cname,
            ty,
            rate_hz,
            unit: rc.unit.clone(),
        });
    }

    // ── [[command]] ─────────────────────────────────────────────────────
    let raw_commands = raw.command.unwrap_or_default();
    let mut commands = Vec::with_capacity(raw_commands.len());
    let mut seen_command_ids = HashSet::new();

    for (idx, rcmd) in raw_commands.iter().enumerate() {
        let id = rcmd.id.ok_or(format!("command[{idx}]: id is required"))?;
        let cmd_name = rcmd.name.clone().ok_or(format!("command[{idx}]: name is required"))?;

        if !seen_command_ids.insert(id) {
            return Err(format!("command id {id} is duplicated — command ids must be unique"));
        }

        is_valid_name(&cmd_name)?;

        let args = rcmd.args.clone().unwrap_or_default();
        let mut typed_args = Vec::with_capacity(args.len());
        for (aidx, arg) in args.iter().enumerate() {
            let aname = arg.name.clone().ok_or(format!(
                "command '{cmd_name}': args[{aidx}]: name is required"
            ))?;
            let aty = arg.ty.clone().ok_or(format!(
                "command '{cmd_name}': args[{aidx}]: type is required"
            ))?;

            if !VALID_TYPES.contains(&aty.as_str()) {
                return Err(format!(
                    "command '{cmd_name}': arg '{aname}' type '{aty}' is not valid — must be one of {VALID_TYPES:?}"
                ));
            }

            is_valid_name(&aname)?;

            typed_args.push(CommandArgDef {
                name: aname,
                ty: aty,
            });
        }

        commands.push(CommandDef {
            id,
            name: cmd_name,
            args: typed_args,
        });
    }

    Ok(DeviceSchema {
        name,
        transport,
        channels,
        commands,
    })
}

// ── Tests ───────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    fn write_temp_toml(contents: &str) -> String {
        use std::sync::atomic::{AtomicU64, Ordering};
        static COUNTER: AtomicU64 = AtomicU64::new(0);
        let n = COUNTER.fetch_add(1, Ordering::SeqCst);
        let dir = std::env::temp_dir();
        let path = dir.join(format!("seam_test_{}_{}.toml", std::process::id(), n));
        let mut f = fs::File::create(&path).unwrap();
        f.write_all(contents.as_bytes()).unwrap();
        path.to_string_lossy().to_string()
    }

    #[test]
    fn test_valid_toml_parses() {
        let toml = r#"
[device]
name = "my-node"
transport = "usb-cdc"

[[channel]]
id = 1
name = "accel"
type = "f32x3"
rate_hz = 100
unit = "g"

[[command]]
id = 1
name = "set_rate"
args = [{ name = "hz", type = "u16" }]
"#;
        let path = write_temp_toml(toml);
        let schema = parse(&path).unwrap();
        assert_eq!(schema.name, "my-node");
        assert_eq!(schema.transport, "usb-cdc");
        assert_eq!(schema.channels.len(), 1);
        assert_eq!(schema.channels[0].name, "accel");
        assert_eq!(schema.commands.len(), 1);
        assert_eq!(schema.commands[0].name, "set_rate");
        assert_eq!(schema.commands[0].args[0].name, "hz");
    }

    #[test]
    fn test_duplicate_channel_id_rejected() {
        let toml = r#"
[device]
name = "dup-node"
transport = "ble-nus"

[[channel]]
id = 1
name = "accel"
type = "f32x3"
rate_hz = 100

[[channel]]
id = 1
name = "temp"
type = "f32"
rate_hz = 10
"#;
        let path = write_temp_toml(toml);
        let err = parse(&path).unwrap_err();
        assert!(err.contains("duplicated"), "unexpected error: {err}");
    }

    #[test]
    fn test_invalid_type_rejected() {
        let toml = r#"
[device]
name = "bad-type"
transport = "usb-cdc"

[[channel]]
id = 1
name = "weird"
type = "f64"
rate_hz = 10
"#;
        let path = write_temp_toml(toml);
        let err = parse(&path).unwrap_err();
        assert!(err.contains("not valid"), "unexpected error: {err}");
    }

    #[test]
    fn test_invalid_transport_rejected() {
        let toml = r#"
[device]
name = "bad-transport"
transport = "spi"

[[channel]]
id = 1
name = "accel"
type = "f32x3"
rate_hz = 100
"#;
        let path = write_temp_toml(toml);
        let err = parse(&path).unwrap_err();
        assert!(err.contains("not valid"), "unexpected error: {err}");
    }

    #[test]
    fn test_leading_digit_name_rejected() {
        let toml = r#"
[device]
name = "digit-node"
transport = "usb-cdc"

[[channel]]
id = 1
name = "1accel"
type = "f32x3"
rate_hz = 100
"#;
        let path = write_temp_toml(toml);
        let err = parse(&path).unwrap_err();
        assert!(err.contains("digit"), "unexpected error: {err}");
    }

    #[test]
    fn test_uppercase_name_rejected() {
        let toml = r#"
[device]
name = "upper-node"
transport = "usb-cdc"

[[channel]]
id = 1
name = "Accel"
type = "f32x3"
rate_hz = 100
"#;
        let path = write_temp_toml(toml);
        let err = parse(&path).unwrap_err();
        assert!(err.contains("invalid character"), "unexpected error: {err}");
    }

    #[test]
    fn test_missing_device_section_rejected() {
        let toml = r#"
[[channel]]
id = 1
name = "accel"
type = "f32x3"
rate_hz = 100
"#;
        let path = write_temp_toml(toml);
        let err = parse(&path).unwrap_err();
        assert!(err.contains("[device]"), "unexpected error: {err}");
    }

    #[test]
    fn test_duplicate_command_id_rejected() {
        let toml = r#"
[device]
name = "dup-cmd"
transport = "usb-cdc"

[[command]]
id = 1
name = "set_rate"

[[command]]
id = 1
name = "set_gain"
"#;
        let path = write_temp_toml(toml);
        let err = parse(&path).unwrap_err();
        assert!(err.contains("duplicated"), "unexpected error: {err}");
    }
}
