#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -d ".venv" ]]; then
  echo "No .venv found. Run the setup script for this operating system first."
  exit 1
fi

source .venv/bin/activate
python -m pip install --upgrade "setuptools<82" wheel
python -m pip install "transformers<5" sentencepiece safetensors

python - <<'PY'
from huggingface_hub import hf_hub_download
from transformers import M2M100ForConditionalGeneration

model_name = "alirezamsh/small100"
print(f"Downloading {model_name} and its custom tokenizer into the local model cache...")
hf_hub_download(model_name, "tokenization_small100.py")
M2M100ForConditionalGeneration.from_pretrained(model_name)
print("Core SMaLL-100 is installed. Enable Core mode from the operator Languages page.")
PY
