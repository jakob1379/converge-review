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
      agentsWithSkills = [
        "antigravity-cli"
        "claude-code"
        "codex"
        "crush"
        "github-copilot-cli"
        "opencode"
        "warp-terminal"
      ];
    in
    {
      skills = forAll (
        system: pkgs: _:
        lib.mapAttrs (name: src: pkgs.runCommand "skill-${name}" { } "cp -r ${src} $out") {
          converge-review = ./skills/converge-review;
          requesting-code-review = "${inputs.superpowers}/skills/requesting-code-review";
          ponytail-review = "${inputs.ponytail}/skills/ponytail-review";
          code-review = "${inputs.mattpocock-skills}/skills/engineering/code-review";
          delegate-review = pkgs.runCommand "delegate-review-src" { } ''
            mkdir $out
            { printf -- '---\nname: delegate-review\n'
              sed -n '2,/^---$/p' ${inputs.open-code-review}/plugins/open-code-review/claude-code/commands/delegate-review.md
              sed '1,/^---$/{/^---$/!d}' ${inputs.open-code-review}/plugins/open-code-review/claude-code/commands/delegate-review.md | sed '1,2d'
            } > $out/SKILL.md
          '';
        }
      );

      packages = forAll (
        system: pkgs: agents: {
          default = pkgs.linkFarm "converge-review-skills" self.skills.${system};
          inherit (agents) open-code-review;
        }
      );

      apps = forAll (
        system: pkgs: _: {
          default = {
            type = "app";
            meta.description = "Copy converge-review and its four seat skills into ~/.claude/skills or $SKILLS_DIR";
            program = toString (
              pkgs.writeShellScript "install-converge-review" ''
                set -eu
                dest="''${SKILLS_DIR:-''${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}}"
                mkdir -p "$dest"
                for src in ${self.packages.${system}.default}/*; do
                  name=$(basename "$src")
                  if [ -e "$dest/$name" ]; then
                    echo "kept   $name: $dest/$name exists; remove it to update"
                  else
                    cp -rL "$src" "$dest/$name" && chmod -R u+w "$dest/$name" && echo "copied $name"
                  fi
                done
                command -v ocr >/dev/null || echo "open-code-review needs 'ocr' on PATH: nix profile install ${self}#open-code-review"
              ''
            );
          };
        }
      );

      homeManagerModules.default =
        {
          config,
          options,
          pkgs,
          ...
        }:
        let
          system = pkgs.stdenv.hostPlatform.system;
          present = builtins.filter (a: options.programs ? ${a} && options.programs.${a} ? skills) agentsWithSkills;
        in
        {
          home.packages = [ llm-agents.packages.${system}.open-code-review ];
          programs = lib.genAttrs present (a: {
            skills = lib.mkIf config.programs.${a}.enable self.skills.${system};
          });
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
