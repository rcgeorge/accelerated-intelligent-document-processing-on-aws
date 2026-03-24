// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

/**
 * Apollo GraphQL adapter for GovCloud mode.
 * Implements the same interface as Amplify's generateClient() return value,
 * using fetch() for queries/mutations and WebSocket for subscriptions.
 */

import { fetchAuthSession } from 'aws-amplify/auth';
import { subscribe as wsSubscribe } from './ws-client';

const GRAPHQL_HTTP_URL = import.meta.env.VITE_GRAPHQL_HTTP_URL || '';

/**
 * Extract the subscription name from a GraphQL subscription document string.
 * e.g., "subscription OnUpdateDocument { onUpdateDocument { ... } }" → "onUpdateDocument"
 */
function extractSubscriptionName(query: string): string {
  // Match the first field inside the subscription block
  const match = query.match(/subscription\s+\w+[^{]*\{[\s]*(on\w+)/);
  return match?.[1] || '';
}

/**
 * Extract variables from a GraphQL subscription string.
 * e.g., "subscription OnFoo($sessionId: String!) { ... }" → ["sessionId"]
 */
function extractVariableNames(query: string): string[] {
  const match = query.match(/subscription\s+\w+\(([^)]*)\)/);
  if (!match) return [];
  return [...match[1].matchAll(/\$(\w+)/g)].map((m) => m[1]);
}

/**
 * Check if a GraphQL query string is a subscription.
 */
function isSubscription(query: string): boolean {
  const trimmed = query.trim();
  return trimmed.startsWith('subscription ') || trimmed.startsWith('subscription{');
}

async function getAuthToken(): Promise<string> {
  const session = await fetchAuthSession();
  return session.tokens?.idToken?.toString() || '';
}

/**
 * Execute a GraphQL query or mutation via HTTP.
 */
async function executeGraphQL(query: string, variables?: Record<string, unknown>) {
  const token = await getAuthToken();

  const response = await fetch(GRAPHQL_HTTP_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ query, variables }),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`GraphQL request failed: ${response.status} ${errorText}`);
  }

  const result = await response.json();

  if (result.errors?.length) {
    const error = new Error(result.errors[0].message) as Error & { errors: unknown[] };
    error.errors = result.errors;
    throw error;
  }

  return result;
}

/**
 * Create a subscription observable that matches the Amplify client interface:
 * client.graphql({ query }).subscribe({ next, error })
 */
function createSubscriptionObservable(
  query: string,
  variables?: Record<string, unknown>,
) {
  const subscriptionName = extractSubscriptionName(query);
  const variableNames = extractVariableNames(query);

  // Build the variables map for the subscription
  const subscriptionVars: Record<string, unknown> = {};
  for (const name of variableNames) {
    if (variables?.[name] !== undefined) {
      subscriptionVars[name] = variables[name];
    }
  }

  return {
    subscribe(callbacks: { next: (value: unknown) => void; error?: (error: unknown) => void }) {
      let subscriptionRef: { unsubscribe: () => void } | null = null;

      wsSubscribe(subscriptionName, subscriptionVars, {
        next: (payload: unknown) => {
          callbacks.next(payload);
        },
        error: (err: unknown) => {
          callbacks.error?.(err);
        },
      })
        .then((sub) => {
          subscriptionRef = sub;
        })
        .catch((err) => {
          callbacks.error?.(err);
        });

      return {
        unsubscribe: () => {
          subscriptionRef?.unsubscribe();
        },
      };
    },
  };
}

/**
 * Create an Apollo adapter client that matches the Amplify generateClient() interface.
 *
 * Supports:
 *   - client.graphql({ query, variables }) → Promise (queries/mutations)
 *   - client.graphql({ query, variables }).subscribe({ next, error }) (subscriptions)
 */
export function createApolloClient() {
  return {
    graphql(options: { query: string; variables?: Record<string, unknown> }) {
      const queryStr = typeof options.query === 'string' ? options.query : String(options.query);

      if (isSubscription(queryStr)) {
        return createSubscriptionObservable(queryStr, options.variables);
      }

      // For queries and mutations, return a promise
      return executeGraphQL(queryStr, options.variables);
    },
  };
}
