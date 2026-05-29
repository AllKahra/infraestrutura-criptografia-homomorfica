import os
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
BONUS_MANIFEST_PATH = CLIENT_OUTPUT / "bonus_clinics_input_manifest.json"


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


def ensure_bucket(s3):
    try:
        s3.head_bucket(Bucket=BUCKET_NAME)
        print(f"[CLIENTE-BONUS] Bucket já existe: {BUCKET_NAME}")
    except ClientError:
        s3.create_bucket(Bucket=BUCKET_NAME)
        print(f"[CLIENTE-BONUS] Bucket criado: {BUCKET_NAME}")


def create_or_load_context():
    CLIENT_OUTPUT.mkdir(parents=True, exist_ok=True)

    if PRIVATE_CONTEXT_PATH.exists() and PUBLIC_CONTEXT_PATH.exists():
        print("[CLIENTE-BONUS] Contexto criptográfico existente encontrado.")
        context = ts.context_from(PRIVATE_CONTEXT_PATH.read_bytes())
        public_context_bytes = PUBLIC_CONTEXT_PATH.read_bytes()
        return context, public_context_bytes

    print("[CLIENTE-BONUS] Criando novo contexto criptográfico TenSEAL/BFV.")
    context = ts.context(
        ts.SCHEME_TYPE.BFV,
        poly_modulus_degree=4096,
        plain_modulus=1032193
    )

    private_context_bytes = context.serialize(save_secret_key=True)
    public_context_bytes = context.serialize(save_secret_key=False)

    PRIVATE_CONTEXT_PATH.write_bytes(private_context_bytes)
    PUBLIC_CONTEXT_PATH.write_bytes(public_context_bytes)

    return context, public_context_bytes


def main():
    s3 = get_s3_client()
    wait_for_s3(s3)
    ensure_bucket(s3)

    context, public_context_bytes = create_or_load_context()

    clinicas = {
        "Clinica_Alpha": {
            "Norte": [40, 50]
        },
        "Clinica_Beta": {
            "Sul": [30, 60, 45]
        },
        "Clinica_Gamma": {
            "Leste": [35, 42, 28]
        }
    }

    peso_constante = 2

    payload = {
        "empresa": "HealthData Analytics S.A.",
        "bonus": {
            "dados_por_clinica": True,
            "multiplicacao_por_constante": True,
            "peso_constante": peso_constante,
            "seguranca": "contexto privado permanece apenas no cliente"
        },
        "biblioteca": "TenSEAL",
        "esquema": "BFV",
        "input_key": "input/clinicas_dados_criptografados.json",
        "clinicas": {}
    }

    print("\n[CLIENTE-BONUS] Dados originais por clínica existem apenas no cliente:")
    print(json.dumps(clinicas, indent=2, ensure_ascii=False))

    for clinica, regioes in clinicas.items():
        payload["clinicas"][clinica] = {}

        for regiao, valores in regioes.items():
            payload["clinicas"][clinica][regiao] = []

            for index, valor in enumerate(valores, start=1):
                encrypted_vector = ts.bfv_vector(context, [valor])
                ciphertext_bytes = encrypted_vector.serialize()
                ciphertext_b64 = base64.b64encode(ciphertext_bytes).decode("utf-8")

                payload["clinicas"][clinica][regiao].append({
                    "id": f"{clinica.lower()}_{regiao.lower()}_{index}",
                    "ciphertext_b64": ciphertext_b64
                })

    s3.put_object(
        Bucket=BUCKET_NAME,
        Key="context/context_public_no_secret.tenseal",
        Body=public_context_bytes
    )

    s3.put_object(
        Bucket=BUCKET_NAME,
        Key="input/clinicas_dados_criptografados.json",
        Body=json.dumps(payload, indent=2).encode("utf-8")
    )

    BONUS_MANIFEST_PATH.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    print("\n[CLIENTE-BONUS] Upload bônus finalizado.")
    print("[CLIENTE-BONUS] Contexto público enviado ao S3.")
    print("[CLIENTE-BONUS] Dados criptografados por clínica enviados ao S3.")
    print("[CLIENTE-BONUS] Objeto criado: s3://healthdata-he/input/clinicas_dados_criptografados.json")
    print("[CLIENTE-BONUS] Chave secreta permaneceu apenas no cliente.")
    print(f"[CLIENTE-BONUS] Manifesto local salvo em: {BONUS_MANIFEST_PATH}")


if __name__ == "__main__":
    main()
