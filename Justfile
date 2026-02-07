set shell := ["bash", "-euc"]

@coverage-hsk1:
  nix run .#coverage -- --word-list "HSK/HSK 1.txt" --sentences "corpus/HSK-1-sentences.yml"

@coverage-hsk1-md:
  nix run .#coverage -- --word-list "HSK/HSK 1.txt" --sentences "corpus/HSK-1-sentences.yml" --format markdown --title "Coverage status (HSK 1)" --update-readme README.md

@generate model word:
  nix run .#generate -- --model {{model}} --word {{word}}

@bulk-generate model word_list output:
  nix run .#bulk-generate -- --model {{model}} --word-list {{word_list}} --output {{output}}

@sanitize input:
  nix run .#sanitize -- {{input}}

@sanitize-fix input:
  nix run .#sanitize -- {{input}} --fix

@sanitize-hsk1:
  nix run .#sanitize -- corpus/HSK-1-sentences.yml

@audio input:
  nix run .#audio-gen -- {{input}}
