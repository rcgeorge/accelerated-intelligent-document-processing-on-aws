# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""
WebSocket Manager Lambda for GraphQL subscriptions.

Handles $connect, $disconnect, subscribe, and unsubscribe routes.
Validates JWT tokens on connect and manages subscription records in DynamoDB.
"""

import json
import logging
import os
import time
import urllib.request

import boto3

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

dynamodb = boto3.resource("dynamodb")
connections_table = dynamodb.Table(os.environ["CONNECTIONS_TABLE"])

USER_POOL_ID = os.environ.get("USER_POOL_ID", "")
USER_POOL_CLIENT_ID = os.environ.get("USER_POOL_CLIENT_ID", "")
REGION = os.environ.get("AWS_REGION", "us-east-1")

# Cache JWKS keys
_jwks_cache = None


def _get_jwks():
    """Fetch and cache JWKS from Cognito."""
    global _jwks_cache
    if _jwks_cache is not None:
        return _jwks_cache

    url = f"https://cognito-idp.{REGION}.amazonaws.com/{USER_POOL_ID}/.well-known/jwks.json"
    with urllib.request.urlopen(url) as response:  # noqa: S310
        _jwks_cache = json.loads(response.read())
    return _jwks_cache


def _validate_token_basic(token):
    """
    Basic JWT validation - decode payload without full signature verification.
    API Gateway should handle full JWT validation; this extracts claims.
    For production, use python-jose or aws-jwt-verify for full validation.
    """
    import base64

    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid JWT format")

    # Decode payload (part 1)
    payload = parts[1]
    # Add padding
    payload += "=" * (4 - len(payload) % 4)
    decoded = base64.urlsafe_b64decode(payload)
    claims = json.loads(decoded)

    # Basic expiry check
    if "exp" in claims and claims["exp"] < time.time():
        raise ValueError("Token expired")

    return claims


# Connection TTL: 2 hours (WebSocket connections timeout after ~10 min idle,
# but we set a generous TTL for DynamoDB cleanup)
CONNECTION_TTL_SECONDS = 7200


def handler(event, context):
    """Main WebSocket handler dispatching by route key."""
    route_key = event.get("requestContext", {}).get("routeKey")
    connection_id = event.get("requestContext", {}).get("connectionId")

    logger.info(f"Route: {route_key}, ConnectionId: {connection_id}")

    try:
        if route_key == "$connect":
            return handle_connect(event, connection_id)
        elif route_key == "$disconnect":
            return handle_disconnect(connection_id)
        elif route_key == "subscribe":
            return handle_subscribe(event, connection_id)
        elif route_key == "unsubscribe":
            return handle_unsubscribe(event, connection_id)
        else:
            return {"statusCode": 400, "body": f"Unknown route: {route_key}"}
    except Exception:
        logger.exception(f"Error handling route {route_key}")
        return {"statusCode": 500, "body": "Internal server error"}


def handle_connect(event, connection_id):
    """
    Handle $connect: validate JWT from query string and store connection.
    Token is passed as ?token=<jwt> since WebSocket doesn't support headers.
    """
    query_params = event.get("queryStringParameters") or {}
    token = query_params.get("token")

    if not token:
        logger.warning("No token provided on connect")
        return {"statusCode": 401, "body": "Unauthorized: No token"}

    try:
        claims = _validate_token_basic(token)
    except Exception as e:
        logger.warning(f"Token validation failed: {e}")
        return {"statusCode": 401, "body": f"Unauthorized: {e}"}

    # Extract user info from claims
    sub = claims.get("sub", "")
    email = claims.get("email", "")
    username = claims.get("cognito:username", sub)
    groups = claims.get("cognito:groups", [])
    if isinstance(groups, str):
        groups = [groups]

    # Store connection record
    ttl = int(time.time()) + CONNECTION_TTL_SECONDS
    connections_table.put_item(
        Item={
            "connectionId": connection_id,
            "sub": sub,
            "email": email,
            "username": username,
            "groups": groups,
            "connectedAt": int(time.time()),
            "ttl": ttl,
        }
    )

    logger.info(f"Connected: {connection_id} (user: {email})")
    return {"statusCode": 200, "body": "Connected"}


def handle_disconnect(connection_id):
    """Handle $disconnect: remove connection and all its subscriptions."""
    try:
        # Delete the connection record
        connections_table.delete_item(Key={"connectionId": connection_id})

        # Also delete any subscription records for this connection
        # (subscriptions are stored as separate items with topic as sort key)
        # Query by connectionId to find all subscriptions
        response = connections_table.query(
            KeyConditionExpression="connectionId = :cid",
            ExpressionAttributeValues={":cid": connection_id},
        )
        for item in response.get("Items", []):
            connections_table.delete_item(
                Key={"connectionId": connection_id}
            )

    except Exception:
        logger.exception(f"Error cleaning up connection {connection_id}")

    logger.info(f"Disconnected: {connection_id}")
    return {"statusCode": 200, "body": "Disconnected"}


def handle_subscribe(event, connection_id):
    """
    Handle subscribe: register subscription for a topic.
    Message body: { "action": "subscribe", "topic": "onUpdateDocument", "variables": {...} }
    """
    body = json.loads(event.get("body", "{}"))
    topic = body.get("topic")
    variables = body.get("variables", {})
    subscription_id = body.get("id", topic)  # Client-provided subscription ID

    if not topic:
        return {"statusCode": 400, "body": "Missing topic"}

    # Build the topic key (e.g., "onAgentChatMessageUpdate#session123")
    topic_key = topic
    if topic == "onAgentChatMessageUpdate" and variables.get("sessionId"):
        topic_key = f"{topic}#{variables['sessionId']}"
    elif topic == "onAgentJobComplete" and variables.get("jobId"):
        topic_key = f"{topic}#{variables['jobId']}"
    elif topic == "onDiscoveryJobStatusChange" and variables.get("jobId"):
        topic_key = f"{topic}#{variables['jobId']}"

    ttl = int(time.time()) + CONNECTION_TTL_SECONDS
    connections_table.put_item(
        Item={
            "connectionId": connection_id,
            "topic": topic_key,
            "subscriptionId": subscription_id,
            "variables": variables,
            "subscribedAt": int(time.time()),
            "ttl": ttl,
        }
    )

    logger.info(f"Subscribed: {connection_id} -> {topic_key}")
    return {"statusCode": 200, "body": json.dumps({"subscribed": topic_key})}


def handle_unsubscribe(event, connection_id):
    """
    Handle unsubscribe: remove subscription for a topic.
    Message body: { "action": "unsubscribe", "id": "subscription-id" }
    """
    body = json.loads(event.get("body", "{}"))
    subscription_id = body.get("id")

    if not subscription_id:
        return {"statusCode": 400, "body": "Missing subscription id"}

    # Find and delete the subscription by scanning for this connection's subscriptions
    # with matching subscription ID
    response = connections_table.query(
        IndexName="TopicIndex",
        KeyConditionExpression="topic = :topic",
        FilterExpression="connectionId = :cid AND subscriptionId = :sid",
        ExpressionAttributeValues={
            ":topic": subscription_id,
            ":cid": connection_id,
            ":sid": subscription_id,
        },
    )

    for item in response.get("Items", []):
        connections_table.delete_item(
            Key={"connectionId": item["connectionId"]}
        )

    logger.info(f"Unsubscribed: {connection_id} from {subscription_id}")
    return {"statusCode": 200, "body": json.dumps({"unsubscribed": subscription_id})}
