# GenAIIDP — Engineering Backlog

Informal backlog of larger design items raised during architecture/troubleshooting
sessions. Each item captures the ask, current state, and a rough assessment so the
work can be specced later. Not a substitute for the issue tracker — these are
design notes.

---

## BL-001 — Decouple the private Jobs REST API from headless mode (`DeployInVPC` should be able to stand it up)

**Ask:** Allow the private Jobs API Gateway to be deployed alongside the full
(ALB-hosted) Web UI, rather than only in headless mode. Today the only way to get
the REST API is `EnableHeadless=true`, which strips the UI/AppSync/Cognito layer.

**Current state:**
- The Jobs API Gateway is **already private by construction** — `EndpointConfiguration: Type: PRIVATE` is hardcoded (`template.yaml:1589`). There is no public variant. So the work is not "make it private," it's "deploy the already-private API off a different condition."
- All API resources hang off one condition: `DeployApiGateway: !Equals [!Ref EnableHeadless, 'true']` (`template.yaml:1059`).
- ~15 resources carry `Condition: DeployApiGateway`: the API, two handler Lambdas, a **dedicated** Cognito pool (`ApiUserPool` — M2M `client_credentials`, independent of the UI's Cognito pool), resource server, app client, domain, log group, an SQS queue + role + invoke permission, a staging bucket + policy, and two outputs.
- The API's resource policy denies any source VPCE that isn't `ApiGatewayVpcEndpointId` (`template.yaml:1598–1610`); reachability requires a customer-supplied `com.amazonaws.<region>.execute-api` interface endpoint.

**Why it's feasible:** the API's auth is a self-contained Cognito pool, so it does
not collide with the UI's Cognito pool — the two can coexist in one stack.

**Change surface (modest):**
1. Repoint the deploy condition. Prefer a new opt-in param: `DeployApiGateway: !Or [EnableHeadless==true, EnableJobsApi==true]`. (Binding directly to `DeployInVPC` would force the API onto every VPC deployment, including ALB-UI-only stacks.)
2. Add a `Rules` assertion mirroring `HeadlessRequiresVPC` so the new path also requires `DeployInVPC=true` + non-empty `ApiGatewayVpcEndpointId`.
3. `execute-api` endpoint plumbing: it is **not** in `scripts/vpc-endpoints.yaml` today, so the private-network ALB runbook never creates it. Either keep requiring the customer to pre-create + pass `ApiGatewayVpcEndpointId`, or add `execute-api` to `scripts/vpc-endpoints.yaml` + `deploy-vpc-endpoints.py`.
4. Coexistence check: verify the `DeployApiGateway`-gated staging bucket (`3275`), SQS queue (`5652`), and IAM roles don't collide with UI resources when both are present (no existing deployment exercises UI + Jobs API together). Names are API-specific, so likely clean.
5. Outside the template: add an `idp-cli` flag/parameter parallel to `--headless`; update docs (the headless guide frames the Jobs API as a *replacement* for the UI).

**Open decision:** new `EnableJobsApi` flag (opt-in, cleaner) vs. gate on `DeployInVPC` (automatic, but couples the API to every VPC stack).

---

## BL-002 — CodeBuild builds deployment artifacts and publishes to a cross-account (private) S3 bucket

**Ask:** Run the artifact build in CodeBuild (instead of a workstation) and have it
push the built artifacts to an S3 bucket in a **different AWS account**, so the stack
is deployed from that bucket rather than the default published S3 path.

**Customer intent (clarified):** the customer wants to deploy via **pure
CloudFormation** but using **their own build** of the code. The flow they have in
mind: the `idp-cli publish` (build) commands run in **CodeBuild or a Bitbucket
pipeline**, which creates and pushes the artifact zips/templates to S3; they then
hand CloudFormation a template that points at that zip. This is exactly the
supported model — `idp-cli publish` produces a self-contained artifact set plus a
ready-to-deploy `idp-main.yaml`; the only twist is the cross-account, private,
direct-to-destination-bucket publish (see constraint below). Any CI runner works
(CodeBuild, Bitbucket Pipelines, GitLab CI) as long as it provides the build
toolchain and Docker.

**Build system: SAM, not CDK (confirmed).** Every template uses
`Transform: AWS::Serverless-2016-10-31` (`template.yaml:5` and all nested
templates). There is **no `cdk.json` / CDK app** anywhere in the repo. The
`cdk_nag` entries seen in templates are just multi-scanner suppression metadata
(alongside `cfn_nag`, `checkov`, `security-matrix`), not CDK usage. Implication for
this item: the build is `sam build` + `sam package` (driven by `idp-cli publish`),
which **rewrites local `CodeUri`/`TemplateURL` paths to `s3://<bucket>/...` at
publish time** — there is no synth step and no runtime artifact-bucket parameter,
which is precisely why the destination bucket name is baked in (see constraint).

**Current state / key facts:**
- `idp-cli publish` (legacy `publish.py` → `idp_sdk._core.publish.IDPPublisher`) already does the full build: SAM build of all Lambda zips/layers, nested templates, `config_library`, `sam-objects`, feature `extensions`; uploads to `<bucket-basename>-<region>` under `<prefix>/<version>/`; emits `idp-main.yaml`.
- **Artifact bucket name is baked in at publish time.** Nested `TemplateURL`s are local paths (`./nested/.../packaged.yaml`, e.g. `template.yaml:2044/2517/2609/2751`) that `sam package` rewrites to `s3://<bucket>/...`. ⇒ you must publish **directly to the destination bucket name** — you cannot build to bucket A and copy to bucket B (references would break).
- Publisher already has cross-account awareness: default ACL `bucket-owner-full-control` (`publish.py:411`), `public` mode sets `public-read` (`:422`, `set_public_acls` `:3386`), and a comment about cross-account public deploys hitting 403 on the version-free `extensions/` prefix.
- Existing SDLC pipeline (`scripts/sdlc/cfn/codepipeline-s3.yml`) is a build-**and-deploy** pipeline (good reference for the CodeBuild role/buildspec pattern), **not** a publish-artifacts-to-cross-account pipeline.
- Deploy side already supports a KMS-encrypted artifact bucket via the `ArtifactsBucketKmsKeyArn` parameter (`template.yaml:626`).

**Assessment of what's required:** see the detailed write-up captured with this item
(summary below).

1. **CodeBuild environment:** Python 3.12, Node 22.12+, SAM CLI, `uv`, `make setup`; **Docker with `privilegedMode: true`** (Pattern-2 builds container images) and **ECR push perms** in the build account; `BUILD_GENERAL1_LARGE`.
2. **Publish directly to the destination bucket name** (name is embedded). Pre-create the bucket in account B (publish auto-creates only same-account; cross-account create is wrong/not permitted).
3. **Cross-account write — pick one model:**
   - **(a) Direct cross-account write:** account B bucket policy grants the account A CodeBuild role `PutObject`/`GetObject`/`ListBucket` (+`PutObjectAcl` if ACLs on). **Object-ownership trap:** if account B uses **Bucket Owner Enforced** (ACLs disabled — the modern S3 default), `put_object` *with an ACL* fails (`AccessControlListNotSupported`). Publisher currently **always** sends an ACL ⇒ **code change needed** to suppress ACLs for ACL-disabled buckets. If ACLs are left enabled, the existing `bucket-owner-full-control` default is correct.
   - **(b) Assume-role into account B (recommended):** CodeBuild assumes a role in B that owns the write; ownership is clean, no ACL gymnastics. Needs `sts:AssumeRole` + a trust role in B. Publisher would need to run under assumed creds (env/profile).
4. **KMS:** if account B bucket is SSE-KMS, the writing principal needs `kms:GenerateDataKey`/`Encrypt` on B's CMK (grant in key policy).
5. **Deploy-time read access (private, not public):** the deploying account's CloudFormation/Lambda must `s3:GetObject` the nested templates + Lambda zips, and `kms:Decrypt` if encrypted. For a fully-private posture, use bucket-policy grants to the deployer account rather than the `public` flag (public ACLs conflict with "all private"). Pass `ArtifactsBucketKmsKeyArn` at deploy.
6. **Gaps to close in code/docs:** ACL-suppression option for Bucket-Owner-Enforced buckets; a publish flag to *not* create the bucket / target an existing cross-account bucket; optional assume-role support; a new SDLC CFN template for the publish (vs. deploy) pipeline.

**Open decisions:** direct cross-account write vs. assume-role; ACLs-enabled vs.
Bucket-Owner-Enforced on the destination bucket; public-read vs. private bucket-policy
read grants for the deploying account.

---

## BL-003 — Wrapper pattern to consume the solution and override configuration/resources

**Ask:** Can a customer write a "wrapper" that pulls in this solution and overrides
its configuration/resources (rather than forking the repo)?

**Answer in short:** Yes for configuration/parameters/behavior/added-resources;
**limited** for arbitrary internal-resource property changes. This is SAM/
CloudFormation (not CDK — see BL-002), so the wrapper is a parent CloudFormation
stack, and CloudFormation has no mechanism to reach into a nested stack and patch an
individual resource — a parent can only drive **parameters the child exposes**.

**Override surfaces, in order of preference (no fork):**

1. **Nested-stack wrapper (CFN-native).** A parent template nests the published
   `idp-main.yaml` via `AWS::CloudFormation::Stack` and passes `Parameters:` to
   override any exposed knob (`WebUIHosting`, `AppSyncVisibility`, `DeployInVPC`,
   `CustomConfigPath`, `ArtifactsBucketKmsKeyArn`, …). The parent can add its own
   sibling resources and consume child outputs. Limit: parameters only — no
   resource-level override of the child's internals.
2. **Configuration override (first-class).** `CustomConfigPath` parameter (or
   `idp-cli --custom-config`) points at customer YAML that overrides the built-in
   `config_library` presets in the DynamoDB Configuration Table — models, prompts,
   classes, extraction schemas, agentic settings, pricing. No wrapper required.
   See `docs/configuration.md`.
3. **Behavior override via Lambda hooks.** Post-processing hook
   (`docs/post-processing-lambda-hook.md`) and inference hooks
   (`docs/lambda-hook-inference.md`, `samples/lambda-hook-inference/` —
   bedrock-proxy, chandra-ocr, sagemaker) let the customer inject/replace OCR,
   model inference, and post-pipeline logic without editing the template.
4. **Added resources/UI via the Feature Platform.** `EnableFeaturePlatform`
   parameter + sibling feature stacks register against the main stack (AppSync
   resolvers, UI bundles, InstalledFeatures table) by consuming `Fn::ImportValue`
   exports (WebUIBucket, AppSync API ARN/URL, UserPool, …). Sanctioned way to *add*
   resources/UI. See `docs/feature-platform.md`,
   `docs/feature-platform-developer-guide.md`,
   `feature-platform/main-stack-extensions/apply-to-main-stack.md`.

**When the wrapper can't reach it:** to change an internal resource property that is
neither parameterized nor hook/feature-reachable, either (a) **add a parameter
upstream** in `template.yaml` and drive it from the wrapper (preferred; contribute
back), or (b) **fork the template** — viable since the customer already owns the
build (BL-002), but carries an upgrade-merge cost every release.

**Recommended layering:** nested-stack wrapper (parameters) + `CustomConfigPath`
(config) + Lambda hooks (behavior) + Feature Platform (added resources/UI). Covers
almost all override needs without forking; reserve forking for the rare
unparameterized resource change.

**Next step to scope this:** enumerate the *specific* resources/properties the
customer intends to override → classify each as parameter / config / hook / feature
(pure wrapper works) vs. unparameterized internal (needs upstream param or fork).

