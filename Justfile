set shell := ["bash", "-euc"]

@coverage-hsk1:
  nix run .#coverage -- --word-list "HSK/HSK 1.txt" --sentences "corpus/HSK-1-sentences.yml"

@coverage-hsk1-md:
  nix run .#coverage -- --word-list "HSK/HSK 1.txt" --sentences "corpus/HSK-1-sentences.yml" --format markdown --title "Coverage status (HSK 1)" --update-readme README.md

@generate model word:
  nix run .#generate -- --model {{model}} --word {{word}}

@bulk-generate model word_list output:
  nix run .#bulk-generate -- --model {{model}} --word-list {{word_list}} --output {{output}}

@audio input:
  nix run .#audio-gen -- {{input}}
