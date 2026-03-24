// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

import { ApolloServer } from '@apollo/server';
import {
  startServerAndCreateLambdaHandler,
  handlers,
} from '@as-integrations/aws-lambda';
import { readFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  DateTimeResolver,
  TimestampResolver,
  JSONResolver,
} from 'graphql-scalars';

import { checkAccess, IAM_ONLY_FIELDS } from './rbac.mjs';
import { createLambdaResolver } from './lambda-invoker.mjs';
import * as ddb from './dynamodb-datasource.mjs';

const __dirname = dirname(fileURLToPath(import.meta.url));

// Load schema
const typeDefs = readFileSync(resolve(__dirname, '..', 'api', 'schema.graphql'), 'utf-8');

// Table names from environment
const TRACKING_TABLE = process.env.TRACKING_TABLE_NAME;
const AGENT_TABLE = process.env.AGENT_TABLE_NAME;
const CHAT_SESSIONS_TABLE = process.env.CHAT_SESSIONS_TABLE_NAME;
const BACKEND_API_KEY = process.env.BACKEND_API_KEY;

// ── Resolvers ─────────────────────────────────────────────────────────

const resolvers = {
  // Custom scalars
  JSON: JSONResolver,
  DateTime: DateTimeResolver,
  Timestamp: TimestampResolver,

  Query: {
    // DynamoDB direct resolvers
    getDocument: (_p, args) => ddb.getDocument(TRACKING_TABLE, args.ObjectKey),
    listDocumentsDateHour: (_p, args) => ddb.listDocumentsDateHour(TRACKING_TABLE, args.date, args.hour),
    listDocumentsDateShard: (_p, args) => ddb.listDocumentsDateShard(TRACKING_TABLE, args.date, args.shard),
    getAgentJobStatus: (_p, args) => ddb.getAgentJobStatus(AGENT_TABLE, args.jobId),
    listAgentJobs: (_p, args) => ddb.listAgentJobs(AGENT_TABLE, args.limit, args.nextToken),

    // Lambda-backed resolvers
    listDocuments: createLambdaResolver('LIST_DOCUMENTS_GSI_FUNCTION_ARN'),
    getDocumentCount: createLambdaResolver('LIST_DOCUMENTS_GSI_FUNCTION_ARN'),
    listDocumentsByDateRange: createLambdaResolver('LIST_DOCUMENTS_RANGE_FUNCTION_ARN'),
    getFileContents: createLambdaResolver('GET_FILE_CONTENTS_FUNCTION_ARN'),
    getStepFunctionExecution: createLambdaResolver('GET_STEPFUNCTION_EXECUTION_FUNCTION_ARN'),
    getConfigVersions: createLambdaResolver('CONFIGURATION_FUNCTION_ARN'),
    getConfigVersion: createLambdaResolver('CONFIGURATION_FUNCTION_ARN'),
    getPricing: createLambdaResolver('CONFIGURATION_FUNCTION_ARN'),
    calculateCapacity: createLambdaResolver('CONFIGURATION_FUNCTION_ARN'),
    listAvailableAgents: createLambdaResolver('LIST_AVAILABLE_AGENTS_FUNCTION_ARN'),
    getAgentChatMessages: createLambdaResolver('GET_AGENT_CHAT_MESSAGES_FUNCTION_ARN'),
    listChatSessions: createLambdaResolver('LIST_AGENT_CHAT_SESSIONS_FUNCTION_ARN'),
    getChatMessages: createLambdaResolver('GET_AGENT_CHAT_MESSAGES_FUNCTION_ARN'),
    queryKnowledgeBase: createLambdaResolver('QUERY_KNOWLEDGEBASE_FUNCTION_ARN'),
    chatWithDocument: createLambdaResolver('CHAT_WITH_DOCUMENT_FUNCTION_ARN'),
    listDiscoveryJobs: createLambdaResolver('DISCOVERY_UPLOAD_FUNCTION_ARN'),
    submitAgentQuery: createLambdaResolver('AGENT_REQUEST_HANDLER_FUNCTION_ARN'),
    getTestRun: createLambdaResolver('TEST_RESULTS_FUNCTION_ARN'),
    getTestRuns: createLambdaResolver('TEST_RESULTS_FUNCTION_ARN'),
    getTestRunStatus: createLambdaResolver('TEST_RESULTS_FUNCTION_ARN'),
    compareTestRuns: createLambdaResolver('TEST_RESULTS_FUNCTION_ARN'),
    getTestSets: createLambdaResolver('TEST_SET_FUNCTION_ARN'),
    listBucketFiles: createLambdaResolver('TEST_SET_FUNCTION_ARN'),
    validateTestFileName: createLambdaResolver('TEST_SET_FUNCTION_ARN'),
    listConfigurationLibrary: createLambdaResolver('CONFIGURATION_FUNCTION_ARN'),
    getConfigurationLibraryFile: createLambdaResolver('CONFIGURATION_FUNCTION_ARN'),
    listUsers: createLambdaResolver('CONFIGURATION_FUNCTION_ARN'),
    getMyProfile: createLambdaResolver('CONFIGURATION_FUNCTION_ARN'),
  },

  Mutation: {
    // DynamoDB direct mutations
    updateDocument: (_p, args) => ddb.updateDocument(TRACKING_TABLE, args.input),
    updateDocumentStatus: (_p, args) => ddb.updateDocumentStatus(TRACKING_TABLE, args.input),
    updateDocumentSection: (_p, args) => ddb.updateDocumentSection(TRACKING_TABLE, args.input),
    updateAgentJobStatus: (_p, args) =>
      ddb.updateAgentJobStatus(AGENT_TABLE, args.jobId, args.status, args.userId, args.result),
    updateDiscoveryJobStatus: (_p, args) =>
      ddb.updateDiscoveryJobStatus(
        process.env.DISCOVERY_TABLE_NAME,
        args.jobId, args.status, args.errorMessage,
        args.discoveredClassName, args.statusMessage,
      ),
    deleteAgentJob: (_p, args) => ddb.deleteAgentJob(AGENT_TABLE, args.jobId),

    // HITL DynamoDB direct mutations
    completeSectionReview: (_p, args, ctx) =>
      ddb.completeSectionReview(TRACKING_TABLE, args.objectKey, args.sectionId, args.editedData),
    skipAllSectionsReview: (_p, args) =>
      ddb.skipAllSectionsReview(TRACKING_TABLE, args.objectKey),
    claimReview: (_p, args, ctx) =>
      ddb.claimReview(TRACKING_TABLE, args.objectKey, ctx.identity),
    releaseReview: (_p, args) =>
      ddb.releaseReview(TRACKING_TABLE, args.objectKey),
    updateChatSessionTitle: (_p, args) =>
      ddb.updateChatSessionTitle(CHAT_SESSIONS_TABLE, args.sessionId, args.title),

    // Lambda-backed mutations
    createDocument: createLambdaResolver('CREATE_DOCUMENT_FUNCTION_ARN'),
    deleteDocument: createLambdaResolver('DELETE_DOCUMENT_FUNCTION_ARN'),
    deleteConfigVersion: createLambdaResolver('CONFIGURATION_FUNCTION_ARN'),
    updateConfiguration: createLambdaResolver('CONFIGURATION_FUNCTION_ARN'),
    setActiveVersion: createLambdaResolver('CONFIGURATION_FUNCTION_ARN'),
    syncBdaIdp: createLambdaResolver('SYNC_BDA_IDP_FUNCTION_ARN'),
    updatePricing: createLambdaResolver('CONFIGURATION_FUNCTION_ARN'),
    restoreDefaultPricing: createLambdaResolver('CONFIGURATION_FUNCTION_ARN'),
    uploadDocument: createLambdaResolver('UPLOAD_FUNCTION_ARN'),
    deleteDiscoveryJob: createLambdaResolver('DISCOVERY_UPLOAD_FUNCTION_ARN'),
    uploadDiscoveryDocument: createLambdaResolver('DISCOVERY_UPLOAD_FUNCTION_ARN'),
    autoDetectSections: createLambdaResolver('DISCOVERY_UPLOAD_FUNCTION_ARN'),
    copyToBaseline: createLambdaResolver('COPY_TO_BASELINE_FUNCTION_ARN'),
    reprocessDocument: createLambdaResolver('REPROCESS_DOCUMENT_FUNCTION_ARN'),
    abortWorkflow: createLambdaResolver('ABORT_WORKFLOW_FUNCTION_ARN'),
    sendAgentChatMessage: createLambdaResolver('AGENT_CHAT_FUNCTION_ARN'),
    updateAgentChatMessage: createLambdaResolver('AGENT_CHAT_FUNCTION_ARN'),
    deleteChatSession: createLambdaResolver('DELETE_AGENT_CHAT_SESSION_FUNCTION_ARN'),
    processChanges: createLambdaResolver('PROCESS_CHANGES_FUNCTION_ARN'),
    startTestRun: createLambdaResolver('TEST_RUNNER_FUNCTION_ARN'),
    deleteTests: createLambdaResolver('DELETE_TESTS_FUNCTION_ARN'),
    addTestSet: createLambdaResolver('TEST_SET_FUNCTION_ARN'),
    addTestSetFromUpload: createLambdaResolver('TEST_SET_FUNCTION_ARN'),
    deleteTestSets: createLambdaResolver('TEST_SET_FUNCTION_ARN'),
    createUser: createLambdaResolver('CONFIGURATION_FUNCTION_ARN'),
    updateUser: createLambdaResolver('CONFIGURATION_FUNCTION_ARN'),
    deleteUser: createLambdaResolver('CONFIGURATION_FUNCTION_ARN'),
  },
};

// ── Apollo Server ─────────────────────────────────────────────────────

const server = new ApolloServer({
  typeDefs,
  resolvers,
  introspection: true,
});

// ── Lambda Handler ────────────────────────────────────────────────────

export const handler = startServerAndCreateLambdaHandler(
  server,
  handlers.createAPIGatewayProxyEventV2RequestHandler(),
  {
    context: async ({ event }) => {
      const identity = { sub: '', username: '', email: '', groups: [], isApiKey: false };

      // Check for backend API key auth (x-api-key header)
      const apiKey = event.headers?.['x-api-key'];
      if (apiKey && apiKey === BACKEND_API_KEY) {
        identity.isApiKey = true;
        return { identity };
      }

      // Extract JWT claims from API Gateway authorizer context
      const authorizer = event.requestContext?.authorizer;
      if (authorizer?.jwt?.claims) {
        const claims = authorizer.jwt.claims;
        identity.sub = claims.sub || '';
        identity.username = claims['cognito:username'] || claims.sub || '';
        identity.email = claims.email || identity.username;

        // Groups can be a string or array depending on the JWT structure
        const groups = claims['cognito:groups'];
        if (typeof groups === 'string') {
          identity.groups = groups.startsWith('[')
            ? JSON.parse(groups)
            : [groups];
        } else if (Array.isArray(groups)) {
          identity.groups = groups;
        }
      }

      return { identity };
    },
  },
);

// ── Auth Plugin ───────────────────────────────────────────────────────
// We inject RBAC checks as a plugin so they run before resolvers.

const authPlugin = {
  async requestDidStart() {
    return {
      async didResolveOperation(requestContext) {
        const { operation, contextValue } = requestContext;
        const { identity } = contextValue;

        if (!identity) {
          throw new Error('Unauthorized: No identity found');
        }

        // If not API key auth and no groups/sub, reject
        if (!identity.isApiKey && !identity.sub) {
          throw new Error('Unauthorized: Invalid or missing authentication');
        }

        // Check field-level RBAC for each selection in the operation
        const selections = operation.selectionSet?.selections || [];
        for (const selection of selections) {
          if (selection.kind !== 'Field') continue;
          const fieldName = selection.name.value;

          const { allowed, reason } = checkAccess(
            fieldName,
            identity.groups,
            identity.isApiKey,
          );

          if (!allowed) {
            throw new Error(`Forbidden: ${reason}`);
          }
        }
      },
    };
  },
};

// Add the auth plugin to the server
server.addPlugin(authPlugin);
