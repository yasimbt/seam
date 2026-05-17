"""Export .seam recordings to MCAP format.

Requires: pip install seam[mcap]
"""

from seam.recording import Recording


async def export_mcap(rec: Recording, output: str, channel: str | None = None) -> None:
    """Export a Recording to MCAP format.

    Stub — full implementation requires the mcap package.
    """
    try:
        import mcap  # noqa: F401
    except ImportError:
        raise ImportError(
            "mcap export requires the mcap package. Install with: pip install seam[mcap]"
        )

    raise NotImplementedError("MCAP export is not yet implemented")
