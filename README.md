# Projeto HE Cloud — HealthData Analytics S.A.

## Objetivo

Este projeto implementa uma prova de conceito de infraestrutura de criptografia homomórfica em ambiente de nuvem local simulado com containers.

A solução utiliza Docker Compose, LocalStack simulando S3, TenSEAL com esquema BFV, cliente responsável por criptografia e descriptografia, servidor responsável apenas por processamento homomórfico e bucket S3 local para armazenamento dos dados criptografados.

## Arquitetura

O cliente gera o contexto criptográfico e a chave secreta. A chave secreta permanece apenas no cliente.

O cliente criptografa números inteiros por região e envia os dados criptografados para um bucket S3 local no LocalStack.

O servidor baixa apenas o contexto público e os ciphertexts, executa soma homomórfica por região e envia o resultado ainda criptografado de volta ao bucket.

O cliente baixa o resultado criptografado, descriptografa localmente e calcula a média final.

## Execução

Subir LocalStack:

```bash
docker compose up -d localstack

