import argparse
import json
import os
import sys
from collections import Counter

import yaml

from cedict_tool import load_word_list


def has_chinese(text):
    return any("\u4e00" <= c <= "\u9fff" for c in text)


def is_safe(text):
    has = has_chinese(text)
    if not has:
        return True

    return all(
        ("\u3000" <= c <= "\u303f")
        or ("\uff00" <= c <= "\uffef")
        or (not ("\u4e00" <= c <= "\u9fff"))
        for c in text
    )


def is_all_chinese_chars(text):
    return bool(text) and all("\u4e00" <= c <= "\u9fff" for c in text)


def load_sentences(path):
    if not os.path.exists(path):
        raise FileNotFoundError(f"Sentences file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or []
    if not isinstance(data, list):
        raise ValueError("Sentence YAML must be a list.")
    return data


def collect_candidate_compounds(sentences, base_allowed, vocab_chars):
    chunk_counts = Counter()
    for item in sentences:
        chunks = item.get("chunks", [])
        if not isinstance(chunks, list):
            continue
        for chunk in chunks:
            if not isinstance(chunk, dict):
                continue
            text = chunk.get("chinese", "")
            if not isinstance(text, str):
                continue
            text = text.strip()
            if text:
                chunk_counts[text] += 1

    candidates = []
    skipped = Counter()
    for chunk, count in chunk_counts.items():
        if chunk in base_allowed:
            skipped["in_base_allowed"] += 1
            continue
        if is_safe(chunk):
            skipped["safe_or_punct"] += 1
            continue
        if not has_chinese(chunk):
            skipped["not_chinese"] += 1
            continue
        if not is_all_chinese_chars(chunk):
            skipped["mixed_chars"] += 1
            continue
        if len(chunk) < 2 or len(chunk) > 4:
            skipped["length_outside_2_4"] += 1
            continue
        if any(c not in vocab_chars for c in chunk):
            skipped["char_not_in_vocab"] += 1
            continue
        candidates.append((chunk, count))

    candidates.sort(key=lambda x: (-x[1], x[0]))
    return candidates, skipped, len(chunk_counts)


def build_sentence_requirement_counts(sentences, vocab_set, base_allowed, candidate_set):
    baseline_eligible = 0
    req_counter = Counter()

    for item in sentences:
        chunks = item.get("chunks", [])
        if not isinstance(chunks, list):
            continue

        words_in_sentence = set()
        unknown_chunks = set()

        for chunk in chunks:
            if not isinstance(chunk, dict):
                continue
            text = chunk.get("chinese", "")
            if not isinstance(text, str):
                continue
            text = text.strip()
            if not text:
                continue

            if text in vocab_set:
                words_in_sentence.add(text)
            elif text in base_allowed:
                continue
            elif is_safe(text):
                continue
            else:
                unknown_chunks.add(text)

        if not words_in_sentence:
            continue

        if not unknown_chunks:
            baseline_eligible += 1
            continue

        if all(u in candidate_set for u in unknown_chunks):
            req_counter[frozenset(unknown_chunks)] += 1

    return baseline_eligible, req_counter


def score_results(candidates, req_counter, max_compounds, min_gain):
    single_gain = {}
    for compound, _count in candidates:
        gain = req_counter.get(frozenset([compound]), 0)
        if gain >= min_gain:
            single_gain[compound] = gain

    results = [([compound], gain) for compound, gain in single_gain.items()]

    if max_compounds >= 2:
        candidate_words = [c for c, _count in candidates]
        for i, w1 in enumerate(candidate_words):
            g1 = req_counter.get(frozenset([w1]), 0)
            for w2 in candidate_words[i + 1 :]:
                gain = g1 + req_counter.get(frozenset([w2]), 0) + req_counter.get(frozenset([w1, w2]), 0)
                if gain >= min_gain:
                    results.append(([w1, w2], gain))

    results.sort(key=lambda row: (-row[1], len(row[0]), "+".join(row[0])))
    return results


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Find candidate compound additions that unlock more list-only sentences."
    )
    parser.add_argument("--word-list", required=True, help="Path to the primary vocabulary list")
    parser.add_argument("--sentences", required=True, help="Path to sentence YAML")
    parser.add_argument("--extra-words", help="Optional extra allowed words file")
    parser.add_argument("--top", type=int, default=100, help="Maximum rows to output (default: 100)")
    parser.add_argument(
        "--min-gain",
        type=int,
        default=1,
        help="Only report additions that unlock at least this many sentences (default: 1)",
    )
    parser.add_argument(
        "--max-compounds",
        type=int,
        choices=[1, 2],
        default=2,
        help="Maximum compounds per suggestion (1 or 2, default: 2)",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--max-candidates",
        type=int,
        help="Optional cap on number of candidate compounds to score (after sorting)",
    )
    parser.add_argument(
        "--show-skipped",
        action="store_true",
        help="Print candidate filtering diagnostics to stderr",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv or sys.argv[1:])

    vocab_list = load_word_list(args.word_list)
    if not vocab_list:
        print("Error: word list is empty or unreadable.", file=sys.stderr)
        return 2

    extra_set = set()
    if args.extra_words:
        extra_set = set(load_word_list(args.extra_words))

    try:
        sentences = load_sentences(args.sentences)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    vocab_set = set(vocab_list)
    base_allowed = vocab_set | extra_set
    vocab_chars = set()
    for word in vocab_set:
        for c in word:
            if "\u4e00" <= c <= "\u9fff":
                vocab_chars.add(c)

    candidates_with_count, skipped, unique_chunk_count = collect_candidate_compounds(
        sentences, base_allowed, vocab_chars
    )

    if args.max_candidates is not None and args.max_candidates >= 0:
        candidates_with_count = candidates_with_count[: args.max_candidates]

    candidate_set = {compound for compound, _count in candidates_with_count}
    baseline_eligible, req_counter = build_sentence_requirement_counts(
        sentences, vocab_set, base_allowed, candidate_set
    )

    results = score_results(
        candidates_with_count,
        req_counter,
        max_compounds=args.max_compounds,
        min_gain=args.min_gain,
    )

    if args.top >= 0:
        results = results[: args.top]

    if args.show_skipped:
        print(f"Unique chunks seen: {unique_chunk_count}", file=sys.stderr)
        print(f"Candidates retained: {len(candidates_with_count)}", file=sys.stderr)
        for key in sorted(skipped.keys()):
            print(f"Skipped {key}: {skipped[key]}", file=sys.stderr)
        print(f"Baseline eligible sentences: {baseline_eligible}", file=sys.stderr)

    if args.format == "json":
        payload = [
            {
                "compounds": compounds,
                "label": "+".join(compounds),
                "additional_sentences": gain,
            }
            for compounds, gain in results
        ]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for compounds, gain in results:
            label = "+".join(compounds)
            print(f"{label}: {gain} additional sentences.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
