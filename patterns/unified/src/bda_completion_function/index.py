# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json
import logging
import boto3
import os
from idp_common import metrics

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))
logging.getLogger('idp_common.bedrock.client').setLevel(os.environ.get("BEDROCK_LOG_LEVEL", "INFO"))
# Get LOG_LEVEL from environment variable with INFO as default

dynamodb = boto3.resource('dynamodb')
stepfunctions = boto3.client('stepfunctions')
tracking_table = dynamodb.Table(os.environ['TRACKING_TABLE'])

METRIC_NAMESPACE = os.environ['METRIC_NAMESPACE']

def get_task_token(object_key: str):
    """Look up the Step Functions task token recorded for this BDA job.

    When the input was staged under a sanitized key (for BDA URI
    compatibility), the tasktoken record is keyed on the sanitized
    key (which is what BDA echoes back in its completion event) and
    carries the original key under ``OriginalObjectKey``. We return
    both so the caller can forward the original key downstream.

    Returns a tuple ``(task_token, original_object_key)`` where
    ``original_object_key`` is ``None`` if the input wasn't staged.
    """
    try:
        # Get current tracking record using consistent read
        key = f"tasktoken#{object_key}"
        logger.info(f"Performing consistent read for tracking record: {key}")
        response = tracking_table.get_item(
            Key={'PK': key, 'SK': 'none'},
            ConsistentRead=True
        )
        
        if 'Item' not in response:
            error_msg = f"No tracking record found for {key} (with consistent read)"
            logger.error(error_msg)
            raise Exception(error_msg)
        
        item = response['Item']
        return item['TaskToken'], item.get('OriginalObjectKey')

    except Exception as e:
        logger.error(f"Error retrieving tracking record: {e}")
        raise

# Using metrics.put_metric directly

def send_task_response(task_token, job_status, job_detail, original_object_key=None):
    metrics.put_metric('BDAJobsTotal', 1)
    try:
        if job_status == 'SUCCESS':
            logger.info(f"Sending task success for token: {task_token}")
            output_payload = {
                'status': "SUCCESS",
                'job_detail': job_detail,
            }
            # When the input was staged under a sanitized key for BDA,
            # carry the original object key in the payload so
            # bda_processresults_function uses it as the document
            # identity instead of the sanitized key BDA echoed back.
            if original_object_key is not None:
                output_payload['original_object_key'] = original_object_key
            stepfunctions.send_task_success(
                taskToken=task_token,
                output=json.dumps(output_payload)
            )
            metrics.put_metric('BDAJobsSucceeded', 1)
        else:
            logger.info(f"Sending task failure for token: {task_token}")
            stepfunctions.send_task_failure(
                taskToken=task_token,
                error='JobExecutionError',
                cause=job_detail.get('error_message') or 'Job execution failed'
            )
            metrics.put_metric('BDAJobsFailed', 1)
    except Exception as e:
        logger.error(f"Error sending task response: {e}")
        raise

def handler(event, context):
    logger.info(f"Event: {json.dumps(event)}")
    
    try:
        # Extract required information from event
        detail = event['detail']
        object_key = detail['input_s3_object']['name']
        job_status = detail['job_status']
        
        logger.info(f"Processing job completion for object: {object_key}, status: {job_status}")
        
        # Look up the task token. If the input was staged under a
        # sanitized key, we also recover the original object key.
        task_token, original_object_key = get_task_token(object_key)
        logger.info(
            f"Retrieved task_token for sanitized_key={object_key!r} "
            f"original_key={original_object_key!r}"
        )
        
        # Send appropriate response to Step Functions
        send_task_response(task_token, job_status, detail, original_object_key)
        
        response = {
            'statusCode': 200,
            'body': 'Task response sent successfully'
        }
        logger.info(f"Response: {json.dumps(response, default=str)}")
        return response
        
    except Exception as e:
        logger.error(f"Error processing event: {e}")
        raise