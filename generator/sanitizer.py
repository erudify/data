import yaml
import sys
import os
import unicodedata
from collections import defaultdict

def strip_tones(s):
    return "".join(c for c in unicodedata.normalize('NFD', s)
                  if unicodedata.category(c) != 'Mn').lower()

def normalize_pinyin_full(pinyin):
    return "".join(c for c in pinyin if unicodedata.category(c).startswith('L')).lower()

def normalize_pinyin_stripped(pinyin):
    stripped = strip_tones(pinyin)
    return "".join(c for c in stripped if unicodedata.category(c).startswith('L')).lower()

def run_sanitizer(filename):
    if not os.path.exists(filename):
        print(f"File not found: {filename}")
        return

    print(f"Analyzing {filename}...")
    with open(filename, 'r', encoding='utf-8') as f:
        try:
            data = yaml.safe_load(f)
        except Exception as e:
            print(f"Error parsing YAML: {e}")
            return

    if not data:
        print("Empty file.")
        return

    # 1. Full-sentence duplicate search
    chinese_groups = defaultdict(list)
    # 2. Word-level inconsistency search
    word_map = defaultdict(lambda: defaultdict(list)) # chinese_chunk -> full_pinyin -> list of sentence_indices

    for i, entry in enumerate(data):
        if 'chunks' not in entry:
            continue
        
        full_chinese = "".join(chunk.get('chinese', '') for chunk in entry['chunks'])
        chinese_groups[full_chinese].append(i)

        for chunk in entry['chunks']:
            ch = chunk.get('chinese', '')
            py = chunk.get('pinyin', '')
            if not any(unicodedata.category(c).startswith('L') for c in ch):
                continue
            
            py_full = normalize_pinyin_full(py)
            if not py_full: continue
            
            word_map[ch][py_full].append(i)

    # Output Duplicates
    duplicates_found = 0
    for chinese, indices in chinese_groups.items():
        if len(indices) > 1:
            # Group by full pinyin of the sentence
            pinyin_map = defaultdict(list)
            for idx in indices:
                full_py = " ".join(c.get('pinyin', '') for c in data[idx]['chunks'])
                pinyin_map[normalize_pinyin_full(full_py)].append(idx)
            
            if len(pinyin_map) == 1:
                if duplicates_found < 10:
                    print(f"\n[DUPLICATE SENTENCE] {chinese}")
                    print(f"  Pinyin:  {' '.join(c.get('pinyin', '') for c in data[indices[0]]['chunks'])}")
                    print(f"  English: {[data[idx].get('english', '???') for idx in indices]}")
                duplicates_found += 1

    if duplicates_found > 10:
        print(f"  ... and {duplicates_found - 10} more duplicate sentences.")
    elif duplicates_found == 0:
        print("\nNo duplicate sentences found.")
    else:
        print(f"\nFound {duplicates_found} duplicate sentences.")

    # Output Inconsistent Tones
    print("\n[INCONSISTENT TONES] (Same letters, different tones)")
    inconsistent_count = 0
    for ch, py_full_map in sorted(word_map.items()):
        if len(py_full_map) > 1:
            # Check if they have the same base letters
            stripped_map = defaultdict(list) # stripped -> list of full_pinyins
            for py_full in py_full_map.keys():
                stripped_map[normalize_pinyin_stripped(py_full)].append(py_full)
            
            for stripped, full_pinyins in stripped_map.items():
                if len(full_pinyins) > 1:
                    inconsistent_count += 1
                    print(f"  Chinese: {ch}")
                    for fp in sorted(full_pinyins):
                        # Find original raw pinyin for this full version
                        indices = py_full_map[fp]
                        # Just grab the first sample's raw pinyin for this chunk
                        sample_raw = ""
                        for idx in indices:
                            for chunk in data[idx]['chunks']:
                                if chunk.get('chinese') == ch and normalize_pinyin_full(chunk.get('pinyin', '')) == fp:
                                    sample_raw = chunk.get('pinyin', '')
                                    break
                            if sample_raw: break
                        
                        print(f"    - {sample_raw} (in {len(indices)} sentences, e.g. '{data[indices[0]].get('english')}')")

    if inconsistent_count == 0:
        print("  None found.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 sanitizer.py <file.yml>")
    else:
        run_sanitizer(sys.argv[1])
