# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
WebSocket Publisher Lambda - pushes DynamoDB Stream events to WebSocket subscribers.

Triggered by DynamoDB Streams on the TrackingTable. Maps stream events to
subscription topics and posts data to subscribed WebSocket connections.

Can also be invoked directly by backend Lambdas for non-stream subscriptions
(e.g., agent chat messages).
"""

import json
import logging
import os

import boto3
from boto3.dynamodb.types import TypeDeserializer
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

dynamodb = boto3.resource("dynamodb")
connections_table = dynamodb.Table(os.environ["CONNECTIONS_TABLE"])
api_endpoint = os.environ["WEBSOCKET_API_ENDPOINT"]

# API Gateway Management API client for posting to connections
apigw_management = boto3.client(
    "apigatewaymanagementapi",
    endpoint_url=api_endpoint,
)

deserializer = TypeDeserializer()


def deserialize_dynamodb_record(record):
    """Convert DynamoDB stream record to plain Python dict."""
    return {k: deserializer.deserialize(v) for k, v in record.items()}


def handler(event, context):
    """
    Handle DynamoDB Stream events or direct invocations.

    DynamoDB Stream event:
        { "Records": [{ "eventName": "INSERT"|"MODIFY", "dynamodb": {...} }] }

    Direct invocation (for agent chat, etc.):
        { "topic": "onAgentChatMessageUpdate#sessionId", "data": {...} }
    """
    # Direct invocation path
    if "topic" in event and "data" in event:
        return handle_direct_publish(event["topic"], event["data"])

    # DynamoDB Stream path
    records = event.get("Records", [])
    if not records:
        return {"statusCode": 200, "body": "No records"}

    for record in records:
        try:
            process_stream_record(record)
        except Exception:
            logger.exception(f"Error processing record: {record.get('eventID')}")

    return {"statusCode": 200, "body": f"Processed {len(records)} records"}


def process_stream_record(record):
    """Process a single DynamoDB Stream record and publish to subscribers."""
    event_name = record.get("eventName")
    dynamodb_record = record.get("dynamodb", {})

    new_image = dynamodb_record.get("NewImage")
    if not new_image:
        return

    item = deserialize_dynamodb_record(new_image)
    pk = item.get("PK", "")

    # Determine topics based on the record
    topics = []

    if pk.startswith("doc#"):
        if event_name == "INSERT":
            topics.append("onCreateDocument")
        elif event_name == "MODIFY":
            topics.append("onUpdateDocument")
    elif pk.startswith("discovery#"):
        job_id = pk.replace("discovery#", "")
        topics.append(f"onDiscoveryJobStatusChange#{job_id}")
    elif pk.startswith("job#"):
        job_id = pk.replace("job#", "")
        status = item.get("status", "")
        if status in ("COMPLETED", "FAILED"):
            topics.append(f"onAgentJobComplete#{job_id}")

    # Publish to all matching topics
    for topic in topics:
        publish_to_topic(topic, item)


def handle_direct_publish(topic, data):
    """Handle direct invocation for publishing to a specific topic."""
    publish_to_topic(topic, data)
    return {"statusCode": 200, "body": f"Published to {topic}"}


def publish_to_topic(topic, data):
    """Look up subscribers for a topic and post data to their connections."""
    # Query the TopicIndex GSI
    try:
        response = connections_table.query(
            IndexName="TopicIndex",
            KeyConditionExpression="topic = :topic",
            ExpressionAttributeValues={":topic": topic},
        )
    except ClientError:
        logger.exception(f"Error querying subscriptions for topic: {topic}")
        return

    subscribers = response.get("Items", [])
    if not subscribers:
        logger.debug(f"No subscribers for topic: {topic}")
        return

    logger.info(f"Publishing to {len(subscribers)} subscribers for topic: {topic}")

    # Build the message payload matching AppSync subscription format
    # Extract the subscription name from the topic (e.g., "onUpdateDocument" from "onUpdateDocument")
    subscription_name = topic.split("#")[0]
    message = json.dumps(
        {
            "type": "data",
            "id": topic,
            "payload": {
                "data": {subscription_name: _serialize_for_json(data)}
            },
        },
        default=str,
    )

    stale_connections = []

    for subscriber in subscribers:
        connection_id = subscriber["connectionId"]
        try:
            apigw_management.post_to_connection(
                ConnectionId=connection_id,
                Data=message.encode("utf-8"),
            )
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code == "GoneException" or "410" in str(e):
                # Connection is stale - mark for cleanup
                stale_connections.append(connection_id)
                logger.debug(f"Stale connection: {connection_id}")
            else:
                logger.error(f"Error posting to {connection_id}: {e}")

    # Clean up stale connections
    for conn_id in stale_connections:
        try:
            connections_table.delete_item(Key={"connectionId": conn_id})
        except ClientError:
            logger.exception(f"Error cleaning up stale connection: {conn_id}")


def _serialize_for_json(data):
    """Convert DynamoDB-specific types (Decimal, sets) to JSON-safe types."""
    if isinstance(data, dict):
        return {k: _serialize_for_json(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [_serialize_for_json(item) for item in data]
    elif isinstance(data, set):
        return [_serialize_for_json(item) for item in data]
    elif hasattr(data, "as_integer_ratio"):
        # Decimal or float
        if data == int(data):
            return int(data)
        return float(data)
    return data
