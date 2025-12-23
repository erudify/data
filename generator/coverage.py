import sys
import argparse
import yaml
import os
import re
from collections import defaultdict

def load_word_list(filepath):
    """
    Load words from a file (one word per line).
    Handles UTF-8 BOM. Returns a list to preserve order.
    """
    words = []
    if not os.path.exists(filepath):
        print(f"Error: Word list file {filepath} not found.", file=sys.stderr)
        return words
    
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if line not in words:
                words.append(line)
    return words

def is_safe(text):
# ... (same as before)
    # Check if there are any Chinese characters
    has_chinese = any('\u4e00' <= char <= '\u9fff' for char in text)
    if not has_chinese:
        return True
    
    # If it has Chinese, it's only safe if it's a known punctuation mark that we missed.
    # Chinese punctuation often falls in \u3000-\u303F or \uFF00-\uFFEF.
    is_pure_punct = all(
        ('\u3000' <= char <= '\u303F') or 
        ('\uFF00' <= char <= '\uFFEF') or
        (not '\u4e00' <= char <= '\u9fff')
        for char in text
    )
    return is_pure_punct

def main():
    parser = argparse.ArgumentParser(description="Analyze sentence coverage relative to a word list.")
    parser.add_argument("--word-list", required=True, help="Path to the primary vocabulary list (e.g., HSK 1)")
    parser.add_argument("--sentences", required=True, help="Path to the sentences YAML file")
    parser.add_argument("--extra-words", help="Optional path to additional acceptable Chinese words")
    parser.add_argument("--limit", type=int, help="Only print words with coverage count less than this limit")
    parser.add_argument("--output", help="Optional path to save all fully covered sentences in YAML format")
    
    args = parser.parse_args()
    
    vocab_list = load_word_list(args.word_list)
    if not vocab_list:
        return
    vocab_set = set(vocab_list)

    extra_set = set()
    if args.extra_words:
        extra_list = load_word_list(args.extra_words)
        extra_set = set(extra_list)

    if not os.path.exists(args.sentences):
        print(f"Error: Sentences file {args.sentences} not found.", file=sys.stderr)
        return

    with open(args.sentences, 'r', encoding='utf-8') as f:
        sentences = yaml.safe_load(f) or []

    # Map from word -> count of restricted sentences containing it
    coverage = defaultdict(int)
    total_restricted = 0
    covered_sentences = []
    
    for item in sentences:
        chunks = item.get('chunks', [])
        is_restricted = True
        words_in_sentence = set()
        
        for chunk in chunks:
            chinese = chunk.get('chinese', '').strip()
            if not chinese:
                continue
            
            if chinese in vocab_set:
                words_in_sentence.add(chinese)
            elif chinese in extra_set:
                # Acceptable extra word, does not count towards vocab_set counts
                pass
            elif is_safe(chinese):
                # Safe punctuation or non-Chinese characters
                pass
            else:
                # Found a word NOT in vocab, NOT extra, and NOT punctuation
                is_restricted = False
                break
        
        if is_restricted:
            total_restricted += 1
            covered_sentences.append(item)
            for word in words_in_sentence:
                coverage[word] += 1

    # Print results in original word list order
    num_vocab = len(vocab_list)
    for i, word in enumerate(vocab_list, 1):
        count = coverage[word]
        
        if args.limit is not None and count >= args.limit:
            continue
            
        prefix = f"[{i}/{num_vocab}]"
        
        if count == 0:
            # Print in red using ANSI codes
            print(f"\033[91m{prefix} {word}: {count}\033[0m")
        else:
            print(f"{prefix} {word}: {count}")

    print("-" * 20)
    print(f"Total sentences: {len(sentences)}")
    print(f"Fully covered sentences: {total_restricted}")

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            yaml.dump(covered_sentences, f, allow_unicode=True, sort_keys=False)
        print(f"Saved {len(covered_sentences)} covered sentences to {args.output}", file=sys.stderr)

if __name__ == "__main__":
    main()
