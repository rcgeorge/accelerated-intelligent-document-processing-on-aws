// Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
// SPDX-License-Identifier: Apache-2.0
import gql from 'graphql-tag';

export default gql`
  mutation UpdateConfiguration($versionId: String!, $customConfig: AWSJSON!, $description: String) {
    updateConfiguration(versionId: $versionId, customConfig: $customConfig, description: $description) {
      success
      message
      error {
        type
        message
        validationErrors {
          field
          message
          type
        }
      }
    }
  }
`;
