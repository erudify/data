import json
import os
import sys
import random
from pathlib import Path

# Load .env manually to avoid dependency
def load_env():
    # Check current dir and parent dir
    search_paths = [Path(".env"), Path(__file__).parent / ".env", Path(__file__).parent.parent / ".env"]
    for env_path in search_paths:
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    if "=" in line and not line.startswith("#"):
                        key, value = line.strip().split("=", 1)
                        os.environ[key] = value
            return

load_env()

FREE_MODELS = [
    "tngtech/deepseek-r1t2-chimera:free",
#    "xiaomi/mimo-v2-flash:free",
    "nex-agi/deepseek-v3.1-nex-n1:free",
#    "z-ai/glm-4.5-air:free",
#    "openai/gpt-oss-20b:free",
    "allenai/olmo-3.1-32b-think:free",
    "google/gemma-3-27b-it:free",
#    "meta-llama/llama-3.3-70b-instruct:free",
    "openai/gpt-oss-120b:free",
]

def get_claude_model_id(model_name):
    mapping = {
        "Haiku": "arn:aws:bedrock:eu-west-1:118330671040:inference-profile/global.anthropic.claude-haiku-4-5-20251001-v1:0",
        "Sonnet": "arn:aws:bedrock:eu-west-1:118330671040:inference-profile/global.anthropic.claude-sonnet-4-5-20250929-v1:0",
        "Opus": "arn:aws:bedrock:eu-west-1:118330671040:inference-profile/global.anthropic.claude-opus-4-5-20251101-v1:0"
    }
    return mapping.get(model_name, model_name)

def opencode(model_name, prompt):
    """
    AWS Bedrock Claude wrapper.
    """
    import boto3
    bedrock = boto3.client(service_name='bedrock-runtime')
    model_id = get_claude_model_id(model_name)
    
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 16000,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ]
    })
    
    response = bedrock.invoke_model(body=body, modelId=model_id)
    response_body = json.loads(response.get('body').read())
    return response_body['content'][0]['text']

def openrouter_wrapper(model_name, prompt):
    """
    OpenRouter wrapper.
    """
    from openai import OpenAI
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY"),
    )
    
    response = client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"} if "json" in prompt.lower() else None,
        max_tokens=16000
    )
    return response.choices[0].message.content

def run_ai(model_name, prompt):
    if model_name == "free":
        model_name = random.choice(FREE_MODELS)
        print(f"Selected random free model: {model_name}", file=sys.stderr)
    
    if model_name in ["Haiku", "Sonnet", "Opus"]:
        return opencode(model_name, prompt)
    elif "/" in model_name or model_name.endswith(":free"):
        return openrouter_wrapper(model_name, prompt)
    else:
        raise ValueError(f"Unknown model: {model_name}")
