# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json
import logging
import os
from datetime import datetime

import boto3

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
sqs = boto3.client('sqs')

def handler(event, context):
    logger.info(f"Test runner invoked with event: {json.dumps(event)}")
    
    try:
        input_data = event['arguments']['input']
        test_set_id = input_data['testSetId']
        test_context = input_data.get('context', '')
        number_of_files = input_data.get('numberOfFiles')
        config_version = input_data.get('configVersion')
        tracking_table = os.environ['TRACKING_TABLE']
        config_table = os.environ['CONFIG_TABLE']
        
        # Get test set
        test_set = _get_test_set(tracking_table, test_set_id)
        if not test_set:
            raise ValueError(f"Test set with ID '{test_set_id}' not found")
        
        # Determine actual file count to process
        test_set_file_count = test_set['fileCount']
        files_to_process = test_set_file_count
        
        if number_of_files is not None:
            if number_of_files <= 0:
                raise ValueError("numberOfFiles must be greater than 0")
            if number_of_files > test_set_file_count:
                raise ValueError(f"numberOfFiles ({number_of_files}) cannot exceed test set file count ({test_set_file_count})")
            files_to_process = number_of_files
        
        # Create test run identifier using test set name
        timestamp = datetime.utcnow().strftime('%Y%m%d-%H%M%S')
        test_run_id = f"{test_set['name']}-{timestamp}"
        
        # Capture current config
        config = _capture_config(config_table)
        
        # Store initial test run metadata
        _store_test_run_metadata(tracking_table, test_run_id, test_set_id, test_set['name'], config, [], test_context, files_to_process, config_version)
        
        # Send file copying job to SQS queue
        queue_url = os.environ['FILE_COPY_QUEUE_URL']
        
        message_body = {
            'testRunId': test_run_id,
            'testSetId': test_set_id,
            'trackingTable': tracking_table
        }
        
        # Only include numberOfFiles if it was specified
        if number_of_files is not None:
            message_body['numberOfFiles'] = number_of_files
            
        # Include configVersion if specified
        if config_version is not None:
            message_body['configVersion'] = config_version
        
        sqs.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(message_body)
        )
        
        logger.info(f"Queued test run {test_run_id} for test set {test_set_id} with {files_to_process} files")
        
        # Return immediately
        return {
            'testRunId': test_run_id,
            'testSetName': test_set['name'],
            'status': 'QUEUED',
            'filesCount': files_to_process,
            'completedFiles': 0,
            'createdAt': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        }
        
    except Exception as e:
        logger.error(f"Error in test runner: {str(e)}")
        raise

def _get_test_set(tracking_table, test_set_id):
    """Get test set by ID"""
    table = dynamodb.Table(tracking_table)  # type: ignore[attr-defined]
    
    try:
        response = table.get_item(
            Key={
                'PK': f'testset#{test_set_id}',
                'SK': 'metadata'
            }
        )
        return response.get('Item')
    except Exception as e:
        logger.error(f"Error getting test set {test_set_id}: {e}")
        return None

def _capture_config(config_table):
    """Capture current configuration"""
    table = dynamodb.Table(config_table)  # type: ignore[attr-defined]
    
    config = {}
    for config_type in ['Schema', 'Default', 'Custom']:
        try:
            response = table.get_item(Key={'Configuration': config_type})
            if 'Item' in response:
                config[config_type] = response['Item']
        except Exception as e:
            logger.warning(f"Could not retrieve {config_type} config: {e}")
    
    return config

def _store_test_run_metadata(tracking_table, test_run_id, test_set_id, test_set_name, config, files, context=None, file_count=0, config_version=None):
    """Store test run metadata in tracking table"""
    table = dynamodb.Table(tracking_table)  # type: ignore[attr-defined]
    
    try:
        item = {
            'PK': f'testrun#{test_run_id}',
            'SK': 'metadata',
            'TestSetId': test_set_id,
            'TestSetName': test_set_name,
            'TestRunId': test_run_id,
            'Status': 'QUEUED',
            'FilesCount': file_count,
            'CompletedFiles': 0,
            'FailedFiles': 0,
            'Files': files,
            'Config': config,
            'CreatedAt': datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%fZ')
        }
        
        if context:
            item['Context'] = context
            
        if config_version:
            item['ConfigVersion'] = config_version
            
        table.put_item(Item=item)
        logger.info(f"Stored test run metadata for {test_run_id}")
    except Exception as e:
        logger.error(f"Failed to store test run metadata: {e}")
        raise
