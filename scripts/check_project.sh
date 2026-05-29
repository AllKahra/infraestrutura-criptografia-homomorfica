#!/bin/bash

echo "Estrutura do projeto:"
find . -maxdepth 3 -type f | sort

echo
echo "Status Docker Compose:"
docker compose ps -a

echo
echo "Arquivos de resultado:"
find resultados bonus/resultados evidencias docs -maxdepth 2 -type f 2>/dev/null | sort

echo
echo "Verificação de chave secreta versionada:"
if git ls-files 2>/dev/null | grep -q "context_private.tenseal"; then
  echo "ATENÇÃO: context_private.tenseal está versionado. Remova antes do push."
else
  echo "OK: context_private.tenseal não está versionado."
fi
