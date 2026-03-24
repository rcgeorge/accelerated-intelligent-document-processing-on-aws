// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

import { DynamoDBClient } from '@aws-sdk/client-dynamodb';
import {
  DynamoDBDocumentClient,
  GetCommand,
  PutCommand,
  UpdateCommand,
  QueryCommand,
  DeleteCommand,
  ScanCommand,
} from '@aws-sdk/lib-dynamodb';

const ddbClient = new DynamoDBClient({});
const docClient = DynamoDBDocumentClient.from(ddbClient, {
  marshallOptions: { removeUndefinedValues: true },
});

/**
 * DynamoDB data source that replaces AppSync VTL direct resolvers.
 * Each method mirrors the corresponding VTL resolver logic.
 */

// ── Document Queries ──────────────────────────────────────────────────

export async function getDocument(tableName, objectKey) {
  const pk = `doc#${objectKey}`;
  const result = await docClient.send(
    new GetCommand({
      TableName: tableName,
      Key: { PK: pk, SK: 'none' },
    }),
  );
  return result.Item || null;
}

export async function listDocumentsDateHour(tableName, date, hour) {
  const pk = `date#${date}#hour#${hour}`;
  const result = await docClient.send(
    new QueryCommand({
      TableName: tableName,
      KeyConditionExpression: 'PK = :pk',
      ExpressionAttributeValues: { ':pk': pk },
    }),
  );
  return { Documents: result.Items || [] };
}

export async function listDocumentsDateShard(tableName, date, shard) {
  const pk = `date#${date}#shard#${shard}`;
  const result = await docClient.send(
    new QueryCommand({
      TableName: tableName,
      KeyConditionExpression: 'PK = :pk',
      ExpressionAttributeValues: { ':pk': pk },
    }),
  );
  return { Documents: result.Items || [] };
}

// ── Document Mutations (DynamoDB direct) ──────────────────────────────

export async function updateDocument(tableName, input) {
  const pk = `doc#${input.ObjectKey}`;
  const expNames = {};
  const expValues = {};
  const setParts = [];

  for (const [key, value] of Object.entries(input)) {
    if (key === 'ObjectKey' || value === undefined || value === null) continue;
    const nameAlias = `#${key}`;
    const valueAlias = `:${key}`;
    expNames[nameAlias] = key;
    expValues[valueAlias] = value;
    setParts.push(`${nameAlias} = ${valueAlias}`);
  }

  if (setParts.length === 0) return null;

  const result = await docClient.send(
    new UpdateCommand({
      TableName: tableName,
      Key: { PK: pk, SK: 'none' },
      UpdateExpression: `SET ${setParts.join(', ')}`,
      ExpressionAttributeNames: expNames,
      ExpressionAttributeValues: expValues,
      ReturnValues: 'ALL_NEW',
    }),
  );
  return result.Attributes || null;
}

export async function updateDocumentStatus(tableName, input) {
  const pk = `doc#${input.ObjectKey}`;
  const expNames = { '#ObjectStatus': 'ObjectStatus' };
  const expValues = { ':ObjectStatus': input.ObjectStatus };
  let expression = 'SET #ObjectStatus = :ObjectStatus';

  if (input.WorkflowExecutionArn) {
    expNames['#WorkflowExecutionArn'] = 'WorkflowExecutionArn';
    expValues[':WorkflowExecutionArn'] = input.WorkflowExecutionArn;
    expression += ', #WorkflowExecutionArn = :WorkflowExecutionArn';
  }

  if (input.WorkflowStatus) {
    expNames['#WorkflowStatus'] = 'WorkflowStatus';
    expValues[':WorkflowStatus'] = input.WorkflowStatus;
    expression += ', #WorkflowStatus = :WorkflowStatus';
  }

  const result = await docClient.send(
    new UpdateCommand({
      TableName: tableName,
      Key: { PK: pk, SK: 'none' },
      UpdateExpression: expression,
      ExpressionAttributeNames: expNames,
      ExpressionAttributeValues: expValues,
      ReturnValues: 'ALL_NEW',
    }),
  );
  return result.Attributes || null;
}

export async function updateDocumentSection(tableName, input) {
  const pk = `doc#${input.ObjectKey}`;
  const result = await docClient.send(
    new UpdateCommand({
      TableName: tableName,
      Key: { PK: pk, SK: 'none' },
      UpdateExpression: `SET Sections[${input.SectionIndex}] = :section`,
      ExpressionAttributeValues: { ':section': input.Section },
      ReturnValues: 'ALL_NEW',
    }),
  );
  return result.Attributes || null;
}

// ── Agent Job Resolvers (DynamoDB direct) ─────────────────────────────

export async function getAgentJobStatus(tableName, jobId) {
  const result = await docClient.send(
    new GetCommand({
      TableName: tableName,
      Key: { PK: `job#${jobId}`, SK: 'metadata' },
    }),
  );
  if (!result.Item) return null;
  return { ...result.Item, jobId };
}

export async function listAgentJobs(tableName, limit, nextToken) {
  const params = {
    TableName: tableName,
    IndexName: 'GSI1',
    KeyConditionExpression: 'GSI1PK = :pk',
    ExpressionAttributeValues: { ':pk': 'AGENT_JOB' },
    ScanIndexForward: false,
    Limit: limit || 20,
  };
  if (nextToken) {
    params.ExclusiveStartKey = JSON.parse(Buffer.from(nextToken, 'base64').toString());
  }

  const result = await docClient.send(new QueryCommand(params));
  const items = (result.Items || []).map((item) => ({
    ...item,
    jobId: item.PK?.replace('job#', ''),
  }));

  let newNextToken = null;
  if (result.LastEvaluatedKey) {
    newNextToken = Buffer.from(JSON.stringify(result.LastEvaluatedKey)).toString('base64');
  }

  return { items, nextToken: newNextToken };
}

export async function updateAgentJobStatus(tableName, jobId, status, userId, result) {
  const updateExpr = ['#status = :status'];
  const expNames = { '#status': 'status' };
  const expValues = { ':status': status };

  if (result !== undefined && result !== null) {
    updateExpr.push('#result = :result');
    expNames['#result'] = 'result';
    expValues[':result'] = result;
  }

  if (status === 'COMPLETED' || status === 'FAILED') {
    updateExpr.push('completedAt = :completedAt');
    expValues[':completedAt'] = new Date().toISOString();
  }

  await docClient.send(
    new UpdateCommand({
      TableName: tableName,
      Key: { PK: `job#${jobId}`, SK: 'metadata' },
      UpdateExpression: `SET ${updateExpr.join(', ')}`,
      ExpressionAttributeNames: expNames,
      ExpressionAttributeValues: expValues,
    }),
  );
  return true;
}

export async function deleteAgentJob(tableName, jobId) {
  await docClient.send(
    new DeleteCommand({
      TableName: tableName,
      Key: { PK: `job#${jobId}`, SK: 'metadata' },
    }),
  );
  return true;
}

// ── Discovery Job Resolvers (DynamoDB direct) ─────────────────────────

export async function updateDiscoveryJobStatus(tableName, jobId, status, errorMessage, discoveredClassName, statusMessage) {
  const updateParts = ['#status = :status'];
  const expNames = { '#status': 'status' };
  const expValues = { ':status': status };

  if (errorMessage !== undefined && errorMessage !== null) {
    updateParts.push('errorMessage = :errorMessage');
    expValues[':errorMessage'] = errorMessage;
  }
  if (discoveredClassName !== undefined && discoveredClassName !== null) {
    updateParts.push('discoveredClassName = :discoveredClassName');
    expValues[':discoveredClassName'] = discoveredClassName;
  }
  if (statusMessage !== undefined && statusMessage !== null) {
    updateParts.push('statusMessage = :statusMessage');
    expValues[':statusMessage'] = statusMessage;
  }

  updateParts.push('updatedAt = :updatedAt');
  expValues[':updatedAt'] = new Date().toISOString();

  const result = await docClient.send(
    new UpdateCommand({
      TableName: tableName,
      Key: { PK: `discovery#${jobId}`, SK: 'metadata' },
      UpdateExpression: `SET ${updateParts.join(', ')}`,
      ExpressionAttributeNames: expNames,
      ExpressionAttributeValues: expValues,
      ReturnValues: 'ALL_NEW',
    }),
  );

  const item = result.Attributes || {};
  return { jobId, ...item };
}

// ── HITL Resolvers (DynamoDB direct) ──────────────────────────────────

export async function completeSectionReview(tableName, objectKey, sectionId, editedData) {
  const pk = `doc#${objectKey}`;

  // Get current document first
  const doc = await docClient.send(
    new GetCommand({ TableName: tableName, Key: { PK: pk, SK: 'none' } }),
  );

  if (!doc.Item) return null;

  const pendingSections = (doc.Item.HITLSectionsPending || []).filter((s) => s !== sectionId);
  const completedSections = [...(doc.Item.HITLSectionsCompleted || []), sectionId];
  const allDone = pendingSections.length === 0;

  const updateParts = [
    'HITLSectionsPending = :pending',
    'HITLSectionsCompleted = :completed',
  ];
  const expValues = {
    ':pending': pendingSections,
    ':completed': completedSections,
  };

  if (allDone) {
    updateParts.push('HITLStatus = :status', 'HITLCompleted = :done');
    expValues[':status'] = 'COMPLETED';
    expValues[':done'] = true;
  }

  const result = await docClient.send(
    new UpdateCommand({
      TableName: tableName,
      Key: { PK: pk, SK: 'none' },
      UpdateExpression: `SET ${updateParts.join(', ')}`,
      ExpressionAttributeValues: expValues,
      ReturnValues: 'ALL_NEW',
    }),
  );
  return result.Attributes || null;
}

export async function skipAllSectionsReview(tableName, objectKey) {
  const pk = `doc#${objectKey}`;

  const doc = await docClient.send(
    new GetCommand({ TableName: tableName, Key: { PK: pk, SK: 'none' } }),
  );
  if (!doc.Item) return null;

  const pendingSections = doc.Item.HITLSectionsPending || [];

  const result = await docClient.send(
    new UpdateCommand({
      TableName: tableName,
      Key: { PK: pk, SK: 'none' },
      UpdateExpression: 'SET HITLSectionsPending = :empty, HITLSectionsSkipped = :skipped, HITLStatus = :status, HITLCompleted = :done',
      ExpressionAttributeValues: {
        ':empty': [],
        ':skipped': pendingSections,
        ':status': 'COMPLETED',
        ':done': true,
      },
      ReturnValues: 'ALL_NEW',
    }),
  );
  return result.Attributes || null;
}

export async function claimReview(tableName, objectKey, identity) {
  const pk = `doc#${objectKey}`;
  const result = await docClient.send(
    new UpdateCommand({
      TableName: tableName,
      Key: { PK: pk, SK: 'none' },
      UpdateExpression: 'SET HITLReviewOwner = :owner, HITLReviewOwnerEmail = :email',
      ExpressionAttributeValues: {
        ':owner': identity.sub,
        ':email': identity.email,
      },
      ReturnValues: 'ALL_NEW',
    }),
  );
  return result.Attributes || null;
}

export async function releaseReview(tableName, objectKey) {
  const pk = `doc#${objectKey}`;
  const result = await docClient.send(
    new UpdateCommand({
      TableName: tableName,
      Key: { PK: pk, SK: 'none' },
      UpdateExpression: 'REMOVE HITLReviewOwner, HITLReviewOwnerEmail',
      ReturnValues: 'ALL_NEW',
    }),
  );
  return result.Attributes || null;
}

// ── Chat Session / Message Resolvers (DynamoDB direct) ────────────────

export async function updateChatSessionTitle(sessionsTableName, sessionId, title) {
  const result = await docClient.send(
    new UpdateCommand({
      TableName: sessionsTableName,
      Key: { sessionId },
      UpdateExpression: 'SET title = :title, updatedAt = :now',
      ExpressionAttributeValues: {
        ':title': title,
        ':now': new Date().toISOString(),
      },
      ReturnValues: 'ALL_NEW',
    }),
  );
  return result.Attributes || null;
}
