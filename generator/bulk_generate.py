import sys
import argparse
import yaml
import os
from collections import defaultdict
from generate_sentences import generate_for_word

def load_word_list(filepath):
    """
    Load words from a file (one word per line).
    """
    words = []
    if not os.path.exists(filepath):
        print(f"Error: Word list file {filepath} not found.", file=sys.stderr)
        return words
    
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        for line in f:
            word = line.strip()
            if word:
                words.append(word)
    return words

def get_sentence_counts(output_file, word_list):
    """
    Count how many sentences exist for each word in the output file.
    Uses substring matching to handle multi-character words.
    """
    counts = defaultdict(int)
    if not os.path.exists(output_file) or os.path.getsize(output_file) == 0:
        return counts
    
    # Use a set for slightly faster membership checks if we were doing exact matches,
    # but for substring matching we still need to iterate.
    # However, we only care about the words in our current list.
    target_words = set(word_list)
    
    try:
        with open(output_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            if data and isinstance(data, list):
                for item in data:
                    # Reconstruct Chinese sentence from chunks
                    chunks = item.get('chunks', [])
                    chinese_text = "".join(c.get('chinese', '') for c in chunks)
                    for word in target_words:
                        if word in chinese_text:
                            counts[word] += 1
    except Exception as e:
        print(f"Warning: Could not read existing output file {output_file}: {e}", file=sys.stderr)
        
    return counts

def append_to_output(output_file, new_sentences):
    """
    Append new sentences to the YAML output file.
    Reads current data, appends, and rewrites to maintain valid YAML.
    """
    all_data = []
    if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
        with open(output_file, 'r', encoding='utf-8') as f:
            all_data = yaml.safe_load(f) or []
    
    all_data.extend(new_sentences)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        yaml.dump(all_data, f, allow_unicode=True, sort_keys=False)

def main():
    parser = argparse.ArgumentParser(description="Bulk generate Chinese example sentences.")
    parser.add_argument("--model", required=True, help="Model name")
    parser.add_argument("--word-list", required=True, help="Path to word list file (e.g. HSK file)")
    parser.add_argument("--output", required=True, help="Path to output YAML file")
    parser.add_argument("--mock", action="store_true", help="Use mock AI response")
    parser.add_argument("--limit", type=int, default=5, help="Target number of sentences per word (default: 5)")
    parser.add_argument("--retries", type=int, default=3, help="Number of retries per word on failure (default: 3)")
    parser.add_argument("--simple", action="store_true", help="Demand simple language (300 common characters)")
    
    args = parser.parse_args()
    
    words = load_word_list(args.word_list)
    if not words:
        return

    # Count existing sentences using the words we just loaded
    target_words = set(words)
    counts = get_sentence_counts(args.output, words)
    consecutive_failures = 0
    total_new_count = 0
    
    num_words = len(words)
    
    for i, word in enumerate(words, 1):
        if consecutive_failures >= 5:
            print(f"Stopping execution after 5 consecutive failures.", file=sys.stderr)
            break
            
        current_count = counts.get(word, 0)
        progress_prefix = f"[{i}/{num_words}]"
        if current_count < args.limit:
            print(f"{progress_prefix} Word '{word}' has {current_count} sentences. Target is {args.limit}.", file=sys.stderr)
            
            success = False
            for attempt in range(args.retries + 1):
                try:
                    sentences = generate_for_word(args.model, word, args.mock, args.simple)
                    append_to_output(args.output, sentences)
                    print(f"{progress_prefix} Appended {len(sentences)} new sentences for '{word}' to {args.output}", file=sys.stderr)
                    
                    # Update counts for ALL words in the vocabulary based on new sentences
                    for s in sentences:
                        chunks = s.get('chunks', [])
                        chinese_text = "".join(c.get('chinese', '') for c in chunks)
                        for w in target_words:
                            if w in chinese_text:
                                counts[w] += 1
                    
                    total_new_count += len(sentences)
                    consecutive_failures = 0
                    success = True
                    break # Success, move to next word
                except Exception as e:
                    consecutive_failures += 1
                    print(f"{progress_prefix} Error generating for '{word}' (Attempt {attempt+1}/{args.retries+1}, Sequential Failures {consecutive_failures}/5): {e}", file=sys.stderr)
                    if consecutive_failures >= 5:
                        break # Stop everything
                    if attempt < args.retries:
                        print(f"{progress_prefix} Retrying '{word}'...", file=sys.stderr)
            
            if not success and consecutive_failures >= 5:
                break
        else:
            print(f"{progress_prefix} Word '{word}' already has {current_count} sentences. Skipping.", file=sys.stderr)
            
    if total_new_count > 0:
        print(f"Finished bulk generation. Added {total_new_count} sentences in total.", file=sys.stderr)
    else:
        print("No new sentences generated.", file=sys.stderr)

if __name__ == "__main__":
    main()
