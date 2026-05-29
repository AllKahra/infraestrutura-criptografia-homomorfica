# Infraestrutura de Criptografia Homomórfica em Ambiente de Nuvem Simulado com Container

## Autora

Anna Beatriz Gallo  
Graduação em Segurança Cibernética  
Faculdade SENAI 1.34 Paulo Antonio Skaf

## Visão geral

Este projeto implementa uma prova de conceito de criptografia homomórfica em ambiente de nuvem local simulado com containers.

A solução utiliza Docker Compose, LocalStack, S3 local, Python, TenSEAL, cliente, servidor e componentes extras para simular uma arquitetura mais próxima de um ambiente corporativo.

## Componentes principais

- Cliente: gera o contexto criptográfico, mantém a chave secreta, criptografa os dados e descriptografa o resultado final.
- LocalStack: simula serviços de nuvem, incluindo S3, SQS, Lambda, IAM e Logs.
- Servidor: processa dados criptografados sem receber a chave secreta.
- API REST: componente extra para orquestração dos bônus.
- TenSEAL: biblioteca utilizada para criptografia homomórfica com esquema BFV.

## Estrutura do projeto

- client/
- server/
- api/
- bonus/
- docs/
- output/
- resultados/
- scripts/
- docker-compose.yml
- README.md
- ENTREGA.md

## Execução principal

Subir o LocalStack:

docker compose up -d localstack

Construir as imagens:

docker compose build client server

Criptografar e enviar os dados:

docker compose run --rm client encrypt

Executar o processamento homomórfico:

docker compose run --rm server

Descriptografar o resultado no cliente:

docker compose run --rm client decrypt

## Execução dos bônus

Subir LocalStack e API:

docker compose up -d localstack api

Enviar dados de múltiplas clínicas:

docker compose run --rm client python bonus_clinics_upload.py

Criar Lambda e fila SQS:

docker compose run --rm client python lambda_deploy.py

Invocar Lambda local:

docker compose run --rm client python lambda_invoke.py

Descriptografar resultado bônus:

docker compose run --rm client python bonus_decrypt.py

## Resultados principais

Região | Soma | Quantidade | Média
Norte | 90 | 2 | 45
Sul | 135 | 3 | 45
Leste | 105 | 3 | 35

## Bônus implementados

- API REST;
- Lambda local;
- SQS;
- multiplicação por constante;
- dados por clínica;
- monitoramento com logs estruturados;
- separação entre contexto público e contexto secreto.

## Segurança

A chave secreta permanece somente no cliente e não é versionada no GitHub.

O servidor, a API, a Lambda e o bucket trabalham somente com contexto público, metadados e ciphertexts.

## Documentação

O relatório final está na pasta docs/.

Os resultados principais e bônus estão nas pastas resultados/ e bonus/resultados/.
