$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $ProjectRoot

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Host "No .venv found. Run .\setup-windows.cmd first."
    exit 1
}

& $VenvPython -m pip install --upgrade "setuptools<82" wheel
& $VenvPython -m pip install "ctranslate2>=4.4,<5" "transformers<5" sentencepiece safetensors "OpenCC==1.4.1"

$pythonScript = @'
from pathlib import Path
from huggingface_hub import hf_hub_download
from ctranslate2.converters import TransformersConverter

model_name = "alirezamsh/small100"
output_dir = Path("data/models/small100-ct2-int8")
output_dir.parent.mkdir(parents=True, exist_ok=True)

print(f"Downloading {model_name} tokenizer/model metadata into the local cache...")
hf_hub_download(model_name, "tokenization_small100.py")

print(f"Converting {model_name} to CTranslate2 INT8 at {output_dir}...")
converter = TransformersConverter(model_name)
converter.convert(output_dir=str(output_dir), quantization="int8", force=True)
print("Fast Core / CTranslate2 INT8 model is installed. Enable Fast Core from the operator Languages page.")
'@
$pythonScript | & $VenvPython -
