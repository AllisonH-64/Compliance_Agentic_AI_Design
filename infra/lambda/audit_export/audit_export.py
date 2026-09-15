"""DynamoDB Streams -> S3 audit export.

Subscribed to the decision_history and review_history table streams (see
infra/api_stack.py). Writes each new history record as an immutable JSON object in
S3, partitioned by the date the event was actually recorded (not export time), so
the audit trail survives independently of the DynamoDB tables even if those are
ever modified or deleted.
"""

import json
import os
from datetime import datetime, timezone

import boto3

s3 = boto3.client("s3")
BUCKET = os.environ["AUDIT_BUCKET"]


def handler(event, context):
    batch_item_failures = []

    for record in event.get("Records", []):
        try:
            _export_record(record)
        except Exception:
            batch_item_failures.append({"itemIdentifier": record["eventID"]})

    return {"batchItemFailures": batch_item_failures}


def _export_record(record: dict) -> None:
    if record.get("eventName") != "INSERT":
        return  # history tables are append-only; nothing else is expected here

    new_image = record["dynamodb"].get("NewImage")
    if new_image is None:
        return

    table_name = record["eventSourceARN"].split("/")[1]
    item = _from_dynamodb_stream_item(new_image)

    recorded_at = item.get("recorded_at")
    date_partition = _date_partition(recorded_at)
    key = f"{table_name}/dt={date_partition}/{record['eventID']}.json"

    s3.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=json.dumps(item).encode("utf-8"),
        ContentType="application/json",
    )


def _date_partition(recorded_at: str | None) -> str:
    if recorded_at:
        try:
            return datetime.fromisoformat(recorded_at).strftime("%Y-%m-%d")
        except ValueError:
            pass

    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _from_dynamodb_stream_item(image: dict) -> dict:
    """Flat conversion from the DynamoDB Streams attribute-value wrapper to a plain
    dict. Every attribute this app writes (app/storage_dynamodb.py) is a String, so
    this doesn't need the full generality (Decimal handling, nested maps/lists) of
    boto3.dynamodb.types.TypeDeserializer."""
    result = {}
    for key, typed_value in image.items():
        _, value = next(iter(typed_value.items()))
        result[key] = value
    return result
