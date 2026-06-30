# Deployment Architecture Diagrams

Conceptual architecture diagrams for the GenAIIDP deployment modes, networking
options, and downstream (Amazon MQ) integration patterns. They are intentionally
**logical, not exhaustive** — focused on the trust/network boundaries and the
parameter that selects each mode, so they stay readable.

> These diagrams illustrate the deployment options discussed in
> [`../../BACKLOG.md`](../../BACKLOG.md), [ALB Hosting](../alb-hosting.md),
> [Deployment in a Private Network](../deployment-private-network.md),
> [Headless Deployment](../headless-deployment.md), and
> [Post-Processing Lambda Hook](../post-processing-lambda-hook.md).

## Diagrams

| File | Mode / option | Key parameters |
|------|---------------|----------------|
| `01_cloudfront_s3_public.png` | **Standard hosting** — CloudFront + S3, public | `WebUIHosting=CloudFront` (default) |
| `02_alb_s3_invpc_endpoints.png` | **Private hosting** — internal ALB + S3 via VPC endpoints, all Lambdas in-VPC, PRIVATE AppSync + Route 53 PHZ | `WebUIHosting=ALB`, `ALBScheme=internal`, `AppSyncVisibility=PRIVATE`, `DeployInVPC=true` |
| `05_headless_jobs_api.png` | **Headless** — private Jobs REST API, no UI/CloudFront/AppSync | `EnableHeadless=true`, `DeployInVPC=true`, `ApiGatewayVpcEndpointId` |
| `03_mq_eventbridge_relay.png` | **MQ integration — Option A (recommended)** — cross-account EventBridge relay → local publisher → Amazon MQ | post-processing hook + EventBridge |
| `04_mq_direct_privatelink.png` | **MQ integration — Option B** — post-processing hook → SQS buffer → VPC publisher → PrivateLink → cross-account broker | `PostProcessingLambdaHookFunctionArn`, PrivateLink/peering |
| `06_target_private_full.png` | **Combined target** — private ALB UI + AppSync + Jobs API + S3, all via VPC endpoints, Cognito + Ping (SAML/OIDC) federation, cross-account post to Amazon MQ | all of the above combined |
| `07_build_pipeline_crossaccount.png` | **Customer-owned build (optional)** — CodeBuild *or* Bitbucket Pipelines runs `idp-cli publish`, pushes artifacts to a private S3 bucket in a different account, then CloudFormation points at `idp-main.yaml` there | see `BACKLOG.md` BL-002 |

> **Notes on `07_build_pipeline_crossaccount.png`** (detail in `BACKLOG.md` BL-002):
> the artifact **bucket name is baked into `idp-main.yaml` at publish time** (SAM
> `sam package` rewrites `CodeUri`/`TemplateURL` to `s3://<bucket>/...`), so the
> pipeline must publish **directly to the destination bucket** — build-here-copy-
> there breaks the references. Cross-account write is cleanest via **assume-role**
> into account B; on a **Bucket-Owner-Enforced** bucket the publisher must not send
> object ACLs. Docker/ECR is required because Pattern-2 Lambdas are container
> images. CloudFormation/Lambda in the deploy account need `s3:GetObject` +
> `kms:Decrypt` on the bucket/CMK.

> **⚠ Caveat on `06_target_private_full.png`:** Amazon Cognito (`cognito-idp`)
> does **not** currently offer a native interface VPC endpoint (PrivateLink) in
> commercial regions — the private-network docs note "Cognito has no VPC endpoint
> — browser egress only." The Cognito VPCE in this diagram is drawn as a *target*
> and flagged ⚠; realistic options today are browser egress to public Cognito over
> the corporate network, or a reverse-proxy fronting the Cognito Hosted UI. Also,
> running the full ALB UI (AppSync) **and** the private Jobs API in one stack is
> the decoupling described in `BACKLOG.md` BL-001 (today the Jobs API requires
> headless mode).

## Colour / edge convention

| Style | Meaning |
|-------|---------|
| Green edge | Private / in-VPC traffic |
| Red edge | Public-internet traffic |
| Dashed orange | DNS resolution (e.g. Route 53 private hosted zone) |
| Dashed navy | Asynchronous / event-driven |
| Dotted grey | Optional / credential lookup |

## Regenerating

The diagrams are generated from [`generate_deployment_diagrams.py`](./generate_deployment_diagrams.py)
using the [`diagrams`](https://diagrams.mingrammer.com/) library, which renders
via Graphviz.

### Prerequisites

```bash
# Python wrapper
pip install diagrams

# Graphviz `dot` binary (one of):
scoop install graphviz       # Windows (scoop)
conda install -c conda-forge graphviz
winget install Graphviz.Graphviz
brew install graphviz         # macOS
apt-get install graphviz      # Debian/Ubuntu
```

`dot` must be on `PATH` at render time (the `diagrams` library shells out to it).

### Run

```bash
python docs/diagrams/generate_deployment_diagrams.py
```

PNGs are written next to the script. To edit a diagram, change the corresponding
`with Diagram(...)` block and re-run — node classes come from
`diagrams.aws.*` (e.g. `CloudFront`, `ALB`, `Endpoint`, `Appsync`, `MQ`,
`Bedrock`, `Textract`).

> **Note:** these are conceptual reference diagrams maintained by hand alongside
> the source script — they are not auto-generated from `template.yaml`. When a
> deployment mode changes materially, update the script and regenerate.
