import os
import json
import boto3


ENDPOINT_URL = os.getenv("S3_ENDPOINT_URL", "http://localstack:4566")

lamb = boto3.client(
    "lambda",
    endpoint_url=ENDPOINT_URL,
    aws_access_key_id="test",
    aws_secret_access_key="test",
    region_name="us-east-1"
)

payload = {
    "source": "manual-validation",
    "message": "Invocação manual para validar Lambda local",
    "input_key": "input/clinicas_dados_criptografados.json",
    "output_key": "output/bonus_resultados_criptografados.json",
    "weight": 2
}

response = lamb.invoke(
    FunctionName="he_bonus_processor",
    InvocationType="RequestResponse",
    Payload=json.dumps(payload).encode("utf-8")
)

print("[LAMBDA-INVOKE] StatusCode:", response["StatusCode"])
print("[LAMBDA-INVOKE] Payload:")
print(response["Payload"].read().decode("utf-8"))
