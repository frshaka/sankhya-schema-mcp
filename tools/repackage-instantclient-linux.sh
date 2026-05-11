#!/usr/bin/env bash
# Reempacota o zip oficial da Oracle para o formato esperado pelo setup.sh
# Uso: bash tools/repackage-instantclient-linux.sh <caminho-para-o-zip-oracle>

set -e

ORACLE_ZIP="${1:-}"

if [ -z "$ORACLE_ZIP" ] || [ ! -f "$ORACLE_ZIP" ]; then
    echo "Uso: bash tools/repackage-instantclient-linux.sh <arquivo.zip>"
    echo "Exemplo: bash tools/repackage-instantclient-linux.sh ~/Downloads/instantclient-basic-linux.x64-21.13.0.0.0dbru.zip"
    exit 1
fi

WORK_DIR="$(mktemp -d)"
OUTPUT_ZIP="$(pwd)/instantclient-linux.zip"

echo "[1/4] Extraindo $ORACLE_ZIP ..."
unzip -q "$ORACLE_ZIP" -d "$WORK_DIR"

# O zip da Oracle extrai para instantclient_XX_Y/ — normalizar para instantclient/
EXTRACTED_DIR=$(find "$WORK_DIR" -maxdepth 1 -type d -name "instantclient*" | head -1)
if [ -z "$EXTRACTED_DIR" ]; then
    echo "ERRO: estrutura inesperada no zip Oracle — pasta instantclient_* não encontrada"
    rm -rf "$WORK_DIR"
    exit 1
fi

echo "[2/4] Reorganizando para instantclient/ ..."
mv "$EXTRACTED_DIR" "$WORK_DIR/instantclient"

# Criar symlink libclntsh.so sem versão se necessário
if [ ! -f "$WORK_DIR/instantclient/libclntsh.so" ]; then
    VERSIONED=$(ls "$WORK_DIR/instantclient"/libclntsh.so.* 2>/dev/null | head -1)
    if [ -n "$VERSIONED" ]; then
        (cd "$WORK_DIR/instantclient" && ln -sf "$(basename "$VERSIONED")" libclntsh.so)
        echo "  [OK] Symlink libclntsh.so criado → $(basename "$VERSIONED")"
    fi
fi

echo "[3/4] Gerando $OUTPUT_ZIP ..."
# -y preserva symlinks no zip em vez de copiar o conteúdo dos arquivos apontados
(cd "$WORK_DIR" && zip -qry "$OUTPUT_ZIP" instantclient/)

echo "[4/4] Limpando temporários ..."
rm -rf "$WORK_DIR"

SIZE=$(du -sh "$OUTPUT_ZIP" | cut -f1)
echo ""
echo "[OK] $OUTPUT_ZIP gerado ($SIZE)"
echo ""
echo "Próximo passo: suba este arquivo no GitHub Release v1.0 com o nome 'instantclient-linux.zip':"
echo "  gh release upload v1.0 instantclient-linux.zip --repo frshaka/sankhya-schema-mcp"
