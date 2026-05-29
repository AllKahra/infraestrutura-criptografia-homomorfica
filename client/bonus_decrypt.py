import os
import json
import time
import base64
from pathlib import Path

import boto3
import tenseal as ts
from botocore.config import Config


BUCKET_NAME = os.getenv("BUCKET_NAME", "healthdata-he")
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "http://localstack:4566")
CLIENT_OUTPUT = Path("/app/client_output")
PRIVATE_CONTEXT_PATH = CLIENT_OUTPUT / "context_private.tenseal"
BONUS_RESULT_PATH = CLIENT_OUTPUT / "bonus_resultado_final.json"


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
    print("[CLIENTE-BONUS] Aguardando LocalStack/S3 ficar disponível...")
    for _ in range(30):
        try:
            s3.list_buckets()
            print("[CLIENTE-BONUS] LocalStack/S3 disponível.")
            return
        except Exception:
            time.sleep(2)
    raise RuntimeError("LocalStack/S3 não ficou disponível a tempo.")


def decrypt_vector(context, b64_value):
    encrypted_bytes = base64.b64decode(b64_value)
    encrypted_vector = ts.bfv_vector_from(context, encrypted_bytes)
    return int(encrypted_vector.decrypt()[0])


def main():
    if not PRIVATE_CONTEXT_PATH.exists():
        raise FileNotFoundError("Contexto privado não encontrado no cliente.")

    s3 = get_s3_client()
    wait_for_s3(s3)

    response = s3.get_object(
        Bucket=BUCKET_NAME,
        Key="output/bonus_resultados_criptografados.json"
    )

    payload = json.loads(response["Body"].read().decode("utf-8"))
    context = ts.context_from(PRIVATE_CONTEXT_PATH.read_bytes())

    final = {
        "por_clinica": {},
        "por_regiao": {}
    }

    print("\n[CLIENTE-BONUS] Resultado bônus descriptografado")
    print("=================================================")
    print(f"Peso constante aplicado: {payload['peso_constante']}")
    print()

    print("Resultado por clínica:")
    print("----------------------")
    print(f"{'Clínica':<18} {'Região':<10} {'Soma':<10} {'Ponderada':<12} {'Qtd':<6} {'Média':<10}")

    for clinica, regioes in payload["encrypted_sums_by_clinic"].items():
        final["por_clinica"][clinica] = {}

        for regiao, item in regioes.items():
            soma = decrypt_vector(context, item["ciphertext_b64"])
            ponderada = decrypt_vector(
                context,
                payload["encrypted_weighted_sums_by_clinic"][clinica][regiao]["ciphertext_b64"]
            )
            quantidade = item["quantity"]
            media = soma / quantidade

            final["por_clinica"][clinica][regiao] = {
                "soma": soma,
                "soma_ponderada": ponderada,
                "quantidade": quantidade,
                "media": media
            }

            print(f"{clinica:<18} {regiao:<10} {soma:<10} {ponderada:<12} {quantidade:<6} {media:<10}")

    print("\nResultado agregado por região:")
    print("------------------------------")
    print(f"{'Região':<10} {'Soma':<10} {'Ponderada':<12} {'Qtd':<6} {'Média':<10}")

    for regiao, item in payload["encrypted_sums_by_region"].items():
        soma = decrypt_vector(context, item["ciphertext_b64"])
        ponderada = decrypt_vector(
            context,
            payload["encrypted_weighted_sums_by_region"][regiao]["ciphertext_b64"]
        )
        quantidade = item["quantity"]
        media = soma / quantidade

        final["por_regiao"][regiao] = {
            "soma": soma,
            "soma_ponderada": ponderada,
            "quantidade": quantidade,
            "media": media
        }

        print(f"{regiao:<10} {soma:<10} {ponderada:<12} {quantidade:<6} {media:<10}")

    BONUS_RESULT_PATH.write_text(
        json.dumps(final, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print(f"\n[CLIENTE-BONUS] Resultado bônus salvo em: {BONUS_RESULT_PATH}")
    print("[CLIENTE-BONUS] Descriptografia ocorreu apenas no cliente.")


if __name__ == "__main__":
    main()
