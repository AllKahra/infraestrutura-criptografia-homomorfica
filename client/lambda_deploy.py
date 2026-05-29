import io
import os
import json
import time
import zipfile

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "http://localstack:4566")
REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
QUEUE_NAME = os.getenv("SQS_QUEUE_NAME", "he-bonus-queue")
FUNCTION_NAME = "he_bonus_processor"
ROLE_NAME = "he_bonus_lambda_role"


def client(service):
    return boto3.client(
        service,
        endpoint_url=ENDPOINT_URL,
        aws_access_key_id="test",
        aws_secret_access_key="test",
        region_name=REGION,
        config=Config(s3={"addressing_style": "path"})
    )


def wait_localstack():
    s3 = client("s3")
    for _ in range(30):
        try:
            s3.list_buckets()
            return
        except Exception:
            time.sleep(2)
    raise RuntimeError("LocalStack não respondeu.")


def create_lambda_zip():
    code = r'''
import os
import json
import urllib.request


def handler(event, context):
    api_url = os.environ.get("API_URL", "http://he-api:8000/bonus/process")

    payload = {
        "source": "localstack-lambda",
        "message": "Lambda local acionada para processar dados criptografados",
        "input_key": "input/clinicas_dados_criptografados.json",
        "output_key": "output/bonus_resultados_criptografados.json",
        "weight": 2,
        "event": event
    }

    request = urllib.request.Request(
        api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    with urllib.request.urlopen(request, timeout=120) as response:
        response_body = response.read().decode("utf-8")

    print(json.dumps({
        "lambda": "he_bonus_processor",
        "status": "processamento_disparado",
        "api_response": response_body[:800]
    }, ensure_ascii=False))

    return {
        "statusCode": 200,
        "body": response_body
    }
'''

    buffer = io.BytesIO()

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        info = zipfile.ZipInfo("lambda_function.py")
        info.create_system = 3
        info.external_attr = 0o100644 << 16
        z.writestr(info, code)

    return buffer.getvalue()


def main():
    wait_localstack()

    iam = client("iam")
    lamb = client("lambda")
    sqs = client("sqs")

    assume_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "lambda.amazonaws.com"},
                "Action": "sts:AssumeRole"
            }
        ]
    }

    try:
        role = iam.create_role(
            RoleName=ROLE_NAME,
            AssumeRolePolicyDocument=json.dumps(assume_policy)
        )
        role_arn = role["Role"]["Arn"]
        print(f"[LAMBDA-DEPLOY] IAM Role criada: {role_arn}")
    except ClientError:
        role = iam.get_role(RoleName=ROLE_NAME)
        role_arn = role["Role"]["Arn"]
        print(f"[LAMBDA-DEPLOY] IAM Role já existia: {role_arn}")

    try:
        sqs.create_queue(QueueName=QUEUE_NAME)
        print(f"[LAMBDA-DEPLOY] Fila SQS criada: {QUEUE_NAME}")
    except ClientError:
        print(f"[LAMBDA-DEPLOY] Fila SQS já existia: {QUEUE_NAME}")

    queue_url = sqs.get_queue_url(QueueName=QUEUE_NAME)["QueueUrl"]
    queue_attrs = sqs.get_queue_attributes(
        QueueUrl=queue_url,
        AttributeNames=["QueueArn"]
    )
    queue_arn = queue_attrs["Attributes"]["QueueArn"]

    try:
        lamb.delete_function(FunctionName=FUNCTION_NAME)
        print("[LAMBDA-DEPLOY] Lambda antiga removida.")
        time.sleep(5)
    except ClientError:
        print("[LAMBDA-DEPLOY] Nenhuma Lambda antiga para remover.")

    lamb.create_function(
        FunctionName=FUNCTION_NAME,
        Runtime="python3.11",
        Role=role_arn,
        Handler="lambda_function.handler",
        Code={"ZipFile": create_lambda_zip()},
        Timeout=120,
        MemorySize=256,
        Environment={
            "Variables": {
                "API_URL": "http://he-api:8000/bonus/process"
            }
        }
    )

    print(f"[LAMBDA-DEPLOY] Função Lambda criada: {FUNCTION_NAME}")
    time.sleep(8)

    mappings = lamb.list_event_source_mappings(
        FunctionName=FUNCTION_NAME
    ).get("EventSourceMappings", [])

    for mapping in mappings:
        lamb.delete_event_source_mapping(UUID=mapping["UUID"])

    lamb.create_event_source_mapping(
        EventSourceArn=queue_arn,
        FunctionName=FUNCTION_NAME,
        Enabled=True,
        BatchSize=1
    )

    print("[LAMBDA-DEPLOY] Event source mapping criado: SQS -> Lambda")
    print(f"[LAMBDA-DEPLOY] Queue URL: {queue_url}")
    print(f"[LAMBDA-DEPLOY] Queue ARN: {queue_arn}")
    print("[LAMBDA-DEPLOY] Deploy finalizado com permissões corrigidas.")


if __name__ == "__main__":
    main()
