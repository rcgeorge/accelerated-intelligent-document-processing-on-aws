// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

import { LambdaClient, InvokeCommand } from '@aws-sdk/client-lambda';

const lambdaClient = new LambdaClient({});

/**
 * Invoke an existing AppSync resolver Lambda function.
 *
 * Constructs the event in AppSync Lambda resolver format so existing
 * resolver Lambdas work without modification:
 *   { arguments: {...}, identity: { claims: {...} } }
 *
 * @param {string} functionName - Lambda function name or ARN
 * @param {object} args - GraphQL arguments
 * @param {object} identity - User identity from context
 * @returns {Promise<any>} Parsed Lambda response
 */
export async function invokeLambda(functionName, args, identity) {
  // Build AppSync-compatible event shape
  const event = {
    arguments: args,
    identity: {
      sub: identity.sub,
      username: identity.username,
      claims: {
        sub: identity.sub,
        email: identity.email,
        'cognito:username': identity.username,
        'cognito:groups': identity.groups,
      },
    },
  };

  const command = new InvokeCommand({
    FunctionName: functionName,
    InvocationType: 'RequestResponse',
    Payload: JSON.stringify(event),
  });

  const response = await lambdaClient.send(command);

  if (response.FunctionError) {
    const errorPayload = JSON.parse(new TextDecoder().decode(response.Payload));
    throw new Error(errorPayload.errorMessage || `Lambda error: ${response.FunctionError}`);
  }

  const payload = JSON.parse(new TextDecoder().decode(response.Payload));
  return payload;
}

/**
 * Create a resolver function that invokes a specific Lambda.
 * Returns a function compatible with Apollo Server resolver signature.
 *
 * @param {string} envVarName - Environment variable containing Lambda ARN
 * @returns {Function} Apollo resolver function
 */
export function createLambdaResolver(envVarName) {
  return async (_parent, args, context) => {
    const functionArn = process.env[envVarName];
    if (!functionArn) {
      throw new Error(`Lambda function not configured: ${envVarName}`);
    }
    return invokeLambda(functionArn, args, context.identity);
  };
}
