{
  description = "Erudify data tools - Chinese sentence generation and grading";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.11";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};

        pythonEnv = pkgs.python3.withPackages (ps: [
          ps.boto3
          ps.openai
          ps.pyyaml
          ps.requests
        ]);

        mkPythonApp = name: script: pkgs.writeShellApplication {
          name = name;
          runtimeInputs = [ pythonEnv ];
          text = ''
            if [ -n "''${PYTHONPATH:-}" ]; then
              export PYTHONPATH="${./generator}:''${PYTHONPATH}"
            else
              export PYTHONPATH="${./generator}"
            fi
            exec ${pythonEnv}/bin/python ${script} "$@"
          '';
        };

        coverage = mkPythonApp "coverage" ./generator/coverage.py;
        generate = mkPythonApp "generate-sentences" ./generator/generate_sentences.py;
        bulk = mkPythonApp "bulk-generate" ./generator/bulk_generate.py;
        audio = mkPythonApp "audio-gen" ./audio-gen/generate.py;
      in
      {
        apps = {
          coverage = {
            type = "app";
            program = "${coverage}/bin/coverage";
          };
          generate = {
            type = "app";
            program = "${generate}/bin/generate-sentences";
          };
          bulk-generate = {
            type = "app";
            program = "${bulk}/bin/bulk-generate";
          };
          audio-gen = {
            type = "app";
            program = "${audio}/bin/audio-gen";
          };
          default = self.apps.${system}.coverage;
        };

        packages = {
          coverage = coverage;
          generate-sentences = generate;
          bulk-generate = bulk;
          audio-gen = audio;
          default = coverage;
        };

        devShells.default = pkgs.mkShell {
          buildInputs = [
            pythonEnv
            pkgs.just
            coverage
            generate
            bulk
            audio
          ];

          shellHook = ''
            echo "Erudify data tools"
            echo "  just --list"
          '';
        };
      }
    );
}
