#!/usr/bin/env bash
# ==============================================================================
# Script: setup_models.sh
# Purpose: Pull and verify candidate SLMs in the Home Lab Ollama container
# Recommended models for CPU (Intel Xeon E5-2640 v2, 8 GB RAM):
#  - llama3.2:1b   (~1.3 GB) - Ultralight, minimal latency
#  - llama3.2:3b   (~2.0 GB) - Balanced reasoning
#  - qwen2.5:1.5b  (~1.0 GB) - Excellent Portuguese instruction adherence
#  - qwen2.5:3b    (~1.9 GB) - High precision in parameter extraction
#  - smollm2:1.7b  (~1.0 GB) - Compact Hugging Face model
# ==============================================================================

set -euo pipefail

CONTAINER_NAME="homelab-slm-ollama"

echo "======================================================================"
echo " 🤖 SLM Model Management - Home Lab Ollama"
echo "======================================================================"

# Check if the Ollama container is running
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "[ERROR] Container '${CONTAINER_NAME}' is not running."
    echo "        Run 'make up' before pulling models."
    exit 1
fi

echo "[INFO] Container '${CONTAINER_NAME}' is active and healthy."

# Default candidate models to pull
MODELS=(
    "llama3.2:1b"
    "llama3.2:3b"
    "qwen2.5:1.5b"
    "qwen2.5:3b"
)

# Allow passing a specific model as argument
if [ "$#" -gt 0 ]; then
    MODELS=("$@")
fi

echo "--> Models queued for download:"
for m in "${MODELS[@]}"; do
    echo "    - $m"
done
echo ""

for model in "${MODELS[@]}"; do
    echo "----------------------------------------------------------------------"
    echo "📥 Pulling model: ${model}..."
    docker exec -t "${CONTAINER_NAME}" ollama pull "${model}"
    echo "✅ Model ${model} ready!"
done

echo ""
echo "======================================================================"
echo " 📋 Models installed in Ollama:"
echo "======================================================================"
docker exec -t "${CONTAINER_NAME}" ollama list
echo ""
echo "💡 To test a model interactively in terminal:"
echo "   docker exec -it ${CONTAINER_NAME} ollama run llama3.2:1b"
echo "======================================================================"
