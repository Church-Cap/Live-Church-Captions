$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Python = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    throw "No .venv found. Run the Windows setup script first."
}

Push-Location $Root
try {
    & $Python (Join-Path $Root "scripts\report-install-progress.py") 84 "tigrinya-dependencies" "Preparing Tigrinya translation dependencies."
    & $Python -m pip install "ctranslate2>=4.4,<5" "transformers<5" "sentencepiece>=0.2.1,<0.3" safetensors
    if ($LASTEXITCODE -ne 0) { throw "Tigrinya runtime installation failed with exit code $LASTEXITCODE." }
    $Code = @'
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
import ctranslate2
from ctranslate2.converters import TransformersConverter
from transformers import AutoTokenizer
from app.install_progress import write_install_progress
from app.resource_installer import validate_tokenizer_save_paths

model_name = "Helsinki-NLP/opus-mt-en-ti"
revision = "72f1e40b4b60ff4863407f90792b4fac517562ec"
model_dir = Path(os.environ.get("CHURCHCAP_OPUS_TIGRINYA_DIR", "data/models/opus-mt-en-ti-ct2-int8"))
tokenizer_dir = Path(os.environ.get("CHURCHCAP_OPUS_TIGRINYA_TOKENIZER_DIR", "data/models/opus-mt-en-ti-tokenizer"))
model_dir.parent.mkdir(parents=True, exist_ok=True)
required_tokenizer_files = ("tokenizer_config.json", "source.spm", "target.spm", "vocab.json")
model_ready = ctranslate2.contains_model(str(model_dir))
tokenizer_ready = all((tokenizer_dir / filename).is_file() for filename in required_tokenizer_files)
if model_ready and tokenizer_ready:
    write_install_progress(96, "verifying", "Checking the existing Tigrinya model.")
    print("Tigrinya model files are already installed; checking them before use…", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(str(tokenizer_dir), local_files_only=True)
else:
    write_install_progress(86, "downloading", "Downloading the pinned English-to-Tigrinya model.", indeterminate=True)
    print("Downloading the pinned Apache-2.0 English-to-Tigrinya model…", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(model_name, revision=revision)
    validate_tokenizer_save_paths(tokenizer, tokenizer_dir)
    tokenizer.save_pretrained(tokenizer_dir)
    write_install_progress(91, "converting", "Converting the Tigrinya model to INT8.", indeterminate=True)
    print("Converting the Tigrinya model to CTranslate2 INT8…", flush=True)
    TransformersConverter(model_name, revision=revision, trust_remote_code=False).convert(
        output_dir=str(model_dir), quantization="int8", force=True
    )
print("Checking the installed Tigrinya translation model…", flush=True)
write_install_progress(97, "verifying", "Running a local Tigrinya translation check.")
translator = ctranslate2.Translator(str(model_dir), device="cpu", compute_type="int8")
source = tokenizer.convert_ids_to_tokens(tokenizer.encode("Hello, welcome to church."))
result = translator.translate_batch([source], beam_size=2, max_decoding_length=64)[0]
target = result.hypotheses[0] if result.hypotheses else []
translated = tokenizer.decode(tokenizer.convert_tokens_to_ids(target), skip_special_tokens=True).strip()
if not translated or translated == "Hello, welcome to church." or not any("\u1200" <= character <= "\u137f" for character in translated):
    raise RuntimeError("The installed English-to-Tigrinya model failed its local translation check.")
print("Tigrinya text translation is installed and ready.", flush=True)
write_install_progress(98, "tigrinya-ready", "The Tigrinya translation model is ready.")
'@
    # Windows PowerShell 5.1 can strip embedded quotes when a multiline string
    # is passed to a native program through `python -c`. Write the reviewed
    # source as UTF-8 instead so hashes, paths and Unicode reach Python exactly.
    $TempPythonScript = Join-Path ([System.IO.Path]::GetTempPath()) ("churchcap-tigrinya-" + [Guid]::NewGuid().ToString("N") + ".py")
    $PythonExitCode = 1
    try {
        $Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
        [System.IO.File]::WriteAllText($TempPythonScript, $Code, $Utf8NoBom)
        & $Python $TempPythonScript
        $PythonExitCode = $LASTEXITCODE
    }
    finally {
        Remove-Item -LiteralPath $TempPythonScript -Force -ErrorAction SilentlyContinue
    }
    if ($PythonExitCode -ne 0) { throw "Tigrinya model conversion failed with exit code $PythonExitCode." }
}
finally {
    Pop-Location
}
