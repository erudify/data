import argparse
import json
import os
import re
import shutil
import sys
import unicodedata
from collections import defaultdict

import yaml


def has_chinese(text):
    for ch in text:
        code = ord(ch)
        if 0x3400 <= code <= 0x4DBF or 0x4E00 <= code <= 0x9FFF:
            return True
    return False


def is_ascii_latin(text):
    return any("a" <= c <= "z" or "A" <= c <= "Z" for c in text)


def strip_tones(text):
    return "".join(
        c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn"
    )


def letters_only(text):
    return "".join(c for c in text if unicodedata.category(c).startswith("L"))


def normalize_pinyin_for_compare(text):
    return letters_only(unicodedata.normalize("NFC", text)).lower()


def normalize_pinyin_fix(text):
    nfc = unicodedata.normalize("NFC", text)
    return "".join(nfc.split()).lower()


ALLOWED_PUNCT_CHARS = set(
    "。！？；：，、（）【】《》“”‘’—…·.-!?;:,()[]{}\"'"
)

ALLOWED_PINYIN_CHARS = set(
    "abcdefghijklmnopqrstuvwxyz"
    "āáǎàēéěèīíǐìōóǒòūúǔù"
    "ǖǘǚǜüv"
    "ńňḿê"
    "'"
)

PUNCT_PINYIN_EQUIV = {
    "。": {"。", "."},
    "，": {"，", ","},
    "？": {"？", "?"},
    "！": {"！", "!"},
    "；": {"；", ";"},
    "：": {"：", ":"},
    "（": {"（", "("},
    "）": {"）", ")"},
    "[": {"[", "【"},
    "]": {"]", "】"},
    "《": {"《", "<"},
    "》": {"》", ">"},
    "“": {"“", '"'},
    "”": {"”", '"'},
    "‘": {"‘", "'"},
    "’": {"’", "'"},
    "…": {"…"},
    "—": {"—", "-"},
    "、": {"、", ","},
}


def is_punctuation_text(text):
    if not text:
        return False
    if has_chinese(text):
        return False
    return all(ch in ALLOWED_PUNCT_CHARS for ch in text)


def is_chinese_word_chunk(text):
    return bool(text) and has_chinese(text) and not is_punctuation_text(text)


def is_english_loader_word(text):
    # Allow common embedded terms like WiFi, e-mail, 5G, USB-C.
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]*", text or ""))


def is_loader_word_chunk(chinese, pinyin, transliteration):
    if not (chinese and pinyin and transliteration):
        return False
    if chinese != pinyin or chinese != transliteration:
        return False
    if has_chinese(chinese):
        return False
    return is_english_loader_word(chinese)


def normalize_sentence_for_near_duplicate(text):
    return "".join(ch for ch in text if ch not in ALLOWED_PUNCT_CHARS and not ch.isspace())


def compute_sentence_line_spans(filename):
    with open(filename, "r", encoding="utf-8") as f:
        lines = f.readlines()

    starts = []
    for idx, line in enumerate(lines):
        if line.startswith("- "):
            starts.append(idx)

    spans = []
    for i, start in enumerate(starts):
        end = (starts[i + 1] - 1) if i + 1 < len(starts) else (len(lines) - 1)
        spans.append((start + 1, end + 1))
    return spans


def resolve_cedict_path():
    env_path = os.environ.get("CEDICT_PATH")
    if env_path:
        return env_path

    script_relative = os.path.join(os.path.dirname(__file__), "cedict_ts.u8")
    if os.path.exists(script_relative):
        return script_relative

    cwd_generator = os.path.join(os.getcwd(), "generator", "cedict_ts.u8")
    if os.path.exists(cwd_generator):
        return cwd_generator

    cwd_root = os.path.join(os.getcwd(), "cedict_ts.u8")
    if os.path.exists(cwd_root):
        return cwd_root

    return script_relative


def load_cedict_set(cedict_path):
    if not os.path.exists(cedict_path):
        return None

    words = set()
    with open(cedict_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line or line.startswith("#"):
                continue
            parts = line.strip().split(" ")
            if len(parts) < 2:
                continue
            words.add(parts[0])
            words.add(parts[1])
    return words


def add_issue(issues, check_id, severity, sentence_index, chunk_index, message, before=None, after=None):
    issues.append(
        {
            "check_id": check_id,
            "severity": severity,
            "sentence_index": sentence_index,
            "chunk_index": chunk_index,
            "message": message,
            "before": before,
            "after": after,
        }
    )


def apply_fixes(data, issues):
    changed = False

    for s_idx, item in enumerate(data):
        chunks = item.get("chunks", []) if isinstance(item, dict) else []
        for c_idx, chunk in enumerate(chunks):
            if not isinstance(chunk, dict):
                continue
            chinese = chunk.get("chinese")
            raw = chunk.get("pinyin")
            transliteration = chunk.get("transliteration")
            if (
                isinstance(chinese, str)
                and isinstance(raw, str)
                and isinstance(transliteration, str)
                and chinese
                and is_english_loader_word(chinese)
                and not has_chinese(chinese)
            ):
                loader_changed = False
                if raw.casefold() == chinese.casefold() and raw != chinese:
                    chunk["pinyin"] = chinese
                    loader_changed = True
                    add_issue(
                        issues,
                        "fix_applied",
                        "info",
                        s_idx,
                        c_idx,
                        "Normalized loader-word chunk so pinyin matches chinese exactly.",
                        before=raw,
                        after=chinese,
                    )
                if (
                    transliteration.casefold() == chinese.casefold()
                    and transliteration != chinese
                ):
                    chunk["transliteration"] = chinese
                    loader_changed = True
                    add_issue(
                        issues,
                        "fix_applied",
                        "info",
                        s_idx,
                        c_idx,
                        "Normalized loader-word chunk so transliteration matches chinese exactly.",
                        before=transliteration,
                        after=chinese,
                    )
                if loader_changed:
                    changed = True
                    continue

            if not isinstance(raw, str):
                continue
            fixed = normalize_pinyin_fix(raw)
            if fixed != raw:
                chunk["pinyin"] = fixed
                changed = True
                add_issue(
                    issues,
                    "fix_applied",
                    "info",
                    s_idx,
                    c_idx,
                    "Normalized pinyin using NFC + lowercase + remove spaces.",
                    before=raw,
                    after=fixed,
                )

    return changed


def apply_deletions(data, issues):
    deletable_check_ids = {
        "duplicate_sentence_exact",
        "duplicate_sentence_normalized",
        "transliteration_sanity",
        "sentence_min_chinese_chunks",
        "punctuation_contract",
    }
    to_delete = set()
    for issue in issues:
        if issue.get("check_id") not in deletable_check_ids:
            continue
        sentence_index = issue.get("sentence_index")
        if sentence_index is None:
            continue
        to_delete.add(sentence_index)

    if not to_delete:
        return False, []

    deleted = []
    kept = []
    for idx, sentence in enumerate(data):
        if idx in to_delete:
            deleted.append(idx)
        else:
            kept.append(sentence)
    data[:] = kept
    return True, sorted(deleted)


def remap_issue_indices_after_deletion(issues, deleted_indices):
    if not deleted_indices:
        return issues
    deleted_set = set(deleted_indices)
    sorted_deleted = sorted(deleted_indices)

    remapped = []
    for issue in issues:
        s_idx = issue.get("sentence_index")
        if s_idx is None:
            remapped.append(issue)
            continue
        updated = dict(issue)
        if s_idx in deleted_set:
            updated["sentence_index"] = None
        else:
            shift = 0
            for d in sorted_deleted:
                if d < s_idx:
                    shift += 1
                else:
                    break
            updated["sentence_index"] = s_idx - shift
        remapped.append(updated)
    return remapped


def check_dataset(data, cedict_words):
    issues = []

    chinese_groups = defaultdict(list)
    near_dup_groups = defaultdict(list)
    chunk_pinyin_forms = defaultdict(lambda: defaultdict(list))

    for s_idx, item in enumerate(data):
        if not isinstance(item, dict):
            add_issue(
                issues,
                "schema_integrity",
                "error",
                s_idx,
                None,
                "Sentence entry is not an object.",
            )
            continue

        english = item.get("english")
        chunks = item.get("chunks")

        if not isinstance(english, str) or not english.strip():
            add_issue(
                issues,
                "schema_integrity",
                "error",
                s_idx,
                None,
                "Sentence is missing non-empty 'english' string.",
            )
        elif english != english.strip():
            add_issue(
                issues,
                "field_whitespace_hygiene",
                "error",
                s_idx,
                None,
                "Sentence 'english' has leading or trailing whitespace.",
                before=english,
                after=english.strip(),
            )

        if not isinstance(chunks, list) or not chunks:
            add_issue(
                issues,
                "schema_integrity",
                "error",
                s_idx,
                None,
                "Sentence is missing non-empty 'chunks' list.",
            )
            continue

        joined_chinese_parts = []
        chinese_word_chunk_count = 0

        for c_idx, chunk in enumerate(chunks):
            if not isinstance(chunk, dict):
                add_issue(
                    issues,
                    "schema_integrity",
                    "error",
                    s_idx,
                    c_idx,
                    "Chunk is not an object.",
                )
                continue

            field_values = {}
            for field in ("chinese", "pinyin", "transliteration"):
                value = chunk.get(field)
                if not isinstance(value, str):
                    add_issue(
                        issues,
                        "schema_integrity",
                        "error",
                        s_idx,
                        c_idx,
                        f"Chunk field '{field}' must be a string.",
                    )
                    value = ""
                field_values[field] = value

            chinese = field_values["chinese"]
            pinyin = field_values["pinyin"]
            transliteration = field_values["transliteration"]
            loader_word_chunk = is_loader_word_chunk(chinese, pinyin, transliteration)

            joined_chinese_parts.append(chinese)

            for field_name, value in field_values.items():
                stripped = value.strip()
                if value != stripped:
                    add_issue(
                        issues,
                        "field_whitespace_hygiene",
                        "error",
                        s_idx,
                        c_idx,
                        f"Chunk field '{field_name}' has leading or trailing whitespace.",
                        before=value,
                        after=stripped,
                    )

            punct = is_punctuation_text(chinese)
            chinese_word = is_chinese_word_chunk(chinese)

            if chinese_word and is_ascii_latin(chinese):
                add_issue(
                    issues,
                    "chinese_chunk_charset",
                    "error",
                    s_idx,
                    c_idx,
                    "Chunk mixes Chinese and ASCII Latin letters.",
                    before=chinese,
                )

            if chinese_word:
                chinese_word_chunk_count += 1

                if not transliteration.strip():
                    add_issue(
                        issues,
                        "transliteration_sanity",
                        "error",
                        s_idx,
                        c_idx,
                        "Chinese chunk must have non-empty transliteration.",
                    )
                if has_chinese(transliteration):
                    add_issue(
                        issues,
                        "transliteration_sanity",
                        "error",
                        s_idx,
                        c_idx,
                        "Transliteration must not contain Chinese characters.",
                        before=transliteration,
                    )

                pinyin_nfc = unicodedata.normalize("NFC", pinyin)
                if pinyin != pinyin_nfc:
                    add_issue(
                        issues,
                        "pinyin_normalization_valid",
                        "error",
                        s_idx,
                        c_idx,
                        "Pinyin must be NFC-normalized.",
                        before=pinyin,
                        after=pinyin_nfc,
                    )

                if pinyin != pinyin.lower():
                    add_issue(
                        issues,
                        "pinyin_normalization_valid",
                        "error",
                        s_idx,
                        c_idx,
                        "Pinyin must be lowercase.",
                        before=pinyin,
                        after=pinyin.lower(),
                    )

                if any(ch.isspace() for ch in pinyin):
                    add_issue(
                        issues,
                        "pinyin_normalization_valid",
                        "error",
                        s_idx,
                        c_idx,
                        "Pinyin must not contain whitespace.",
                        before=pinyin,
                        after="".join(pinyin.split()),
                    )

                if has_chinese(pinyin):
                    add_issue(
                        issues,
                        "pinyin_normalization_valid",
                        "error",
                        s_idx,
                        c_idx,
                        "Pinyin must not contain Chinese characters.",
                        before=pinyin,
                    )

                normalized_for_charset = normalize_pinyin_fix(pinyin)
                invalid_chars = [ch for ch in normalized_for_charset if ch and ch not in ALLOWED_PINYIN_CHARS]
                if invalid_chars:
                    add_issue(
                        issues,
                        "pinyin_normalization_valid",
                        "error",
                        s_idx,
                        c_idx,
                        "Pinyin contains invalid characters.",
                        before=normalized_for_charset,
                    )

                if not letters_only(pinyin):
                    add_issue(
                        issues,
                        "pinyin_normalization_valid",
                        "error",
                        s_idx,
                        c_idx,
                        "Pinyin must contain at least one letter for Chinese chunks.",
                        before=pinyin,
                    )

                if cedict_words is not None and chinese not in cedict_words:
                    add_issue(
                        issues,
                        "cedict_missing_chunk",
                        "warning",
                        s_idx,
                        c_idx,
                        f"Chinese chunk '{chinese}' not found in CE-DICT.",
                    )

                compare_form = normalize_pinyin_for_compare(pinyin)
                if compare_form:
                    chunk_pinyin_forms[chinese][compare_form].append((s_idx, c_idx, pinyin))
            else:
                if punct:
                    if len(chinese) != 1:
                        add_issue(
                            issues,
                            "punctuation_contract",
                            "error",
                            s_idx,
                            c_idx,
                            "Punctuation chunk must contain exactly one punctuation mark.",
                            before=chinese,
                        )

                    if transliteration != "":
                        add_issue(
                            issues,
                            "punctuation_contract",
                            "error",
                            s_idx,
                            c_idx,
                            "Punctuation chunk must have empty transliteration.",
                            before=transliteration,
                            after="",
                        )

                    allowed_pinyins = PUNCT_PINYIN_EQUIV.get(chinese, {chinese})
                    if pinyin not in allowed_pinyins:
                        add_issue(
                            issues,
                            "punctuation_contract",
                            "error",
                            s_idx,
                            c_idx,
                            "Punctuation chunk pinyin does not match allowed canonical punctuation forms.",
                            before=pinyin,
                        )
                elif not loader_word_chunk:
                    # Unknown non-Chinese, non-punctuation chunk text.
                    add_issue(
                        issues,
                        "chinese_chunk_charset",
                        "error",
                        s_idx,
                        c_idx,
                        "Chunk chinese text must be Chinese or supported punctuation.",
                        before=chinese,
                    )

            if all(field_values.get(key, "") == "" for key in ("chinese", "pinyin", "transliteration")):
                add_issue(
                    issues,
                    "schema_integrity",
                    "error",
                    s_idx,
                    c_idx,
                    "Chunk has all-empty fields.",
                )

        joined_chinese = "".join(joined_chinese_parts)

        if not joined_chinese:
            add_issue(
                issues,
                "sentence_reconstruction",
                "error",
                s_idx,
                None,
                "Joined sentence Chinese text is empty.",
            )
        elif not has_chinese(joined_chinese):
            add_issue(
                issues,
                "sentence_reconstruction",
                "error",
                s_idx,
                None,
                "Joined sentence Chinese text does not contain Chinese characters.",
                before=joined_chinese,
            )

        sentence_chinese = item.get("chinese")
        if sentence_chinese is not None:
            if not isinstance(sentence_chinese, str):
                add_issue(
                    issues,
                    "sentence_reconstruction",
                    "error",
                    s_idx,
                    None,
                    "Sentence 'chinese' field must be a string if present.",
                )
            elif sentence_chinese != joined_chinese:
                add_issue(
                    issues,
                    "sentence_reconstruction",
                    "error",
                    s_idx,
                    None,
                    "Sentence 'chinese' does not match concatenated chunk text.",
                    before=sentence_chinese,
                    after=joined_chinese,
                )

        if chinese_word_chunk_count < 3:
            add_issue(
                issues,
                "sentence_min_chinese_chunks",
                "error",
                s_idx,
                None,
                "Sentence must contain at least 3 Chinese-containing non-punctuation chunks.",
            )

        chinese_chunk_count = chinese_word_chunk_count
        if chinese_chunk_count < 3 or chinese_chunk_count > 15:
            add_issue(
                issues,
                "sentence_length_outlier",
                "warning",
                s_idx,
                None,
                f"Chinese chunk count {chinese_chunk_count} outside recommended range [3, 15].",
            )

        if len(chunks) > 25:
            add_issue(
                issues,
                "sentence_length_outlier",
                "warning",
                s_idx,
                None,
                f"Chunk count {len(chunks)} exceeds recommended maximum 25.",
            )

        chinese_groups[joined_chinese].append(s_idx)
        near_dup_groups[normalize_sentence_for_near_duplicate(joined_chinese)].append(s_idx)

    for sentence_text, indices in chinese_groups.items():
        if sentence_text and len(indices) > 1:
            first = indices[0]
            for dup in indices[1:]:
                add_issue(
                    issues,
                    "duplicate_sentence_exact",
                    "error",
                    dup,
                    None,
                    "Duplicate Chinese sentence. First seen earlier in file.",
                    before=sentence_text,
                )

    for norm_text, indices in near_dup_groups.items():
        if norm_text and len(indices) > 1:
            first = indices[0]
            for dup in indices[1:]:
                add_issue(
                    issues,
                    "duplicate_sentence_normalized",
                    "warning",
                    dup,
                    None,
                    "Near-duplicate sentence after punctuation/space normalization. First seen earlier in file.",
                )

    for chinese_chunk, forms in chunk_pinyin_forms.items():
        if len(forms) <= 1:
            continue

        tone_bases = defaultdict(set)
        for form, examples in forms.items():
            stripped = letters_only(strip_tones(form))
            tone_bases[stripped].add(form)

        if len(tone_bases) > 1:
            any_example = next(iter(next(iter(forms.values()))))
            add_issue(
                issues,
                "chunk_pronunciation_inconsistency",
                "warning",
                any_example[0],
                any_example[1],
                f"Chunk '{chinese_chunk}' has multiple base pinyin forms: {', '.join(sorted(tone_bases.keys()))}.",
            )

        for stripped, fulls in tone_bases.items():
            if len(fulls) > 1:
                any_full = next(iter(fulls))
                any_example = forms[any_full][0]
                add_issue(
                    issues,
                    "chunk_pronunciation_inconsistency",
                    "warning",
                    any_example[0],
                    any_example[1],
                    f"Chunk '{chinese_chunk}' has tone inconsistency for base '{stripped}'.",
                )

    issues.sort(
        key=lambda it: (
            it["sentence_index"] if it["sentence_index"] is not None else 10**12,
            it["chunk_index"] if it["chunk_index"] is not None else 10**12,
            it["check_id"],
        )
    )

    return issues


def sentence_span_text(spans, sentence_index):
    if sentence_index is None:
        return "n/a"
    if sentence_index < 0 or sentence_index >= len(spans):
        return "unknown"
    start, end = spans[sentence_index]
    return f"{start}-{end}"


def attach_line_spans(issues, spans):
    enriched = []
    for issue in issues:
        enriched_issue = dict(issue)
        if issue["sentence_index"] is None:
            enriched_issue["line_span"] = None
        elif 0 <= issue["sentence_index"] < len(spans):
            enriched_issue["line_span"] = {
                "start": spans[issue["sentence_index"]][0],
                "end": spans[issue["sentence_index"]][1],
            }
        else:
            enriched_issue["line_span"] = None
        enriched.append(enriched_issue)
    return enriched


def print_text_report(filename, issues, spans):
    print(f"Analyzing {filename}...")

    counts = defaultdict(int)
    for issue in issues:
        counts[issue["severity"]] += 1

    print(f"Summary: {counts.get('error', 0)} errors, {counts.get('warning', 0)} warnings, {counts.get('info', 0)} info")
    print()

    for issue in issues:
        location = f"lines={sentence_span_text(spans, issue['sentence_index'])}"
        if issue["chunk_index"] is not None:
            location += f", chunk={issue['chunk_index']}"
        print(f"[{issue['severity'].upper()}] {issue['check_id']} ({location})")
        print(f"  {issue['message']}")
        if issue.get("before") is not None:
            print(f"  before: {repr(issue['before'])}")
        if issue.get("after") is not None:
            print(f"  after:  {repr(issue['after'])}")


def run_sanitizer(
    filename,
    fix=False,
    delete_non_fixable_errors=False,
    backup_suffix=".bak",
    out_format="text",
    max_errors=None,
):
    if not os.path.exists(filename):
        print(f"File not found: {filename}", file=sys.stderr)
        return 2

    try:
        spans = compute_sentence_line_spans(filename)
        with open(filename, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception as exc:
        print(f"Error parsing YAML: {exc}", file=sys.stderr)
        return 2

    if data is None:
        data = []

    if not isinstance(data, list):
        payload = [
            {
                "check_id": "schema_integrity",
                "severity": "error",
                "sentence_index": None,
                "chunk_index": None,
                "message": "Top-level YAML must be a list of sentence objects.",
                "before": type(data).__name__,
                "after": "list",
            }
        ]
        if out_format == "json":
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print_text_report(filename, payload, spans=[])
        return 1

    modified = False
    fix_issues = []
    if fix:
        changed = apply_fixes(data, fix_issues)
        modified = modified or changed

    cedict_path = resolve_cedict_path()
    cedict_words = load_cedict_set(cedict_path)

    pre_issues = []
    if cedict_words is None:
        pre_issues.append(
            {
                "check_id": "cedict_unavailable",
                "severity": "warning",
                "sentence_index": None,
                "chunk_index": None,
                "message": f"CE-DICT file not found at '{cedict_path}'. Missing-word warnings were skipped.",
                "before": None,
                "after": None,
            }
        )

    pre_issues.extend(check_dataset(data, cedict_words))

    delete_info = []
    if delete_non_fixable_errors:
        deleted, deleted_indices = apply_deletions(data, pre_issues)
        modified = modified or deleted
        fix_issues = remap_issue_indices_after_deletion(fix_issues, deleted_indices)
        for original_index in deleted_indices:
            delete_info.append(
                {
                    "check_id": "delete_applied",
                    "severity": "info",
                    "sentence_index": None,
                    "chunk_index": None,
                    "message": f"Deleted sentence due to non-fixable error(s) at original sentence index {original_index}.",
                    "before": None,
                    "after": None,
                }
            )

    if modified:
        backup_path = filename + backup_suffix
        if not os.path.exists(backup_path):
            shutil.copy2(filename, backup_path)
        with open(filename, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, sort_keys=False)
        spans = compute_sentence_line_spans(filename)

    issues = []
    if cedict_words is None:
        issues.append(
            {
                "check_id": "cedict_unavailable",
                "severity": "warning",
                "sentence_index": None,
                "chunk_index": None,
                "message": f"CE-DICT file not found at '{cedict_path}'. Missing-word warnings were skipped.",
                "before": None,
                "after": None,
            }
        )
    issues.extend(check_dataset(data, cedict_words))
    issues = delete_info + fix_issues + issues
    issues = attach_line_spans(issues, spans)

    if max_errors is not None and max_errors >= 0:
        error_count = 0
        limited = []
        for issue in issues:
            limited.append(issue)
            if issue["severity"] == "error":
                error_count += 1
                if error_count >= max_errors:
                    break
        issues = limited

    if out_format == "json":
        print(json.dumps(issues, ensure_ascii=False, indent=2))
    else:
        print_text_report(filename, issues, spans)

    has_errors = any(i["severity"] == "error" for i in issues)
    return 1 if has_errors else 0


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Deterministic sanity checker for sentence YAML corpora.")
    parser.add_argument("file", help="Path to sentence YAML file")
    parser.add_argument("--strict", action="store_true", default=True, help="Run strict CI checks (default behavior).")
    parser.add_argument("--fix", action="store_true", help="Apply safe auto-fixes (currently pinyin normalization only).")
    parser.add_argument(
        "--delete-non-fixable-errors",
        action="store_true",
        help="Delete sentences with non-fixable findings (duplicate_sentence_exact, duplicate_sentence_normalized, transliteration_sanity, sentence_min_chinese_chunks, punctuation_contract).",
    )
    parser.add_argument("--backup-suffix", default=".bak", help="Backup suffix used with --fix (default: .bak)")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format (default: text)")
    parser.add_argument("--max-errors", type=int, help="Stop after reporting this many errors (includes prior warnings/info).")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv or sys.argv[1:])
    exit_code = run_sanitizer(
        filename=args.file,
        fix=args.fix,
        delete_non_fixable_errors=args.delete_non_fixable_errors,
        backup_suffix=args.backup_suffix,
        out_format=args.format,
        max_errors=args.max_errors,
    )
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
