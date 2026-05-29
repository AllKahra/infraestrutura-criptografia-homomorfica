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
SERVER_OUTPUT = Path("/app/server_output")
SERVER_LOG_PATH = SERVER_OUTPUT / "server_log.json"


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
    print("[SERVIDOR] Aguardando LocalStack/S3 ficar disponível...")
    for _ in range(30):
        try:
            s3.list_buckets()
            print("[SERVIDOR] LocalStack/S3 disponível.")
            return
        except Exception:
            time.sleep(2)
    raise RuntimeError("LocalStack/S3 não ficou disponível a tempo.")


def main():
    SERVER_OUTPUT.mkdir(parents=True, exist_ok=True)

    s3 = get_s3_client()
    wait_for_s3(s3)

    print("\n[SERVIDOR] Baixando contexto público, sem chave secreta...")

    public_context_response = s3.get_object(
        Bucket=BUCKET_NAME,
        Key="context/context_public_no_secret.tenseal"
    )

    public_context_bytes = public_context_response["Body"].read()
    public_context = ts.context_from(public_context_bytes)

    print("[SERVIDOR] Contexto público carregado.")
    print("[SERVIDOR] Servidor NÃO recebeu chave secreta.")

    print("\n[SERVIDOR] Baixando dados criptografados...")

    encrypted_data_response = s3.get_object(
        Bucket=BUCKET_NAME,
        Key="input/dados_criptografados.json"
    )

    encrypted_payload = json.loads(
        encrypted_data_response["Body"].read().decode("utf-8")
    )

    encrypted_sums = {}
    decrypt_tests = {}

    print("\n[SERVIDOR] Iniciando soma homomórfica por região...")

    for regiao, registros in encrypted_payload["regions"].items():
        encrypted_total = None

        for registro in registros:
            ciphertext_bytes = base64.b64decode(registro["ciphertext_b64"])
            encrypted_value = ts.bfv_vector_from(public_context, ciphertext_bytes)

            if encrypted_total is None:
                encrypted_total = encrypted_value
            else:
                encrypted_total = encrypted_total + encrypted_value

        try:
            encrypted_total.decrypt()
            decrypt_tests[regiao] = "ERRO: servidor conseguiu descriptografar, isso não deveria acontecer."
        except Exception as error:
            decrypt_tests[regiao] = (
                "OK: servidor não conseguiu descriptografar sem chave secreta. "
                f"Erro observado: {type(error).__name__}"
            )

        encrypted_total_b64 = base64.b64encode(
            encrypted_total.serialize()
        ).decode("utf-8")

        encrypted_sums[regiao] = {
            "ciphertext_b64": encrypted_total_b64,
            "quantity": encrypted_payload["quantities"][regiao]
        }

        print(f"\n[SERVIDOR] Soma criptografada gerada para a região: {regiao}")
        print(f"[SERVIDOR] Teste de descriptografia: {decrypt_tests[regiao]}")

    result_payload = {
        "empresa": "HealthData Analytics S.A.",
        "processamento": "Soma homomórfica por região",
        "observacao": "Resultado ainda criptografado. Descriptografia deve ocorrer somente no cliente.",
        "encrypted_sums": encrypted_sums,
        "server_decrypt_tests": decrypt_tests
    }

    s3.put_object(
        Bucket=BUCKET_NAME,
        Key="output/resultados_criptografados.json",
        Body=json.dumps(result_payload, indent=2).encode("utf-8")
    )

    SERVER_LOG_PATH.write_text(
        json.dumps(result_payload, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print("\n[SERVIDOR] Resultado criptografado enviado de volta ao bucket S3.")
    print("[SERVIDOR] Objeto criado: s3://healthdata-he/output/resultados_criptografados.json")
    print(f"[SERVIDOR] Log salvo em: {SERVER_LOG_PATH}")


if __name__ == "__main__":
    main()
