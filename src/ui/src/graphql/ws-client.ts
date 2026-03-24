// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

/**
 * WebSocket subscription client for Apollo/GovCloud mode.
 * Manages a WebSocket connection to the API Gateway WebSocket API
 * and routes subscription messages to registered callbacks.
 */

import { fetchAuthSession } from 'aws-amplify/auth';

type SubscriptionCallback<T = unknown> = {
  next: (value: T) => void;
  error?: (error: unknown) => void;
};

interface Subscription {
  unsubscribe: () => void;
}

interface PendingSubscription {
  topic: string;
  variables: Record<string, unknown>;
  callback: SubscriptionCallback;
  id: string;
}

const WS_URL = import.meta.env.VITE_GRAPHQL_WS_URL || '';

let ws: WebSocket | null = null;
let reconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 10;
const BASE_RECONNECT_DELAY_MS = 1000;

const subscriptions = new Map<string, SubscriptionCallback>();
const pendingSubscriptions: PendingSubscription[] = [];
let idCounter = 0;

function getNextId(): string {
  return `sub_${++idCounter}_${Date.now()}`;
}

async function getToken(): Promise<string> {
  const session = await fetchAuthSession();
  return session.tokens?.idToken?.toString() || '';
}

function handleMessage(event: MessageEvent) {
  try {
    const message = JSON.parse(event.data);
    if (message.type === 'data' && message.id) {
      // Route to all subscriptions matching this topic
      const topicBase = message.id.split('#')[0];
      for (const [subId, callback] of subscriptions) {
        // Match by topic prefix (e.g., "onUpdateDocument" matches subscription for "onUpdateDocument")
        if (subId.startsWith(topicBase) || message.id === subId) {
          try {
            callback.next(message.payload);
          } catch (err) {
            console.error('Subscription callback error:', err);
          }
        }
      }
    }
  } catch (err) {
    console.error('WebSocket message parse error:', err);
  }
}

async function ensureConnection(): Promise<WebSocket> {
  if (ws && ws.readyState === WebSocket.OPEN) {
    return ws;
  }

  return new Promise((resolve, reject) => {
    const connect = async () => {
      try {
        const token = await getToken();
        if (!token) {
          reject(new Error('No auth token available'));
          return;
        }

        const url = `${WS_URL}?token=${encodeURIComponent(token)}`;
        ws = new WebSocket(url);

        ws.onopen = () => {
          reconnectAttempts = 0;
          // Re-subscribe any pending subscriptions
          for (const pending of pendingSubscriptions) {
            sendSubscribe(pending.topic, pending.variables, pending.id);
          }
          resolve(ws!);
        };

        ws.onmessage = handleMessage;

        ws.onerror = (error) => {
          console.error('WebSocket error:', error);
        };

        ws.onclose = () => {
          ws = null;
          // Auto-reconnect if we have active subscriptions
          if (subscriptions.size > 0 && reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
            const delay = BASE_RECONNECT_DELAY_MS * Math.pow(2, reconnectAttempts);
            reconnectAttempts++;
            console.log(`WebSocket reconnecting in ${delay}ms (attempt ${reconnectAttempts})`);
            setTimeout(() => {
              ensureConnection().catch(console.error);
            }, delay);
          }
        };
      } catch (err) {
        reject(err);
      }
    };

    connect();
  });
}

function sendSubscribe(topic: string, variables: Record<string, unknown>, id: string) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({
      action: 'subscribe',
      topic,
      variables,
      id,
    }));
  }
}

/**
 * Subscribe to a GraphQL subscription topic.
 *
 * @param topic - Subscription name (e.g., "onUpdateDocument")
 * @param variables - Subscription variables (e.g., { sessionId: "123" })
 * @param callback - Callback with next/error handlers
 * @returns Subscription with unsubscribe method
 */
export async function subscribe(
  topic: string,
  variables: Record<string, unknown>,
  callback: SubscriptionCallback,
): Promise<Subscription> {
  const id = getNextId();

  // Build topic key with variables
  let topicKey = topic;
  if (topic === 'onAgentChatMessageUpdate' && variables.sessionId) {
    topicKey = `${topic}#${variables.sessionId}`;
  } else if (topic === 'onAgentJobComplete' && variables.jobId) {
    topicKey = `${topic}#${variables.jobId}`;
  } else if (topic === 'onDiscoveryJobStatusChange' && variables.jobId) {
    topicKey = `${topic}#${variables.jobId}`;
  }

  // Register the subscription
  subscriptions.set(topicKey, callback);
  const pending: PendingSubscription = { topic: topicKey, variables, callback, id };
  pendingSubscriptions.push(pending);

  // Ensure connection and send subscribe
  try {
    await ensureConnection();
    sendSubscribe(topicKey, variables, id);
  } catch (err) {
    callback.error?.(err);
  }

  return {
    unsubscribe: () => {
      subscriptions.delete(topicKey);
      const idx = pendingSubscriptions.findIndex((p) => p.id === id);
      if (idx >= 0) pendingSubscriptions.splice(idx, 1);

      // Send unsubscribe message
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action: 'unsubscribe', id: topicKey }));
      }

      // Close connection if no more subscriptions
      if (subscriptions.size === 0 && ws) {
        ws.close();
        ws = null;
      }
    },
  };
}
