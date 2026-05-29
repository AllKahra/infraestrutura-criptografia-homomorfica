import os
import json
import time
import base64
import datetime
from pathlib import Path
from typing import Dict, Any

import boto3
import tenseal as ts
from fastapi import FastAPI
from botocore.config import Config
from botocore.exceptions import ClientError


app = FastAPI(title="HE Cloud Bonus API", version="1.0")

BUCKET_NAME = os.getenv("BUCKET_NAME", "healthdata-he")
S3_ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "http://localstack:4566")
QUEUE_NAME = os.getenv("SQS_QUEUE_NAME", "he-bonus-queue")
API_OUTPUT = Path("/app/api_output")
LOG_PATH = API_OUTPUT / "structured_logs_bonus.jsonl"


def now_iso():
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def log_event(event_type: str, details: Dict[str, Any]):
    API_OUTPUT.mkdir(parents=True, exist_ok=True)

    event = {
        "timestamp": now_iso(),
        "event_type": event_type,
        "component": "he-bonus-api",
        "details": details
    }

    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")

    print(json.dumps(event, ensure_ascii=False))


def get_client(service):
    return boto3.client(
        service,
        endpoint_url=S3_ENDPOINT_URL,
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", "test"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", "test"),
        region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
        config=Config(s3={"addressing_style": "path"})
    )


def wait_for_s3():
    s3 = get_client("s3")
    for _ in range(30):
        try:
            s3.list_buckets()
            return
        except Exception:
            time.sleep(2)
    raise RuntimeError("LocalStack/S3 indisponível.")


def ensure_queue():
    sqs = get_client("sqs")
    try:
        response = sqs.create_queue(QueueName=QUEUE_NAME)
    except ClientError:
        response = {"QueueUrl": sqs.get_queue_url(QueueName=QUEUE_NAME)["QueueUrl"]}

    return response["QueueUrl"]


def load_public_context(s3):
    response = s3.get_object(
        Bucket=BUCKET_NAME,
        Key="context/context_public_no_secret.tenseal"
    )
    return ts.context_from(response["Body"].read())


def bfv_from_b64(context, value):
    ciphertext = base64.b64decode(value)
    return ts.bfv_vector_from(context, ciphertext)


def b64_from_bfv(vector):
    return base64.b64encode(vector.serialize()).decode("utf-8")


def multiply_by_constant(vector, constant: int):
    try:
        return vector * constant
    except Exception:
        result = vector
        for _ in range(constant - 1):
            result = result + vector
        return result


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "HE Cloud Bonus API",
        "s3_endpoint": S3_ENDPOINT_URL,
        "bucket": BUCKET_NAME,
        "queue": QUEUE_NAME
    }


@app.post("/bonus/upload-metadata")
def upload_metadata(payload: Dict[str, Any]):
    wait_for_s3()
    s3 = get_client("s3")

    clinic = payload.get("clinic", "clinica_sem_nome")
    key = f"bonus/api_upload_metadata/{clinic}.json"

    body = {
        "received_at": now_iso(),
        "description": "Metadado recebido pela API REST. Dados sensíveis permanecem criptografados no fluxo principal.",
        "payload": payload
    }

    s3.put_object(
        Bucket=BUCKET_NAME,
        Key=key,
        Body=json.dumps(body, indent=2, ensure_ascii=False).encode("utf-8")
    )

    log_event("api_rest_upload_metadata", {
        "s3_key": key,
        "clinic": clinic
    })

    return {
        "status": "metadata_uploaded",
        "s3_key": key
    }


@app.post("/bonus/queue-process")
def queue_process(payload: Dict[str, Any] | None = None):
    wait_for_s3()

    if payload is None:
        payload = {}

    sqs = get_client("sqs")
    queue_url = ensure_queue()

    message = {
        "requested_at": now_iso(),
        "source": "api-rest",
        "action": "process_bonus_encrypted_data",
        "input_key": payload.get("input_key", "input/clinicas_dados_criptografados.json"),
        "output_key": payload.get("output_key", "output/bonus_resultados_criptografados.json"),
        "weight": int(payload.get("weight", 2))
    }

    sqs.send_message(
        QueueUrl=queue_url,
        MessageBody=json.dumps(message, ensure_ascii=False)
    )

    log_event("sqs_message_sent", {
        "queue_url": queue_url,
        "message": message
    })

    return {
        "status": "message_sent_to_sqs",
        "queue_url": queue_url,
        "message": message
    }


@app.post("/bonus/process")
def process_bonus(payload: Dict[str, Any] | None = None):
    wait_for_s3()

    if payload is None:
        payload = {}

    s3 = get_client("s3")
    input_key = payload.get("input_key", "input/clinicas_dados_criptografados.json")
    output_key = payload.get("output_key", "output/bonus_resultados_criptografados.json")
    weight = int(payload.get("weight", 2))

    log_event("processing_started", {
        "trigger_payload": payload,
        "input_key": input_key,
        "output_key": output_key,
        "weight": weight
    })

    public_context = load_public_context(s3)

    response = s3.get_object(
        Bucket=BUCKET_NAME,
        Key=input_key
    )

    encrypted_payload = json.loads(response["Body"].read().decode("utf-8"))

    encrypted_sums_by_clinic = {}
    encrypted_weighted_sums_by_clinic = {}
    encrypted_sums_by_region = {}
    encrypted_weighted_sums_by_region = {}
    counters_by_region = {}

    for clinic, regions in encrypted_payload["clinicas"].items():
        encrypted_sums_by_clinic[clinic] = {}
        encrypted_weighted_sums_by_clinic[clinic] = {}

        for region, records in regions.items():
            total = None
            weighted_total = None

            for record in records:
                encrypted_value = bfv_from_b64(public_context, record["ciphertext_b64"])
                encrypted_weighted = multiply_by_constant(encrypted_value, weight)

                if total is None:
                    total = encrypted_value
                    weighted_total = encrypted_weighted
                else:
                    total = total + encrypted_value
                    weighted_total = weighted_total + encrypted_weighted

                if region not in encrypted_sums_by_region:
                    encrypted_sums_by_region[region] = encrypted_value
                    encrypted_weighted_sums_by_region[region] = encrypted_weighted
                    counters_by_region[region] = 1
                else:
                    encrypted_sums_by_region[region] = encrypted_sums_by_region[region] + encrypted_value
                    encrypted_weighted_sums_by_region[region] = encrypted_weighted_sums_by_region[region] + encrypted_weighted
                    counters_by_region[region] += 1

            encrypted_sums_by_clinic[clinic][region] = {
                "ciphertext_b64": b64_from_bfv(total),
                "quantity": len(records)
            }

            encrypted_weighted_sums_by_clinic[clinic][region] = {
                "ciphertext_b64": b64_from_bfv(weighted_total),
                "quantity": len(records),
                "weight": weight
            }

    output = {
        "empresa": "HealthData Analytics S.A.",
        "bonus_executados": [
            "API REST",
            "Lambda local",
            "SQS",
            "Multiplicação por constante",
            "Dados por clínica",
            "Monitoramento",
            "Segurança"
        ],
        "peso_constante": weight,
        "observacao_seguranca": "O processamento usou apenas o contexto público. A chave secreta permaneceu no cliente.",
        "input_key": input_key,
        "output_key": output_key,
        "encrypted_sums_by_clinic": encrypted_sums_by_clinic,
        "encrypted_weighted_sums_by_clinic": encrypted_weighted_sums_by_clinic,
        "encrypted_sums_by_region": {
            region: {
                "ciphertext_b64": b64_from_bfv(vector),
                "quantity": counters_by_region[region]
            }
            for region, vector in encrypted_sums_by_region.items()
        },
        "encrypted_weighted_sums_by_region": {
            region: {
                "ciphertext_b64": b64_from_bfv(vector),
                "quantity": counters_by_region[region],
                "weight": weight
            }
            for region, vector in encrypted_weighted_sums_by_region.items()
        }
    }

    s3.put_object(
        Bucket=BUCKET_NAME,
        Key=output_key,
        Body=json.dumps(output, indent=2).encode("utf-8")
    )

    log_event("processing_finished", {
        "output_key": output_key,
        "clinics_processed": list(encrypted_payload["clinicas"].keys()),
        "regions_processed": list(encrypted_sums_by_region.keys()),
        "weight": weight,
        "secret_key_used": False
    })

    return {
        "status": "processed",
        "output_key": output_key,
        "clinics_processed": list(encrypted_payload["clinicas"].keys()),
        "regions_processed": list(encrypted_sums_by_region.keys()),
        "weight": weight,
        "secret_key_used": False
    }
