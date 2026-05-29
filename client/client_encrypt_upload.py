import os
import sys
import json
import time
import base64
from pathlib import Path

import boto3
import tenseal as ts
from botocore.config import Config
from botocore.exceptions import ClientError


BUCKET_NAME = os.getenv("BUCKET_NAME", "healthdata-he")
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "http://localstack:4566")
CLIENT_OUTPUT = Path("/app/client_output")

PRIVATE_CONTEXT_PATH = CLIENT_OUTPUT / "context_private.tenseal"
PUBLIC_CONTEXT_PATH = CLIENT_OUTPUT / "context_public_no_secret.tenseal"
FINAL_RESULT_PATH = CLIENT_OUTPUT / "resultado_final.json"


def get_s3_client():
    return boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT_URL,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", "test"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", "test"),
        region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
        config=Config(s3={"addressing_style": "path"})
    )


def wait_for_s3(s3):
    print("[CLIENTE] Aguardando LocalStack/S3 ficar disponível...")
    for _ in range(30):
        try:
            s3.list_buckets()
            print("[CLIENTE] LocalStack/S3 disponível.")
            return
        except Exception:
            time.sleep(2)
    raise RuntimeError("LocalStack/S3 não ficou disponível a tempo.")


def ensure_bucket(s3):
    try:
        s3.head_bucket(Bucket=BUCKET_NAME)
        print(f"[CLIENTE] Bucket já existe: {BUCKET_NAME}")
    except ClientError:
        s3.create_bucket(Bucket=BUCKET_NAME)
        print(f"[CLIENTE] Bucket criado: {BUCKET_NAME}")


def create_bfv_context():
    print("[CLIENTE] Criando contexto criptográfico TenSEAL/BFV para números inteiros...")

    context = ts.context(
        ts.SCHEME_TYPE.BFV,
        poly_modulus_degree=4096,
        plain_modulus=1032193
    )

    return context


def encrypt_and_upload():
    CLIENT_OUTPUT.mkdir(parents=True, exist_ok=True)

    s3 = get_s3_client()
    wait_for_s3(s3)
    ensure_bucket(s3)

    dados = {
        "Norte": [40, 50],
        "Sul": [30, 60, 45],
        "Leste": [35, 42, 28]
    }

    print("\n[CLIENTE] Dados originais existem apenas no cliente:")
    print(json.dumps(dados, indent=2, ensure_ascii=False))

    context = create_bfv_context()

    private_context_bytes = context.serialize(save_secret_key=True)
    public_context_bytes = context.serialize(save_secret_key=False)

    PRIVATE_CONTEXT_PATH.write_bytes(private_context_bytes)
    PUBLIC_CONTEXT_PATH.write_bytes(public_context_bytes)

    print(f"\n[CLIENTE] Contexto privado salvo localmente em: {PRIVATE_CONTEXT_PATH}")
    print(f"[CLIENTE] Contexto público salvo localmente em: {PUBLIC_CONTEXT_PATH}")

    s3.put_object(
        Bucket=BUCKET_NAME,
        Key="context/context_public_no_secret.tenseal",
        Body=public_context_bytes
    )

    print("\n[CLIENTE] Contexto público enviado ao S3.")
    print("[CLIENTE] A chave secreta NÃO foi enviada ao S3 e NÃO será enviada ao servidor.")

    encrypted_payload = {
        "empresa": "HealthData Analytics S.A.",
        "biblioteca": "TenSEAL",
        "esquema": "BFV",
        "observacao": "Dados criptografados no cliente. Servidor não possui chave secreta.",
        "regions": {},
        "quantities": {}
    }

    for regiao, valores in dados.items():
        encrypted_payload["regions"][regiao] = []
        encrypted_payload["quantities"][regiao] = len(valores)

        for index, valor in enumerate(valores, start=1):
            encrypted_vector = ts.bfv_vector(context, [valor])
            ciphertext_bytes = encrypted_vector.serialize()
            ciphertext_b64 = base64.b64encode(ciphertext_bytes).decode("utf-8")

            encrypted_payload["regions"][regiao].append({
                "id": f"{regiao.lower()}_{index}",
                "ciphertext_b64": ciphertext_b64
            })

    payload_bytes = json.dumps(encrypted_payload, indent=2).encode("utf-8")

    s3.put_object(
        Bucket=BUCKET_NAME,
        Key="input/dados_criptografados.json",
        Body=payload_bytes
    )

    print("\n[CLIENTE] Dados criptografados enviados para o bucket S3 local.")
    print("[CLIENTE] Objeto criado: s3://healthdata-he/input/dados_criptografados.json")

    exemplo = encrypted_payload["regions"]["Norte"][0]["ciphertext_b64"][:120]
    print("\n[CLIENTE] Exemplo de ciphertext armazenado, trecho inicial:")
    print(exemplo + "...")

    print("\n[CLIENTE] Etapa de criptografia e upload finalizada.")


def download_and_decrypt_result():
    CLIENT_OUTPUT.mkdir(parents=True, exist_ok=True)

    if not PRIVATE_CONTEXT_PATH.exists():
        raise FileNotFoundError(
            "Contexto privado não encontrado. Execute primeiro: docker compose run --rm client encrypt"
        )

    s3 = get_s3_client()
    wait_for_s3(s3)

    print("\n[CLIENTE] Baixando resultado criptografado do S3...")

    response = s3.get_object(
        Bucket=BUCKET_NAME,
        Key="output/resultados_criptografados.json"
    )

    encrypted_result = json.loads(response["Body"].read().decode("utf-8"))

    private_context = ts.context_from(PRIVATE_CONTEXT_PATH.read_bytes())

    final_results = {}

    print("\n[CLIENTE] Descriptografando resultado final com a chave secreta local...\n")

    for regiao, item in encrypted_result["encrypted_sums"].items():
        ciphertext_bytes = base64.b64decode(item["ciphertext_b64"])
        encrypted_sum = ts.bfv_vector_from(private_context, ciphertext_bytes)

        soma = int(encrypted_sum.decrypt()[0])
        quantidade = int(item["quantity"])
        media = soma / quantidade

        final_results[regiao] = {
            "soma": soma,
            "quantidade": quantidade,
            "media": media
        }

    print("Resultado final em texto claro:")
    print("--------------------------------")
    print(f"{'Região':<10} {'Soma':<10} {'Quantidade':<12} {'Média':<10}")

    for regiao, valores in final_results.items():
        print(
            f"{regiao:<10} "
            f"{valores['soma']:<10} "
            f"{valores['quantidade']:<12} "
            f"{valores['media']:<10}"
        )

    FINAL_RESULT_PATH.write_text(
        json.dumps(final_results, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print(f"\n[CLIENTE] Resultado final salvo em: {FINAL_RESULT_PATH}")


def main():
    if len(sys.argv) < 2:
        action = "encrypt"
    else:
        action = sys.argv[1].lower()

    if action == "encrypt":
        encrypt_and_upload()
    elif action == "decrypt":
        download_and_decrypt_result()
    else:
        raise ValueError("Ação inválida. Use: encrypt ou decrypt")


if __name__ == "__main__":
    main()
