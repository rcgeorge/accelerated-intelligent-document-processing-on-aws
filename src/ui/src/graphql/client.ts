// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

/**
 * GraphQL client factory.
 *
 * In Standard mode (AppSync), returns the Amplify generateClient() client.
 * In GovCloud mode (Apollo Server), returns the Apollo adapter client.
 *
 * Both clients expose the same interface:
 *   client.graphql({ query, variables }) → Promise | Observable
 */

import { generateClient } from 'aws-amplify/api';
import { createApolloClient } from './apollo-adapter';

const DEPLOYMENT_MODE = import.meta.env.VITE_DEPLOYMENT_MODE || 'Standard';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type GraphQLClient = ReturnType<typeof generateClient> | ReturnType<typeof createApolloClient>;

let _client: GraphQLClient | null = null;

/**
 * Get the GraphQL client singleton.
 * Uses Amplify generateClient() for Standard mode,
 * or the Apollo adapter for GovCloud mode.
 */
export function getClient(): GraphQLClient {
  if (!_client) {
    if (DEPLOYMENT_MODE === 'GovCloud') {
      _client = createApolloClient();
    } else {
      _client = generateClient();
    }
  }
  return _client;
}

/**
 * Check if the current deployment uses Apollo (GovCloud) mode.
 */
export function isGovCloudMode(): boolean {
  return DEPLOYMENT_MODE === 'GovCloud';
}
