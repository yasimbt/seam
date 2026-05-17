"""Export .seam recordings to Rerun viewer.

Requires: pip install seam[rerun]
"""

from seam.recording import Recording


class RerunBridge:
    """Bridge to forward Seam samples to a Rerun viewer."""

    async def export(
        self, rec: Recording, output: str, channel: str | None = None
    ) -> None:
        """Export a Recording to Rerun format.

        Stub — full implementation requires the rerun-sdk package.
        """
        try:
            import rerun  # noqa: F401
        except ImportError:
            raise ImportError(
                "rerun export requires the rerun-sdk package. "
                "Install with: pip install seam[rerun]"
            )

        raise NotImplementedError("Rerun export is not yet implemented")

    async def stream_live(self, rec: Recording, channel: str | None = None) -> None:
        """Stream samples live to a Rerun viewer.

        Stub — full implementation requires the rerun-sdk package.
        """
        try:
            import rerun  # noqa: F401
        except ImportError:
            raise ImportError(
                "rerun streaming requires the rerun-sdk package. "
                "Install with: pip install seam[rerun]"
            )

        raise NotImplementedError("Rerun live streaming is not yet implemented")
