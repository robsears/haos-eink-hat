{
  description = "HAOS e-ink dashboard: Home Assistant add-on driving a Waveshare 2.7\" e-Paper HAT on a Pi's GPIO/SPI";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/26.05";
  };

  outputs =
    { nixpkgs, ... }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "x86_64-darwin"
        "aarch64-darwin"
      ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
    in
    {
      devShells = forAllSystems (
        system:
        let
          pkgs = import nixpkgs { inherit system; };
          python = pkgs.python3.withPackages (
            ps: with ps; [
              pillow
              websockets
              requests
              ruff
            ]
          );
        in
        {
          default = pkgs.mkShell {
            packages = with pkgs; [
              python
              nixfmt
              shellcheck
              docker
              parted
              dosfstools
            ];
          };
        }
      );
    };
}
