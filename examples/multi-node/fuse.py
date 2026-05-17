"""Stream from two BLE devices simultaneously and print fused samples.

Usage:
    python fuse.py

Both node_a and node_b must be powered and advertising.
Their BLE addresses can be set in the respective seam.toml files under
[device] address = "XX:XX:XX:XX:XX:XX".
"""

import asyncio

from seam import MultiDevice


async def main() -> None:
    fleet = MultiDevice.from_configs(
        {
            "node_a": "node_a/seam.toml",
            "node_b": "node_b/seam.toml",
        }
    )

    print("Connecting to both nodes...")
    async with fleet.connect() as dev:
        print("Connected. Streaming — press Ctrl+C to stop.\n")
        try:
            async for sample in dev.stream_all():
                print(
                    f"[{sample.device:6}] {sample.channel:<12} "
                    f"{str(sample.values):<30} @ {sample.timestamp_ms}ms"
                )
        except KeyboardInterrupt:
            print("\nStopped.")


asyncio.run(main())
