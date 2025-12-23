{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  buildInputs = [
    (pkgs.python3.withPackages (ps: [
      ps.boto3
      ps.openai
      ps.pyyaml
    ]))
  ];

  shellHook = ''
    echo "Chinese Example Sentence Generator Environment"
  '';
}
