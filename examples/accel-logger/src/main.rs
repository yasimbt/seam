//! Minimal accel-logger example for Seam.
//!
//! Streams accelerometer (f32x3) and temperature (f32) from an nRF52840
//! over USB CDC to the Python host SDK.
//!
//! Build:
//!   cargo build --target thumbv7em-none-eabihf
//!
//! Stream on host:
//!   seam inspect --config seam.toml
//!   # or
//!   seam record  --config seam.toml --output session.seam

#![no_std]
#![no_main]

use embassy_executor::Spawner;
use embassy_nrf::{config::Config, init};
use embassy_time::Timer;
use seam_fw::{transport::UsbCdc, Sampler};

// Generated from seam.toml by seam-build in build.rs.
// Provides: Channel::Accel, Channel::Temperature
include!(concat!(env!("OUT_DIR"), "/seam_generated.rs"));

/// Read accelerometer — replace with your real sensor driver.
///
/// Returns (x, y, z) in units matching `seam.toml` (g).
fn read_accel(_p: &embassy_nrf::Peripherals) -> [f32; 3] {
    // Stub: static gravity vector pointing -Z
    [0.0_f32, 0.0_f32, -9.81_f32]
}

/// Read temperature sensor — replace with your real sensor driver.
///
/// Returns degrees Celsius.
fn read_temperature(_p: &embassy_nrf::Peripherals) -> f32 {
    // Stub: room temperature
    24.5_f32
}

#[embassy_executor::main]
async fn main(_spawner: Spawner) {
    let p = init(Config::default());
    let mut sampler = Sampler::new(UsbCdc::new(p.USBD));

    loop {
        // Send accelerometer frame (100 Hz from seam.toml advisory rate)
        sampler
            .send(Channel::Accel, read_accel(&p))
            .await
            .ok();

        // Send temperature every 10th iteration (~10 Hz)
        sampler
            .send(Channel::Temperature, read_temperature(&p))
            .await
            .ok();

        Timer::after_millis(10).await;
    }
}
