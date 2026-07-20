$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $ProjectRoot

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Host "No .venv found. Run .\setup-windows.cmd first."
    exit 1
}

& $VenvPython -m pip install --upgrade "setuptools<82" wheel
& $VenvPython -m pip install "transformers<5" sentencepiece safetensors "OpenCC==1.4.1"

$pythonScript = @'
from huggingface_hub import hf_hub_download
from transformers import M2M100ForConditionalGeneration

model_name = "alirezamsh/small100"
print(f"Downloading {model_name} and its custom tokenizer into the local model cache...")
hf_hub_download(model_name, "tokenization_small100.py")
M2M100ForConditionalGeneration.from_pretrained(model_name)
print("Core SMaLL-100 is installed. Enable Core mode from the operator Languages page.")
'@
$pythonScript | & $VenvPython -
