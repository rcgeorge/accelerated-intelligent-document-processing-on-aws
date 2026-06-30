#!/usr/bin/env python3
"""
Generate architecture diagrams for GenAIIDP deployment modes and options.

Requires:
    pip install diagrams      # Python wrapper
    Graphviz `dot` on PATH    # rendering engine (scoop/conda/winget install graphviz)

Run:
    python docs/diagrams/generate_deployment_diagrams.py

Outputs PNGs next to this script:
    01_cloudfront_s3_public.png
    02_alb_s3_invpc_endpoints.png
    03_mq_eventbridge_relay.png
    04_mq_direct_privatelink.png
    05_headless_jobs_api.png
"""

import os

from diagrams import Cluster, Diagram, Edge
from diagrams.aws.compute import ECR, Lambda
from diagrams.aws.database import Dynamodb
from diagrams.aws.devtools import Codebuild
from diagrams.aws.general import Users
from diagrams.aws.integration import MQ, SQS, Eventbridge, StepFunctions
from diagrams.aws.management import Cloudformation, CloudformationStack
from diagrams.aws.ml import Bedrock, Textract
from diagrams.aws.mobile import Appsync
from diagrams.aws.network import (
    ALB,
    APIGateway,
    CloudFront,
    DirectConnect,
    Endpoint,
    Privatelink,
    Route53HostedZone,
    VPCPeering,
)
from diagrams.aws.security import KMS, WAF, Cognito, IAMRole, SecretsManager
from diagrams.aws.storage import S3
from diagrams.generic.blank import Blank

OUT = os.path.dirname(os.path.abspath(__file__))

# Consistent edge styles
PRIV = Edge(color="darkgreen")  # private / in-VPC traffic
PUB = Edge(color="firebrick")  # public-internet traffic
DNS = Edge(color="darkorange", style="dashed")  # DNS resolution
ASYNC = Edge(color="navy", style="dashed")  # async / event

GRAPH_ATTR = {"fontsize": "20", "bgcolor": "white", "pad": "0.5", "splines": "spline"}


def fp(name):
    return os.path.join(OUT, name)


# ---------------------------------------------------------------------------
# 1. Standard public deployment: CloudFront + S3
# ---------------------------------------------------------------------------
with Diagram(
    "GenAIIDP — Standard Hosting (CloudFront + S3, public)",
    filename=fp("01_cloudfront_s3_public"),
    show=False,
    direction="LR",
    graph_attr=GRAPH_ATTR,
):
    users = Users("End users\n(public internet)")

    with Cluster("Web UI + Auth (public, AWS-managed)"):
        waf = WAF("WAF WebACL")
        cf = CloudFront("CloudFront\n(WebUIHosting=CloudFront)")
        web = S3("WebUI bucket\n(OAI)")
        cognito = Cognito("Cognito\nUser Pool")
        appsync = Appsync("AppSync GraphQL\n(Visibility=GLOBAL)")

    with Cluster("Backend (AWS-managed network)"):
        resolvers = Lambda("AppSync\nresolver Lambdas")
        ddb = Dynamodb("DynamoDB\n(tracking/config)")

    with Cluster("Document pipeline"):
        inp = S3("Input bucket")
        eb = Eventbridge("EventBridge")
        q = SQS("Queue")
        sfn = StepFunctions("Step Functions\nworkflow")
        ocr = Textract("OCR (Textract)")
        bed = Bedrock("Classify / Extract\n(Bedrock)")
        out = S3("Output bucket")

    users >> PUB >> waf >> cf >> web
    users >> PUB >> cognito
    users >> PUB >> appsync >> resolvers >> ddb

    users >> PUB >> inp
    inp >> ASYNC >> eb >> q >> sfn
    sfn >> ocr
    sfn >> bed
    sfn >> out


# ---------------------------------------------------------------------------
# 2. Private deployment: ALB + S3, in-VPC, VPC endpoints
# ---------------------------------------------------------------------------
with Diagram(
    "GenAIIDP — Private Hosting (ALB + S3, DeployInVPC=true, VPC endpoints)",
    filename=fp("02_alb_s3_invpc_endpoints"),
    show=False,
    direction="LR",
    graph_attr=GRAPH_ATTR,
):
    users = Users("End users")
    cognito = Cognito("Cognito\n(no VPC endpoint —\nbrowser egress only)")

    with Cluster("Corporate network"):
        dx = DirectConnect("VPN / Direct Connect")

    with Cluster("Customer VPC"):
        with Cluster("ALB subnets"):
            alb = ALB("Internal ALB\n(ALBScheme=internal)")

        with Cluster("Private subnets"):
            lambdas = Lambda("~21 app Lambdas\n(resolvers + pipeline)")

        with Cluster("Interface VPC Endpoints"):
            s3e = Endpoint("S3 (interface)")
            appe = Endpoint("AppSync")
            bede = Endpoint("Bedrock")
            txte = Endpoint("Textract")
            misce = Endpoint("SQS / States / KMS /\nLogs / SSM / STS …")

        with Cluster("Gateway endpoints"):
            ddbg = Endpoint("DynamoDB (gw)")
            s3g = Endpoint("S3 (gw)")

        appsync = Appsync("AppSync GraphQL\n(Visibility=PRIVATE)")
        phz = Route53HostedZone("Route 53 PHZ\n(appsync-api +\nrealtime hostnames)")
        web = S3("WebUI bucket\n(aws:sourceVpce)")
        ddb = Dynamodb("DynamoDB")
        bedrock = Bedrock("Bedrock")
        textract = Textract("Textract")

    # UI path
    users >> PRIV >> dx >> alb
    alb >> PRIV >> s3e >> web
    # Auth + API resolution
    users >> PUB >> cognito
    users >> DNS >> phz >> appe
    dx >> PRIV >> appe >> appsync >> lambdas
    # Lambda egress via endpoints
    lambdas >> PRIV >> bede >> bedrock
    lambdas >> PRIV >> txte >> textract
    lambdas >> PRIV >> ddbg >> ddb
    lambdas >> PRIV >> misce
    lambdas >> PRIV >> s3g
    lambdas >> PRIV >> appe


# ---------------------------------------------------------------------------
# 3. MQ integration — Option A (recommended): cross-account EventBridge relay
# ---------------------------------------------------------------------------
with Diagram(
    "MQ Integration — Option A: cross-account EventBridge relay (recommended)",
    filename=fp("03_mq_eventbridge_relay"),
    show=False,
    direction="LR",
    graph_attr=GRAPH_ATTR,
):
    with Cluster("IDP account"):
        sfn = StepFunctions("Step Functions\nSUCCEEDED")
        eb = Eventbridge("EventBridge\nrule")
        out = S3("Output bucket\n(full results)")

    with Cluster("Consumer account (B)"):
        ebb = Eventbridge("Custom event bus\n(resource policy\ngrants IDP account)")
        relay = Lambda("Relay / publisher\nLambda")
        mq = MQ("Amazon MQ\nbroker")

    sfn >> ASYNC >> eb
    (
        eb
        >> Edge(
            label="cross-account\nevent (S3 pointers)", color="navy", style="dashed"
        )
        >> ebb
    )
    ebb >> relay >> mq
    (
        relay
        >> Edge(label="read full results\n(cross-account S3, optional)", style="dotted")
        >> out
    )


# ---------------------------------------------------------------------------
# 4. MQ integration — Option B: direct to MQ via PrivateLink + SQS buffer
# ---------------------------------------------------------------------------
with Diagram(
    "MQ Integration — Option B: direct publish via SQS buffer + PrivateLink",
    filename=fp("04_mq_direct_privatelink"),
    show=False,
    direction="LR",
    graph_attr=GRAPH_ATTR,
):
    with Cluster("IDP account"):
        sfn = StepFunctions("Step Functions\nSUCCEEDED")
        eb = Eventbridge("EventBridge")
        hook = Lambda("Post-processing\nhook Lambda")
        buf = SQS("SQS buffer\n(+ DLQ)")
        secret = SecretsManager("Secrets Manager\n(broker creds)")
        kms = KMS("KMS")

        with Cluster("VPC — private subnets"):
            pub = Lambda("Publisher Lambda\n(VPC-attached)")
            pl = Privatelink("PrivateLink\nendpoint")

    with Cluster("Consumer account (B)"):
        peer = VPCPeering("PrivateLink svc / NLB\n(or VPC peering / TGW)")
        with Cluster("MQ VPC"):
            mq = MQ("Amazon MQ\nbroker")

    sfn >> ASYNC >> eb >> hook >> buf >> pub
    secret >> Edge(style="dotted") >> pub
    kms >> Edge(style="dotted") >> secret
    pub >> PRIV >> pl
    pl >> Edge(label="OpenWire/AMQP 443/5671", color="darkgreen") >> peer >> mq


# ---------------------------------------------------------------------------
# 5. Headless mode: private Jobs REST API (EnableHeadless=true)
# ---------------------------------------------------------------------------
with Diagram(
    "GenAIIDP — Headless Mode (private Jobs API, EnableHeadless=true)",
    filename=fp("05_headless_jobs_api"),
    show=False,
    direction="LR",
    graph_attr=GRAPH_ATTR,
):
    client = Users("CLI / SDK / app\n(M2M client)")

    with Cluster("Corporate network"):
        dx = DirectConnect("VPN / Direct Connect")

    with Cluster("IDP account — headless (no UI / CloudFront / AppSync)"):
        cognito = Cognito("ApiUserPool\n(dedicated M2M pool,\nclient_credentials)")

        with Cluster("Customer VPC"):
            apie = Endpoint("execute-api\nInterface VPCE")
            api = APIGateway(
                "Private API Gateway\n(Type=PRIVATE; resource policy\ndenies != aws:SourceVpce)"
            )

            with Cluster("Private subnets"):
                handler = Lambda("API handler\nLambdas (VPC)")

            with Cluster("VPC endpoints"):
                svce = Endpoint("Bedrock / Textract /\nSQS / States / KMS …")

            inp = S3("Input bucket")
            sfn = StepFunctions("Step Functions\nworkflow")
            ocr = Textract("OCR (Textract)")
            bed = Bedrock("Classify / Extract\n(Bedrock)")
            out = S3("Output bucket")
            ddb = Dynamodb("DynamoDB\n(tracking)")
            eb = Eventbridge("EventBridge")

    # Auth + request path
    client >> PUB >> cognito
    client >> PRIV >> dx >> apie >> api >> handler
    # Job submission + status
    handler >> PRIV >> inp
    handler >> PRIV >> ddb
    handler >> PRIV >> out
    handler >> PRIV >> svce
    # Pipeline
    inp >> ASYNC >> eb >> sfn
    sfn >> ocr
    sfn >> bed
    sfn >> out


# ---------------------------------------------------------------------------
# 6. Combined target: private ALB UI + AppSync + Jobs API + Cognito/Ping
#    federation + cross-account MQ
# ---------------------------------------------------------------------------
with Diagram(
    "GenAIIDP — Target: Private ALB UI + AppSync + Jobs API + Cognito/Ping + cross-account MQ",
    filename=fp("06_target_private_full"),
    show=False,
    direction="LR",
    graph_attr=GRAPH_ATTR,
):
    users = Users("End users")
    ping = Blank("Ping IdP\n(PingFederate / PingOne\nSAML / OIDC)")

    with Cluster("Corporate network"):
        dx = DirectConnect("VPN / Direct Connect")

    with Cluster("IDP account"):
        with Cluster("Customer VPC"):
            with Cluster("ALB subnets"):
                alb = ALB("Internal ALB\n(ALBScheme=internal)")

            with Cluster("Private subnets"):
                lam = Lambda("App + AppSync resolver\n+ API-handler Lambdas")
                pub = Lambda("MQ publisher\nLambda")

            with Cluster("Interface VPC endpoints"):
                s3e = Endpoint("S3")
                appe = Endpoint("AppSync")
                coge = Endpoint(
                    "Cognito-idp\n(⚠ no native PrivateLink —\nverify / proxy)"
                )
                apie = Endpoint("execute-api")
                bede = Endpoint("Bedrock")
                txte = Endpoint("Textract")
                misce = Endpoint(
                    "SQS / States / KMS /\nLogs / SSM / STS /\nSecretsManager"
                )

            with Cluster("Gateway endpoints"):
                s3g = Endpoint("S3 (gw)")
                ddbg = Endpoint("DynamoDB (gw)")

            appsync = Appsync("AppSync GraphQL\n(Visibility=PRIVATE)")
            apigw = APIGateway("Private API Gateway\n(Type=PRIVATE)")
            web = S3("WebUI bucket\n(aws:sourceVpce)")
            ddb = Dynamodb("DynamoDB")
            bed = Bedrock("Bedrock")
            txt = Textract("Textract")
            cog = Cognito("Cognito User Pool\n(external IdP = Ping)")
            phz = Route53HostedZone("Route 53 PHZ\n(appsync-api + realtime)")

        with Cluster("Result fan-out → cross-account MQ"):
            sfn = StepFunctions("Step Functions\nSUCCEEDED")
            eb = Eventbridge("EventBridge")
            hook = Lambda("Post-processing\nhook Lambda")
            buf = SQS("SQS buffer\n(+ DLQ)")
            secret = SecretsManager("Secrets Manager\n(broker creds)")
            pl = Privatelink("PrivateLink\nendpoint")

    with Cluster("Consumer account (B)"):
        peer = VPCPeering("PrivateLink svc / NLB\n(or peering / TGW)")
        with Cluster("MQ VPC"):
            mq = MQ("Amazon MQ\nbroker")

    # --- UI hosting path ---
    users >> PRIV >> dx >> alb
    alb >> PRIV >> s3e >> web

    # --- Auth: Cognito + Ping federation ---
    users >> PRIV >> coge >> cog
    cog >> Edge(label="SAML / OIDC federation", color="firebrick") >> ping

    # --- GraphQL (UI backend) ---
    users >> DNS >> phz >> appe
    dx >> PRIV >> appe >> appsync >> lam

    # --- Jobs REST API ---
    dx >> PRIV >> apie >> apigw >> lam

    # --- Lambda egress via endpoints ---
    lam >> PRIV >> bede >> bed
    lam >> PRIV >> txte >> txt
    lam >> PRIV >> ddbg >> ddb
    lam >> PRIV >> s3g
    lam >> PRIV >> misce

    # --- Result fan-out to cross-account MQ ---
    sfn >> ASYNC >> eb >> hook >> buf >> pub
    secret >> Edge(style="dotted") >> pub
    pub >> PRIV >> pl
    pl >> Edge(label="OpenWire / AMQP", color="darkgreen") >> peer >> mq


# ---------------------------------------------------------------------------
# 7. Customer-owned build pipeline: CodeBuild / Bitbucket → cross-account S3
#    artifacts → CloudFormation deploy (BL-002)
# ---------------------------------------------------------------------------
with Diagram(
    "GenAIIDP — Customer-owned build: CI publish → cross-account artifact bucket → CloudFormation",
    filename=fp("07_build_pipeline_crossaccount"),
    show=False,
    direction="LR",
    graph_attr=GRAPH_ATTR,
):
    repo = Blank("Solution source\n(Bitbucket / Git repo)")

    with Cluster("Build account (A) — CI/CD"):
        with Cluster("Build runner (choose one)"):
            cb = Codebuild("CodeBuild\n(privileged: Docker,\nSAM, Python, Node)")
            bb = Blank("— or —\nBitbucket Pipelines\n(self-hosted/cloud runner)")
        builder = Lambda("idp-cli publish\n(sam build + package)")
        role = IAMRole("Cross-account\npublish role\n(sts:AssumeRole)")

    with Cluster("Artifact + deploy account (B)"):
        with Cluster("Private artifact bucket"):
            s3art = S3(
                "S3 artifact bucket\n(exact name baked into\nidp-main.yaml;\nKMS, Bucket-Owner-Enforced)"
            )
            kms = KMS("KMS CMK")
        ecr = ECR("ECR\n(Pattern-2 images)")
        cfn = Cloudformation("CloudFormation\n(points at idp-main.yaml)")
        stack = CloudformationStack(
            "Deployed IDP stack\n(main + nested + Lambdas\nfetched from bucket)"
        )

    # Source → build
    repo >> cb
    repo >> bb
    cb >> builder
    bb >> builder

    # Build outputs
    (
        builder
        >> Edge(label="zip/layers + nested\ntemplates + config", color="darkgreen")
        >> role
    )
    role >> Edge(label="PutObject\n(assume-role into B)", color="darkgreen") >> s3art
    builder >> Edge(label="docker push", color="navy", style="dashed") >> ecr
    kms >> Edge(style="dotted", label="encrypt") >> s3art

    # Deploy
    s3art >> Edge(label="GetObject (templates,\nLambda zips)", color="darkgreen") >> cfn
    cfn >> stack
    ecr >> Edge(style="dotted", label="image pull\nat create") >> stack


print("Diagrams written to:", OUT)
