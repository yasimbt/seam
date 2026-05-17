{ pkgs, lib, config, ... }:

{
  # ── System packages ──────────────────────────────────────────────────────────
  # gcc provides the C linker that Rust needs on NixOS.

  packages = with pkgs; [
    gcc
    pkg-config
    python312        # Python 3.12 (seam-py requires >=3.11)
  ];

  # ── Shell environment ─────────────────────────────────────────────────────────
  # Rust is managed via rustup (in ~/.cargo/bin), not via nix.
  # Run once to set up the embedded target:
  #   rustup target add thumbv7em-none-eabihf

  enterShell = ''
    export PATH="$HOME/.cargo/bin:$PATH"

    echo ""
    echo "seam dev shell"
    printf "  rust    "; rustc   --version 2>/dev/null || echo "(not found — run: rustup toolchain install stable)"
    printf "  cargo   "; cargo   --version 2>/dev/null || echo "(not found)"
    printf "  python  "; python3 --version 2>/dev/null || echo "(not found)"
    echo ""
    echo "  Rust tests:   cargo test -p seam-build -p seam-fw"
    echo "  Python tests: cd seam-py && pytest -m 'not hardware'"
    echo "  seam-py venv: cd seam-py && pip install -e '.[dev]'"
    echo ""
  '';
}
