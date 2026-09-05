#!/usr/bin/env bash
set -u
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
log() { echo "[$(date +%H:%M:%S)] $*"; }

declare -a repos=(
  "https://github.com/SCLBD/DeepfakeBench|DeepfakeBench"
  "https://github.com/alexsabb/CVDeepfakeBench|CVDeepfakeBench"
  "https://github.com/WisconsinAIVision/UniversalFakeDetect|UniversalFakeDetect"
  "https://github.com/polimi-ispl/prnu-python|prnu-python"
  "https://github.com/sim-pez/prnu|prnu-simpez"
  "https://github.com/E0HYL/CameraFingerprint_pytorch|CameraFingerprint_pytorch"
  "https://github.com/frassom/prnu-copy-attack|prnu-copy-attack"
  "https://github.com/BiDAlab/DeepFakesON-Phys|DeepFakesON-Phys"
  "https://github.com/alinle/rPPG|rPPG-Toolbox"
  "https://github.com/phuselab/pyVHR|pyVHR"
  "https://github.com/Daisy-Zhang/Awesome-Deepfakes-Detection|Awesome-Deepfakes-Detection"
  "https://github.com/flyingby/Awesome-Deepfake-Generation-and-Detection|Awesome-Deepfake-Gen-Detect"
  "https://github.com/qiqitao77/Awesome-Comprehensive-Deepfake-Detection|Awesome-Comprehensive-Deepfake-Detection"
  "https://github.com/Purdue-M2/AI-Face-FairnessBench|AI-Face-FairnessBench"
)

for entry in "${repos[@]}"; do
  url="${entry%%|*}"; name="${entry##*|}"
  if [ -d "$name/.git" ]; then log "SKIP (exists): $name"; continue; fi
  log "CLONE: $name"
  if git clone --depth 1 --no-tags --filter=blob:none "$url" "$name" > "$name.clone.log" 2>&1; then
    log "OK: $name"
  else
    log "FAIL: $name (see $name.clone.log)"
  fi
done
log "DONE"
