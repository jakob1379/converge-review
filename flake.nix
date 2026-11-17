{
  description = "converge-review: a four-seat code review skill for Claude Code, and the benchmark behind it";

  nixConfig = {
    extra-substituters = [ "https://cache.numtide.com" ];
    extra-trusted-public-keys = [ "niks3.numtide.com-1:DTx8wZduET09hRmMtKdQDxNNthLQETkc/yaX7M4qK0g=" ];
  };

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
    llm-agents.url = "github:numtide/llm-agents.nix";
    mattpocock-skills = {
      url = "github:mattpocock/skills";
      flake = false;
    };
    open-code-review = {
      url = "github:alibaba/open-code-review";
      flake = false;
    };
    ponytail = {
      url = "github:DietrichGebert/ponytail";
      flake = false;
    };
    superpowers = {
      url = "github:obra/superpowers";
      flake = false;
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      llm-agents,
      ...
    }@inputs:
    let
      lib = nixpkgs.lib;
      systems = [
        "x86_64-linux"
        "aarch64-linux"
        "x86_64-darwin"
        "aarch64-darwin"
      ];
      forAll = f: lib.genAttrs systems (s: f s nixpkgs.legacyPackages.${s} llm-agents.packages.${s});
      skills = {
        converge-review = ./skills/converge-review;
        mattpocock-skills = inputs.mattpocock-skills;
        open-code-review = "${inputs.open-code-review}/plugins/open-code-review/claude-code";
        ponytail = inputs.ponytail;
        superpowers = inputs.superpowers;
      };
    in
    {
      packages = forAll (
        system: pkgs: agents: {
          default = pkgs.runCommand "converge-review-skills" { } ''
            mkdir -p $out
            ${lib.concatStrings (lib.mapAttrsToList (name: src: "cp -r ${src} $out/${name}\n") skills)}
          '';
          inherit (agents) open-code-review;
        }
      );

      apps = forAll (
        system: pkgs: _: {
          default = {
            type = "app";
            meta.description = "Copy converge-review and its four seat skills into ~/.claude/skills";
            program = toString (
              pkgs.writeShellScript "install-converge-review" ''
                set -eu
                dest="''${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
                mkdir -p "$dest"
                for src in ${self.packages.${system}.default}/*; do
                  name=$(basename "$src")
                  if [ -e "$dest/$name" ]; then
                    echo "kept   $name: $dest/$name exists; remove it to update"
                  else
                    cp -r "$src" "$dest/$name" && chmod -R u+w "$dest/$name" && echo "copied $name"
                  fi
                done
                command -v ocr >/dev/null || echo "open-code-review needs 'ocr' on PATH: nix profile install ${self}#open-code-review"
              ''
            );
          };
        }
      );

      homeManagerModules.default =
        { pkgs, ... }:
        {
          home.packages = [ llm-agents.packages.${pkgs.stdenv.hostPlatform.system}.open-code-review ];
          home.file = lib.mapAttrs' (name: src: lib.nameValuePair ".claude/skills/${name}" { source = src; }) skills;
        };

      devShells = forAll (
        system: pkgs: agents: {
          default = pkgs.mkShell {
            packages = [
              pkgs.git
              pkgs.python3
              pkgs.rsync
              pkgs.uv
              agents.claude-code
              agents.codex
              agents.open-code-review
            ];
          };
        }
      );
    };
}
