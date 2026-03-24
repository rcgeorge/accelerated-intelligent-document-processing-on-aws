// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: MIT-0

/**
 * RBAC configuration mapping GraphQL fields to required Cognito groups.
 *
 * Fields not listed here are accessible to all authenticated Cognito users.
 * Fields marked with "IAM" require the backend API key (x-api-key header).
 */

// Backend-only mutations (require API key, not Cognito auth)
export const IAM_ONLY_FIELDS = new Set([
  'createDocument',
  'updateDocument',
  'updateDocumentStatus',
  'updateDocumentSection',
  'updateAgentJobStatus',
  'updateDiscoveryJobStatus',
]);

// Cognito group requirements per field. If a field is not listed, all
// authenticated Cognito users can access it.
export const FIELD_GROUP_REQUIREMENTS = {
  // Admin-only
  deleteConfigVersion: ['Admin'],
  createUser: ['Admin'],
  updateUser: ['Admin'],
  deleteUser: ['Admin'],
  updatePricing: ['Admin'],
  restoreDefaultPricing: ['Admin'],

  // Admin + Author
  deleteDocument: ['Admin', 'Author'],
  updateConfiguration: ['Admin', 'Author'],
  setActiveVersion: ['Admin', 'Author'],
  syncBdaIdp: ['Admin', 'Author'],
  uploadDocument: ['Admin', 'Author'],
  deleteDiscoveryJob: ['Admin', 'Author'],
  uploadDiscoveryDocument: ['Admin', 'Author'],
  autoDetectSections: ['Admin', 'Author'],
  copyToBaseline: ['Admin', 'Author'],
  reprocessDocument: ['Admin', 'Author'],
  abortWorkflow: ['Admin', 'Author'],
  startTestRun: ['Admin', 'Author'],
  deleteTests: ['Admin', 'Author'],
  addTestSet: ['Admin', 'Author'],
  addTestSetFromUpload: ['Admin', 'Author'],
  deleteTestSets: ['Admin', 'Author'],

  // Admin + Reviewer (HITL)
  processChanges: ['Admin', 'Reviewer'],
  completeSectionReview: ['Admin', 'Reviewer'],
  skipAllSectionsReview: ['Admin', 'Reviewer'],
  claimReview: ['Admin', 'Reviewer'],
  releaseReview: ['Admin', 'Reviewer'],

  // Admin, Author, Viewer (not Reviewer)
  getConfigVersions: ['Admin', 'Author', 'Viewer'],
  getConfigVersion: ['Admin', 'Author', 'Viewer'],
  getPricing: ['Admin', 'Author', 'Viewer'],
  calculateCapacity: ['Admin', 'Author', 'Viewer'],
  listConfigurationLibrary: ['Admin', 'Author', 'Viewer'],
  getConfigurationLibraryFile: ['Admin', 'Author', 'Viewer'],
  submitAgentQuery: ['Admin', 'Author', 'Viewer'],
  getAgentJobStatus: ['Admin', 'Author', 'Viewer'],
  listAgentJobs: ['Admin', 'Author', 'Viewer'],

  // Admin, Author (not Reviewer, not Viewer)
  listDiscoveryJobs: ['Admin', 'Author'],
  getTestRun: ['Admin', 'Author'],
  getTestRuns: ['Admin', 'Author'],
  getTestRunStatus: ['Admin', 'Author'],
  compareTestRuns: ['Admin', 'Author'],
  getTestSets: ['Admin', 'Author'],
  listBucketFiles: ['Admin', 'Author'],
  validateTestFileName: ['Admin', 'Author'],
};

/**
 * Check if a user has access to a specific field.
 * @param {string} fieldName - The GraphQL field name
 * @param {string[]} userGroups - The user's Cognito groups
 * @param {boolean} isApiKeyAuth - Whether request uses API key auth
 * @returns {{ allowed: boolean, reason?: string }}
 */
export function checkAccess(fieldName, userGroups, isApiKeyAuth) {
  // IAM-only fields require API key
  if (IAM_ONLY_FIELDS.has(fieldName)) {
    if (isApiKeyAuth) {
      return { allowed: true };
    }
    return { allowed: false, reason: `Field '${fieldName}' requires backend API key authentication` };
  }

  // If field has group requirements, check membership
  const requiredGroups = FIELD_GROUP_REQUIREMENTS[fieldName];
  if (requiredGroups) {
    const hasAccess = userGroups.some((g) => requiredGroups.includes(g));
    if (!hasAccess) {
      return {
        allowed: false,
        reason: `Access denied. Required groups: ${requiredGroups.join(', ')}`,
      };
    }
  }

  // All other fields: any authenticated user can access
  return { allowed: true };
}
