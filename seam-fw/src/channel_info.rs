/// Trait abstracting the channel metadata needed for encoding.
///
/// The generated `Channel` enum implements this trait. Tests can provide
/// their own implementations.
pub trait ChannelInfo {
    fn id(&self) -> u8;
    fn payload_size(&self) -> usize;
}
