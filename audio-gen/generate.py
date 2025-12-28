import argparse
import os
import yaml
import requests
import re
import unicodedata
from pathlib import Path

DEFAULT_CHINESE_VOICES = [
    {"name": "julia", "id": "tOuLUAIdXShmWH7PEUrU"},
    {"name": "jin", "id": "vZZLclMx4wouUtKBRfZn"}
]
DEFAULT_ENGLISH_VOICES = DEFAULT_CHINESE_VOICES
ELEVENLABS_API_URL = "https://api.elevenlabs.io/v1/text-to-speech"

def normalize(text):
    # Normalize unicode characters to decompose combined characters (like accented letters)
    nfkd_form = unicodedata.normalize('NFKD', text)
    # Filter out non-spacing mark characters (accents)
    text = "".join([c for c in nfkd_form if not unicodedata.combining(c)])
    # Lowercase
    text = text.lower()
    # Replace non-alphanumeric characters with underscores
    text = re.sub(r'[^a-z0-9]', '_', text)
    # Collapse multiple underscores
    text = re.sub(r'_+', '_', text)
    # Strip leading/trailing underscores
    text = text.strip('_')
    return text

def generate_audio(text, voice_id, output_path, api_key):
    if output_path.exists():
        # print(f"Skipping {output_path.name}, already exists.")
        return

    url = f"{ELEVENLABS_API_URL}/{voice_id}"
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json"
    }
    data = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75
        }
    }
    
    print(f"Generating audio for: '{text}' -> {output_path.name}")
    try:
        response = requests.post(url, json=data, headers=headers)
        if response.status_code == 200:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'wb') as f:
                f.write(response.content)
        else:
            print(f"Error generating audio for '{text}': {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Exception generating audio for '{text}': {e}")

def main():
    parser = argparse.ArgumentParser(description="Generate audio files for sentences in a YML file.")
    parser.add_argument("input_file", type=Path, help="Path to the YML file containing sentences.")
    parser.add_argument("--count", type=int, help="Limit the number of exercises to process.")
    
    args = parser.parse_args()
    
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        print("Error: ELEVENLABS_API_KEY environment variable is not set.")
        return

    if not args.input_file.exists():
        print(f"Error: Input file '{args.input_file}' does not exist.")
        return

    # Determine output directory relative to script location
    # The script is in erudify/data/audio-gen/
    # We want to output to erudify/data/generated/audio/
    script_dir = Path(__file__).resolve().parent
    output_dir = script_dir.parent / "generated" / "audio"
    
    print(f"Reading from {args.input_file}")
    print(f"Outputting to {output_dir}")

    with open(args.input_file, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)

    if args.count is not None:
        data = data[:args.count]

    for item in data:
        # Generate English Audio
        if 'english' in item:
            eng_text = item['english']
            for voice in DEFAULT_ENGLISH_VOICES:
                voice_name = voice['name']
                voice_id = voice['id']
                eng_filename = f"{voice_name}_{normalize(eng_text)}.mp3"
                generate_audio(eng_text, voice_id, output_dir / eng_filename, api_key)

        # Generate Chinese Audio
        if 'chunks' in item:
            # Concatenate Chinese Chunks
            chi_text = "".join([c.get('chinese', '') for c in item['chunks']])
            
            # Construct Pinyin string for filename normalization
            # Using space to separate chunks in filename for readability before normalization
            pinyin_parts = [c.get('pinyin', '') for c in item['chunks']]
            pinyin_str = " ".join(pinyin_parts)
            
            if chi_text:
                for voice in DEFAULT_CHINESE_VOICES:
                    voice_name = voice['name']
                    voice_id = voice['id']
                    chi_filename = f"{voice_name}_{normalize(pinyin_str)}.mp3"
                    generate_audio(chi_text, voice_id, output_dir / chi_filename, api_key)

if __name__ == "__main__":
    main()
