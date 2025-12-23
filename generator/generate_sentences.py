import sys
import argparse
import json
import yaml
from cedict_tool import lookup_word
from ai_wrappers import run_ai

def validate_data(data):
    if not isinstance(data, list):
        raise ValueError("AI output must be a list of objects.")
    
    for idx, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"Item {idx} in AI output is not an object.")
        
        if "english" not in item or not isinstance(item["english"], str):
            raise ValueError(f"Item {idx} missing 'english' string field.")
            
        if "chunks" not in item or not isinstance(item["chunks"], list):
            raise ValueError(f"Item {idx} missing 'chunks' list field.")
            
        for cidx, chunk in enumerate(item["chunks"]):
            if not isinstance(chunk, dict):
                raise ValueError(f"Chunk {cidx} in item {idx} is not an object.")
            for field in ["chinese", "pinyin", "transliteration"]:
                if field not in chunk or not isinstance(chunk[field], str):
                    raise ValueError(f"Chunk {cidx} in item {idx} missing or invalid '{field}' string field.")

def build_prompt(word, definitions, simple=False):
    defs_str = ""
    for entry in definitions:
        defs_str += f"- {entry['simplified']} ({entry['pinyin']}): {', '.join(entry['definitions'])}\n"
    
    simple_constraint = ""
    if simple:
        simple_constraint = "5. **CRITICAL: Simple Vocabulary**: Use ONLY the 300 most common Chinese characters. This is a strict requirement for absolute beginners."

    prompt = f"""You are an expert Chinese language teacher. Your goal is to generate high-quality example sentences for a target Chinese word.

### Target Audience
The audience consists of Chinese language learners ranging from absolute beginners to advanced students. 

### Instructions for Sentences
1. **Natural & Idiomatic**: Every sentence must be something a native speaker would actually say. Avoid "textbook-style" sentences that sound stiff or artificial.
2. **Pedagogical Range**: Provide a mix of sentences. Some should be simple and direct (for beginners), while others should be more complex, incorporating advanced grammar or specific nuances (for intermediate/advanced students).
3. **Contextual Variety**: Cover different meanings and usages of the word as provided in the dictionary definitions. Use the word in various contexts (e.g., daily life, formal settings, business, social media).
4. **Grammatical Variety**: Use different sentence structures (e.g., questions, statements, sentences with specific particles like 把, 被, 了).
{simple_constraint}

### Output Format
The output MUST be a JSON list of objects. Each object represents one example sentence.

Example list format:
[
  {{
    "english": "I was praised by the teacher.",
    "chunks": [
      {{ "chinese": "我", "pinyin": "wǒ", "transliteration": "I" }},
      {{ "chinese": "被", "pinyin": "bèi", "transliteration": "(passive marker)" }},
      {{ "chinese": "老师", "pinyin": "lǎoshī", "transliteration": "teacher" }},
      {{ "chinese": "表扬", "pinyin": "biǎoyáng", "transliteration": "praised" }},
      {{ "chinese": "了", "pinyin": "le", "transliteration": "(completed)" }},
      {{ "chinese": "。", "pinyin": "。", "transliteration": "" }}
    ]
  }},
  {{
    "english": "Are you a teacher?",
    "chunks": [
      {{ "chinese": "你", "pinyin": "nǐ", "transliteration": "you" }},
      {{ "chinese": "是", "pinyin": "shì", "transliteration": "are" }},
      {{ "chinese": "老师", "pinyin": "lǎoshī", "transliteration": "teacher" }},
      {{ "chinese": "吗", "pinyin": "ma", "transliteration": "(question particle)" }},
      {{ "chinese": "？", "pinyin": "？", "transliteration": "" }}
    ]
  }},
  {{
    "english": "We opened the door.",
    "chunks": [
      {{ "chinese": "我们", "pinyin": "wǒmen", "transliteration": "we" }},
      {{ "chinese": "把", "pinyin": "bǎ", "transliteration": "(object‑focus marker)" }},
      {{ "chinese": "门", "pinyin": "mén", "transliteration": "door" }},
      {{ "chinese": "打开", "pinyin": "dǎkāi", "transliteration": "opened" }},
      {{ "chinese": "了", "pinyin": "le", "transliteration": "(completed action)" }},
      {{ "chinese": "。", "pinyin": "。", "transliteration": "" }}
    ]
  }}
]

### Chunking & Pinyin Guidelines
- **Word Segmentation**: Break the sentence into logical word chunks. Follow standard modern Chinese word segmentation rules.
- **Transliteration**: For each chunk, provide a "best-effort" transliteration that reflects its meaning *in the context of that specific sentence*.
- **Punctuation**: Each punctuation mark (e.g., 。, ，, ！) must be its own chunk with an empty transliteration string and the punctuation itself as the pinyin.
- **Colloquial Pinyin (Neutral Tones)**: Use neutral tones (no tone mark) for the second syllable in common colloquial words. For example:
    - 那个: `nàge` (not `nàgè`)
    - 告诉: `gàosu` (not `gàosù`)
    - 喜欢: `xǐhuan` (not `xǐhuān`)
    - 回来: `huílai` (not `huílái`)
    - 那边: `nàbian` (not `nàbiān`)
    - 甚至: `shènzhi` (not `shènzhì`)
    - 早上: `zǎoshang` (not `zǎoshàng`)
    - 休息: `xiūxi` (not `xiūxí`)

Output only valid JSON.

---

Target word: "{word}"

Dictionary definitions for "{word}":
{defs_str}"""
    return prompt

def generate_for_word(model, word, mock=False, simple=False):
    """
    Generate example sentences for a single word.
    Returns a list of dictionaries.
    """
    definitions = lookup_word(word)
    if not definitions:
        raise ValueError(f"No definitions found for '{word}' in CEDICT.")

    prompt = build_prompt(word, definitions, simple=simple)
    
    if mock:
        response_text = json.dumps([
            {
                "english": f"I {word} the computer.",
                "chunks": [
                    {"chinese": "我", "pinyin": "Wǒ", "transliteration": "I"},
                    {"chinese": word, "pinyin": word, "transliteration": word},
                    {"chinese": "电脑", "pinyin": "diànnǎo", "transliteration": "computer"},
                    {"chinese": "。", "pinyin": ".", "transliteration": ""}
                ]
            },
            {
                "english": f"If you {word} your heart to study, you will do better.",
                "chunks": [
                    {"chinese": "如果你", "pinyin": "Rúguǒnǐ", "transliteration": "if you"},
                    {"chinese": word, "pinyin": word, "transliteration": word},
                    {"chinese": "心", "pinyin": "xīn", "transliteration": "heart"},
                    {"chinese": "学习", "pinyin": "xuéxí", "transliteration": "study"},
                    {"chinese": "，", "pinyin": ",", "transliteration": ""},
                    {"chinese": "你", "pinyin": "nǐ", "transliteration": "you"},
                    {"chinese": "会", "pinyin": "huì", "transliteration": "will"},
                    {"chinese": "做得", "pinyin": "zuòde", "transliteration": "do"},
                    {"chinese": "更好", "pinyin": "gènghǎo", "transliteration": "better"},
                    {"chinese": "。", "pinyin": ".", "transliteration": ""}
                ]
            }
        ])
    else:
        response_text = run_ai(model, prompt)
    
    # Strip markdown code blocks if present
    clean_text = response_text.strip()
    if clean_text.startswith("```"):
        first_newline = clean_text.find("\n")
        last_backticks = clean_text.rfind("```")
        if first_newline != -1 and last_backticks != -1:
            clean_text = clean_text[first_newline:last_backticks].strip()
    
    try:
        data = json.loads(clean_text)
    except json.JSONDecodeError as e:
        print(f"--- INVALID AI RESPONSE ---\n{response_text}\n---------------------------", file=sys.stderr)
        raise e

    try:
        validate_data(data)
    except ValueError as e:
        print(f"--- INVALID AI SCHEMA ---\n{json.dumps(data, indent=2, ensure_ascii=False)}\n--------------------------", file=sys.stderr)
        raise e
    return data

def main():
    parser = argparse.ArgumentParser(description="Generate Chinese example sentences using AI.")
    parser.add_argument("--model", required=True, help="Model name (Haiku, Sonnet, Opus, free, or OpenRouter model ID)")
    parser.add_argument("--word", required=True, help="Target Chinese word")
    parser.add_argument("--mock", action="store_true", help="Use mock AI response for testing")
    parser.add_argument("--simple", action="store_true", help="Demand simple language (300 common characters)")
    
    args = parser.parse_args()
    
    try:
        print(f"Generating sentences for '{args.word}'...", file=sys.stderr)
        data = generate_for_word(args.model, args.word, args.mock, args.simple)
        print(yaml.dump(data, allow_unicode=True, sort_keys=False), end='')
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()
