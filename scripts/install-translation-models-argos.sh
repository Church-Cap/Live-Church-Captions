#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

ENABLE_RUNTIME="false"
INSTALL_SCOPE="common"
for arg in "$@"; do
  case "$arg" in
    --enable) ENABLE_RUNTIME="true" ;;
    --all) INSTALL_SCOPE="all" ;;
    --common) INSTALL_SCOPE="common" ;;
  esac
done

if [[ ! -d ".venv" ]]; then
  echo "No .venv found. Run ./setup-macos.sh first."
  exit 1
fi

source .venv/bin/activate
python -m pip install --upgrade "setuptools<82" wheel
python -m pip install -r requirements-translation.txt
cat <<'MSG'

Argos Translate is installed in the local .venv.

The next step attempts to download/install English -> target-language packages.
Default scope: common church languages. Use --all to install every English -> target package in the Argos index.
This requires internet access now, but live translation itself runs locally afterwards.

MSG
python - <<PY
from argostranslate import package
SCOPE = "$INSTALL_SCOPE"
COMMON_TARGETS = ["es", "fr", "pt", "pl", "uk", "ar", "fa"]
print("Updating Argos package index…")
package.update_package_index()
available = package.get_available_packages()
if SCOPE == "all":
    targets = sorted({p.to_code for p in available if p.from_code == "en" and p.to_code != "en"})
else:
    targets = COMMON_TARGETS
installed = []
missing = []
for target in targets:
    candidates = [p for p in available if p.from_code == "en" and p.to_code == target]
    if not candidates:
        missing.append(target)
        print(f"No en->{target} package found in the Argos index.")
        continue
    pkg = candidates[0]
    print(f"Downloading/installing en->{target}: {pkg.package_version}…")
    path = pkg.download()
    package.install_from_path(path)
    installed.append(target)
print("\nInstalled target languages:", ", ".join(installed) or "none")
if missing:
    print("Missing packages:", ", ".join(missing))
PY

python - <<PY
from pathlib import Path
import json

env_path = Path('.env')
if not env_path.exists():
    template = Path('.env.example') if Path('.env.example').exists() else Path('env.example')
    env_path.write_text(template.read_text(encoding='utf-8'), encoding='utf-8')

values = {
    'TRANSLATION_ENABLED': 'true' if '$ENABLE_RUNTIME' == 'true' else 'false',
    'TRANSLATION_PROVIDER': 'argos',
    'TRANSLATION_ALLOWED_LANGUAGES': 'en',
    'TRANSLATION_MAX_ACTIVE_LANGUAGES': '1',
}

lines = env_path.read_text(encoding='utf-8').splitlines()
seen = set()
new_lines = []
for line in lines:
    if '=' in line and not line.lstrip().startswith('#'):
        key = line.split('=', 1)[0].strip()
        if key in values:
            new_lines.append(f"{key}={values[key]}")
            seen.add(key)
        else:
            new_lines.append(line)
    else:
        new_lines.append(line)
for key, value in values.items():
    if key not in seen:
        new_lines.append(f"{key}={value}")
env_path.write_text('\n'.join(new_lines) + '\n', encoding='utf-8')

# Set operator runtime defaults. By default models/provider are ready, but live
# translated captions stay disabled until the operator turns them on in the web UI.
data_dir = Path('data')
data_dir.mkdir(exist_ok=True)
runtime_path = data_dir / 'runtime_config.json'
if runtime_path.exists():
    try:
        runtime = json.loads(runtime_path.read_text(encoding='utf-8'))
    except Exception:
        runtime = {}
else:
    runtime = {}
runtime.update({
    'translation_enabled': True if '$ENABLE_RUNTIME' == 'true' else False,
    'translation_allowed_languages': ['en'],
    'translation_max_active_languages': 20,
})
runtime_path.write_text(json.dumps(runtime, indent=2), encoding='utf-8')
PY

if [[ "$ENABLE_RUNTIME" == "true" ]]; then
  echo "\nArgos has been configured and enabled in .env/runtime_config.json."
  echo "Translation remains experimental; keep maximum active languages low for Sunday use."
else
  echo "\nArgos has been configured in .env/runtime_config.json but live translation is OFF."
  echo "Enable it in the operator Languages panel when ready, or rerun with --enable."
fi
