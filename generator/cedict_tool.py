import os
import sys
import gzip
import urllib.request
import re

CEDICT_URL = "https://www.mdbg.net/chinese/export/cedict/cedict_1_0_ts_utf-8_mdbg.txt.gz"
CEDICT_FILE = "cedict_ts.u8"

def download_cedict():
    if os.path.exists(CEDICT_FILE):
        return
    
    print(f"Downloading CEDICT from {CEDICT_URL}...", file=sys.stderr)
    temp_file = "cedict.gz"
    urllib.request.urlretrieve(CEDICT_URL, temp_file)
    
    with gzip.open(temp_file, 'rb') as f_in:
        with open(CEDICT_FILE, 'wb') as f_out:
            f_out.write(f_in.read())
    
    os.remove(temp_file)
    print("CEDICT downloaded and extracted.", file=sys.stderr)

def lookup_word(word):
    """
    Look up a word in CEDICT and return a list of definitions.
    """
    if not os.path.exists(CEDICT_FILE):
        download_cedict()
    
    definitions = []
    # CEDICT format: Traditional Simplified [pinyin] /definition 1/definition 2/
    # We search for the word in either Traditional or Simplified column.
    
    with open(CEDICT_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            if line.startswith('#'):
                continue
            
            parts = line.strip().split(' ')
            if len(parts) < 3:
                continue
            
            traditional = parts[0]
            simplified = parts[1]
            
            if word == traditional or word == simplified:
                # Extract definitions between slashes
                match = re.search(r'\[(.*?)\] /(.*)/', line)
                if match:
                    pinyin = match.group(1)
                    defs = match.group(2).split('/')
                    definitions.append({
                        'traditional': traditional,
                        'simplified': simplified,
                        'pinyin': pinyin,
                        'definitions': defs
                    })
    
    return definitions

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        res = lookup_word(sys.argv[1])
        for r in res:
            print(f"{r['simplified']} ({r['pinyin']}): {', '.join(r['definitions'])}")
    else:
        print("Usage: python3 cedict_tool.py <word>")
