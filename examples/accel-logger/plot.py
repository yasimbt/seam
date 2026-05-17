"""Plot accelerometer and temperature data from a .seam recording.

Usage:
    python plot.py session.seam

Requires:
    pip install seam matplotlib
"""

import asyncio
import sys


async def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python plot.py <session.seam>")
        sys.exit(1)

    path = sys.argv[1]

    from seam import Recording

    rec = await Recording.open(path)

    # Collect accel data
    ts, xs, ys, zs = [], [], [], []
    async for s in rec.stream("accel"):
        ts.append(s.timestamp_ms / 1000.0)
        xs.append(s.x)
        ys.append(s.y)
        zs.append(s.z)

    # Collect temperature data
    temp_ts, temps = [], []
    async for s in rec.stream("temperature"):
        temp_ts.append(s.timestamp_ms / 1000.0)
        temps.append(s.values[0])

    print(f"Loaded {len(ts)} accel samples, {len(temps)} temperature samples")

    try:
        import matplotlib.pyplot as plt

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)

        ax1.plot(ts, xs, label="x", color="tab:red")
        ax1.plot(ts, ys, label="y", color="tab:green")
        ax1.plot(ts, zs, label="z", color="tab:blue")
        ax1.set_ylabel("Acceleration (g)")
        ax1.set_title("Accelerometer — accel-logger example")
        ax1.legend()
        ax1.grid(True, alpha=0.3)

        if temps:
            ax2.plot(temp_ts, temps, color="tab:orange")
            ax2.set_ylabel("Temperature (°C)")
            ax2.set_title("Temperature")
            ax2.grid(True, alpha=0.3)

        ax2.set_xlabel("Time (s)")
        plt.tight_layout()
        plt.show()

    except ImportError:
        print("matplotlib not installed — printing stats only")
        if xs:
            print(f"  accel x: min={min(xs):.3f}  max={max(xs):.3f}")
            print(f"  accel y: min={min(ys):.3f}  max={max(ys):.3f}")
            print(f"  accel z: min={min(zs):.3f}  max={max(zs):.3f}")
        if temps:
            print(f"  temp:    min={min(temps):.2f}  max={max(temps):.2f}")


asyncio.run(main())
