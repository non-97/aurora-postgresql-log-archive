import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import { BaseConstructProps, BaseConstruct } from "./base-construct";
import { LambdaProperty, LogDestinationProperty } from "../../parameter";
import * as path from "path";

export interface LambdaConstructProps
  extends LambdaProperty,
    LogDestinationProperty,
    BaseConstructProps {}

export class LambdaConstruct extends BaseConstruct {
  readonly dbClusterPostgreSqlLogFilter: cdk.aws_lambda.IFunction;
  readonly dbClusterPostgreSqlLogUploader: cdk.aws_lambda.IFunction;

  constructor(scope: Construct, id: string, props: LambdaConstructProps) {
    super(scope, id, props);

    // IAM Policy
    const policy = new cdk.aws_iam.Policy(this, "Policy", {
      statements: [
        new cdk.aws_iam.PolicyStatement({
          effect: cdk.aws_iam.Effect.ALLOW,
          resources: ["*"],
          actions: ["xray:PutTelemetryRecords", "xray:PutTraceSegments"],
        }),
        new cdk.aws_iam.PolicyStatement({
          effect: cdk.aws_iam.Effect.ALLOW,
          resources: [
            `arn:aws:rds:${cdk.Stack.of(this).region}:${
              cdk.Stack.of(this).account
            }:cluster:*`,
          ],
          actions: ["rds:DescribeDBClusters"],
        }),
        new cdk.aws_iam.PolicyStatement({
          effect: cdk.aws_iam.Effect.ALLOW,
          resources: [
            `arn:aws:rds:${cdk.Stack.of(this).region}:${
              cdk.Stack.of(this).account
            }:db:*`,
          ],
          actions: ["rds:DescribeDBLogFiles", "rds:DownloadCompleteDBLogFile"],
        }),
        new cdk.aws_iam.PolicyStatement({
          effect: cdk.aws_iam.Effect.ALLOW,
          resources: [
            `arn:aws:s3:::${props.bucketName}`,
            `arn:aws:s3:::${props.bucketName}/*`,
          ],
          actions: ["s3:ListBucket", "s3:GetObject", "s3:PutObject"],
        }),
      ],
    });

    // IAM Role
    const role = new cdk.aws_iam.Role(this, "Role", {
      assumedBy: new cdk.aws_iam.ServicePrincipal("lambda.amazonaws.com"),
      managedPolicies: [
        cdk.aws_iam.ManagedPolicy.fromAwsManagedPolicyName(
          "service-role/AWSLambdaBasicExecutionRole"
        ),
      ],
    });
    role.attachInlinePolicy(policy);

    // Lambda Layer
    const lambdaPowertoolsLayer =
      cdk.aws_lambda.LayerVersion.fromLayerVersionArn(
        this,
        "lambdaPowertoolsLayer",
        `arn:aws:lambda:${
          cdk.Stack.of(this).region
        }:017000801446:layer:AWSLambdaPowertoolsPythonV3-python313-arm64:4`
      );

    // Lambda Function
    const dbClusterPostgreSqlLogFilter = new cdk.aws_lambda.Function(
      this,
      "DbClusterPostgreSqlLogFilter",
      {
        runtime: cdk.aws_lambda.Runtime.PYTHON_3_13,
        handler: "index.lambda_handler",
        code: cdk.aws_lambda.Code.fromAsset(
          path.join(__dirname, "../src/lambda/db_cluster_postgresql_log_filter")
        ),
        role,
        architecture: cdk.aws_lambda.Architecture.ARM_64,
        timeout: cdk.Duration.seconds(30),
        tracing: cdk.aws_lambda.Tracing.ACTIVE,
        logRetention: cdk.aws_logs.RetentionDays.ONE_YEAR,
        loggingFormat: cdk.aws_lambda.LoggingFormat.JSON,
        applicationLogLevelV2: props.functionApplicationLogLevel,
        systemLogLevelV2: props.functionSystemLogLevel,
        layers: [lambdaPowertoolsLayer],
        environment: {
          POWERTOOLS_LOG_LEVEL: props.powertoolsLogLevel || "INFO",
          POWERTOOLS_SERVICE_NAME: "db-cluster-postgresql-log-filter",
        },
      }
    );
    role.node.tryRemoveChild("DefaultPolicy");
    this.dbClusterPostgreSqlLogFilter = dbClusterPostgreSqlLogFilter;

    const dbClusterPostgreSqlLogUploader = new cdk.aws_lambda.Function(
      this,
      "DbClusterPostgreSqlLogUploader",
      {
        runtime: cdk.aws_lambda.Runtime.PYTHON_3_13,
        handler: "index.lambda_handler",
        code: cdk.aws_lambda.Code.fromAsset(
          path.join(
            __dirname,
            "../src/lambda/db_cluster_postgresql_log_uploader"
          )
        ),
        role,
        architecture: cdk.aws_lambda.Architecture.ARM_64,
        memorySize: props.uploaderMemorySize ?? 1024,
        timeout: props.uploaderTimeout ?? cdk.Duration.seconds(600),
        ephemeralStorageSize:
          props.uploaderEphemeralStorageSize ?? cdk.Size.gibibytes(2),
        tracing: cdk.aws_lambda.Tracing.ACTIVE,
        logRetention: cdk.aws_logs.RetentionDays.ONE_YEAR,
        loggingFormat: cdk.aws_lambda.LoggingFormat.JSON,
        applicationLogLevelV2: props.functionApplicationLogLevel,
        systemLogLevelV2: props.functionSystemLogLevel,
        layers: [lambdaPowertoolsLayer],
        environment: {
          POWERTOOLS_LOG_LEVEL: props.powertoolsLogLevel || "INFO",
          POWERTOOLS_SERVICE_NAME: "db-cluster-postgresql-log-uploader",
        },
      }
    );
    role.node.tryRemoveChild("DefaultPolicy");
    this.dbClusterPostgreSqlLogUploader = dbClusterPostgreSqlLogUploader;
  }
}
