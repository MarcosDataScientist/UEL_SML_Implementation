#!/usr/bin/env bash
# ==============================================================================
# Script: setup_models.sh
# Finalidade: Baixar e verificar SLMs candidatas no contêiner Ollama do Home Lab
# Modelos recomendados para CPU (Intel Xeon E5-2640 v2, 8 GB RAM):
#  - llama3.2:1b   (~1.3 GB) - Ultraleve, latência mínima
#  - llama3.2:3b   (~2.0 GB) - Raciocínio equilibrado
#  - qwen2.5:1.5b  (~1.0 GB) - Excelente aderência em português
#  - qwen2.5:3b    (~1.9 GB) - Alta precisão em extração de parâmetros
#  - smollm2:1.7b  (~1.0 GB) - Modelo compacto da Hugging Face
# ==============================================================================

set -euo pipefail

CONTAINER_NAME="homelab-slm-ollama"

echo "======================================================================"
echo " 🤖 Gestão de Modelos SLM - Home Lab Ollama"
echo "======================================================================"

# Verificar se o contêiner Ollama está em execução
if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "[ERRO] O contêiner '${CONTAINER_NAME}' não está em execução."
    echo "       Execute 'make up' antes de baixar os modelos."
    exit 1
fi

echo "[INFO] Contêiner '${CONTAINER_NAME}' ativo e comunicável."

# Modelos padrão a serem baixados
MODELS=(
    "llama3.2:1b"
    "llama3.2:3b"
    "qwen2.5:1.5b"
    "qwen2.5:3b"
)

# Permitir passar modelo específico via argumento
if [ "$#" -gt 0 ]; then
    MODELS=("$@")
fi

echo "--> Modelos na fila de download:"
for m in "${MODELS[@]}"; do
    echo "    - $m"
done
echo ""

for model in "${MODELS[@]}"; do
    echo "----------------------------------------------------------------------"
    echo "📥 Baixando modelo: ${model}..."
    docker exec -t "${CONTAINER_NAME}" ollama pull "${model}"
    echo "✅ Modelo ${model} pronto!"
done

echo ""
echo "======================================================================"
echo " 📋 Modelos instalados no Ollama:"
echo "======================================================================"
docker exec -t "${CONTAINER_NAME}" ollama list
echo ""
echo "💡 Para testar um modelo interativamente no terminal:"
echo "   docker exec -it ${CONTAINER_NAME} ollama run llama3.2:1b"
echo "======================================================================"
