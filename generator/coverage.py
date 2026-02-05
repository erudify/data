import sys
import argparse
import yaml
import os

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

def analyze_sentences(sentences, vocab_list, extra_set):
    vocab_set = set(vocab_list)
    word_to_index = {word: idx for idx, word in enumerate(vocab_list)}

    total_counts = [0] * len(vocab_list)
    prefix_counts = [0] * len(vocab_list)
    min_extra = [None] * len(vocab_list)
    covered_sentences = []
    total_restricted = 0

    for item in sentences:
        chunks = item.get('chunks', [])
        words_in_sentence = set()
        unknown_words = set()

        for chunk in chunks:
            chinese = chunk.get('chinese', '').strip()
            if not chinese:
                continue

            if chinese in vocab_set:
                words_in_sentence.add(chinese)
            elif chinese in extra_set:
                continue
            elif is_safe(chinese):
                continue
            else:
                unknown_words.add(chinese)

        if not words_in_sentence or unknown_words:
            continue

        total_restricted += 1
        covered_sentences.append(item)

        indices = sorted({word_to_index[word] for word in words_in_sentence})
        max_index = indices[-1]
        for pos, idx in enumerate(indices):
            total_counts[idx] += 1
            if max_index <= idx:
                prefix_counts[idx] += 1
            extra_needed = len(indices) - pos - 1
            current_min = min_extra[idx]
            if current_min is None or extra_needed < current_min:
                min_extra[idx] = extra_needed

    return {
        "total_counts": total_counts,
        "prefix_counts": prefix_counts,
        "min_extra": min_extra,
        "covered_sentences": covered_sentences,
        "total_restricted": total_restricted,
    }

def render_legacy(vocab_list, total_counts, limit):
    num_vocab = len(vocab_list)
    for i, word in enumerate(vocab_list, 1):
        count = total_counts[i - 1]

        if limit is not None and count >= limit:
            continue

        prefix = f"[{i}/{num_vocab}]"

        if count == 0:
            print(f"\033[91m{prefix} {word}: {count}\033[0m")
        else:
            print(f"{prefix} {word}: {count}")

def render_text(vocab_list, total_counts, prefix_counts, min_extra, limit):
    num_vocab = len(vocab_list)
    for i, word in enumerate(vocab_list, 1):
        total = total_counts[i - 1]
        prefix = prefix_counts[i - 1]
        extra_needed = min_extra[i - 1]

        if limit is not None and total >= limit:
            continue

        extra_label = "N/A" if extra_needed is None else str(extra_needed)
        print(f"[{i}/{num_vocab}] {word}: prefix={prefix} list={total} min_extra={extra_label}")

def render_markdown(args, vocab_list, total_counts, prefix_counts, min_extra, summary):
    title = args.title or "Coverage status"
    lines = [f"## {title}", ""]
    lines.append(f"- Word list: `{args.word_list}` ({summary['num_vocab']} words)")
    lines.append(f"- Sentences: {summary['total_sentences']} total, {summary['total_restricted']} list-only")
    lines.append(f"- Target: prefix >= {args.min_prefix}, list-only >= {args.min_total}")
    lines.append(f"- Prefix-ready words: {summary['prefix_ready']} ({summary['prefix_ready_pct']:.1f}%)")
    lines.append(f"- List-only coverage: {summary['total_ready']} ({summary['total_ready_pct']:.1f}%)")
    lines.append("")

    rows = []
    for idx, word in enumerate(vocab_list):
        total = total_counts[idx]
        prefix = prefix_counts[idx]
        extra_needed = min_extra[idx]
        if not args.show_all:
            if prefix >= args.min_prefix and total >= args.min_total:
                continue
        extra_label = "N/A" if extra_needed is None else str(extra_needed)
        rows.append((word, idx + 1, prefix, total, extra_label))

    if not rows:
        lines.append("All words meet the target thresholds.")
        return "\n".join(lines)

    lines.append("| Word | Index | Prefix sentences | List-only sentences | Min extra words |")
    lines.append("| --- | ---: | ---: | ---: | ---: |")
    for word, idx, prefix, total, extra_label in rows:
        lines.append(f"| {word} | {idx} | {prefix} | {total} | {extra_label} |")
    return "\n".join(lines)

def update_markdown_file(path, content):
    start_marker = "<!-- COVERAGE_START -->"
    end_marker = "<!-- COVERAGE_END -->"
    block = f"{start_marker}\n\n{content}\n\n{end_marker}"

    if not os.path.exists(path):
        with open(path, 'w', encoding='utf-8') as f:
            f.write("# Erudify data\n\n")
            f.write(block)
            f.write("\n")
        return

    with open(path, 'r', encoding='utf-8') as f:
        existing = f.read()

    if start_marker in existing and end_marker in existing:
        before, remainder = existing.split(start_marker, 1)
        _, after = remainder.split(end_marker, 1)
        updated = before + block + after
    else:
        if existing and not existing.endswith("\n"):
            existing += "\n"
        updated = existing + "\n" + block + "\n"

    with open(path, 'w', encoding='utf-8') as f:
        f.write(updated)

def main():
    parser = argparse.ArgumentParser(description="Analyze sentence coverage relative to a word list.")
    parser.add_argument("--word-list", required=True, help="Path to the primary vocabulary list (e.g., HSK 1)")
    parser.add_argument("--sentences", required=True, help="Path to the sentences YAML file")
    parser.add_argument("--extra-words", help="Optional path to additional acceptable Chinese words")
    parser.add_argument("--limit", type=int, help="Only print words with coverage count less than this limit")
    parser.add_argument("--output", help="Optional path to save all fully covered sentences in YAML format")
    parser.add_argument("--format", choices=["legacy", "text", "markdown"], default="text", help="Output format")
    parser.add_argument("--min-prefix", type=int, default=1, help="Target minimum prefix-only sentences per word")
    parser.add_argument("--min-total", type=int, default=5, help="Target minimum list-only sentences per word")
    parser.add_argument("--show-all", action="store_true", help="Show all words in markdown output")
    parser.add_argument("--title", help="Optional markdown title")
    parser.add_argument("--update-readme", help="Insert markdown output into the README between markers")
    
    args = parser.parse_args()
    
    vocab_list = load_word_list(args.word_list)
    if not vocab_list:
        return
    extra_set = set()
    if args.extra_words:
        extra_list = load_word_list(args.extra_words)
        extra_set = set(extra_list)

    if not os.path.exists(args.sentences):
        print(f"Error: Sentences file {args.sentences} not found.", file=sys.stderr)
        return

    with open(args.sentences, 'r', encoding='utf-8') as f:
        sentences = yaml.safe_load(f) or []

    analysis = analyze_sentences(sentences, vocab_list, extra_set)
    total_counts = analysis["total_counts"]
    prefix_counts = analysis["prefix_counts"]
    min_extra = analysis["min_extra"]
    covered_sentences = analysis["covered_sentences"]
    total_restricted = analysis["total_restricted"]

    summary = {
        "num_vocab": len(vocab_list),
        "total_sentences": len(sentences),
        "total_restricted": total_restricted,
    }
    summary["prefix_ready"] = sum(1 for count in prefix_counts if count >= args.min_prefix)
    summary["total_ready"] = sum(1 for count in total_counts if count >= args.min_total)
    summary["prefix_ready_pct"] = (summary["prefix_ready"] / summary["num_vocab"]) * 100 if summary["num_vocab"] else 0
    summary["total_ready_pct"] = (summary["total_ready"] / summary["num_vocab"]) * 100 if summary["num_vocab"] else 0

    if args.format == "legacy":
        render_legacy(vocab_list, total_counts, args.limit)
    elif args.format == "markdown":
        report = render_markdown(args, vocab_list, total_counts, prefix_counts, min_extra, summary)
        if args.update_readme:
            update_markdown_file(args.update_readme, report)
        else:
            print(report)
    else:
        render_text(vocab_list, total_counts, prefix_counts, min_extra, args.limit)
        print("-" * 20)
        print(f"Total sentences: {summary['total_sentences']}")
        print(f"List-only sentences: {summary['total_restricted']}")
        print(f"Prefix-ready words: {summary['prefix_ready']} ({summary['prefix_ready_pct']:.1f}%)")
        print(f"List-only coverage: {summary['total_ready']} ({summary['total_ready_pct']:.1f}%)")

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            yaml.dump(covered_sentences, f, allow_unicode=True, sort_keys=False)
        print(f"Saved {len(covered_sentences)} covered sentences to {args.output}", file=sys.stderr)

if __name__ == "__main__":
    main()
