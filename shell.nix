# shell.nix — NixOS development shell for Seam
# Usage: nix-shell
# Or for Rust tests: nix-shell --run "~/.cargo/bin/cargo test -p seam-build -p seam-fw"
{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  buildInputs = with pkgs; [
    gcc
    pkg-config
  ];

  shellHook = ''
    export PATH="${pkgs.gcc}/bin:$PATH"
    export CARGO_HOME="$HOME/.cargo"
    export PATH="$CARGO_HOME/bin:$PATH"
    echo "seam dev shell — gcc $(gcc --version | head -1)"
  '';
}
