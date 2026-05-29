#!/bin/bash

set -e

echo "[1/5] Subindo LocalStack..."
docker compose up -d localstack

echo "[2/5] Construindo imagens..."
docker compose build client server

echo "[3/5] Cliente criptografando e enviando dados..."
docker compose run --rm client encrypt

echo "[4/5] Servidor processando dados criptografados..."
docker compose run --rm server

echo "[5/5] Cliente descriptografando resultado..."
docker compose run --rm client decrypt

echo
echo "Execução principal concluída."
cat output/client/resultado_final.json
