#!/usr/bin/env node
import * as cdk from "aws-cdk-lib";
import { AuroraPostgresqlLogArchiveStack } from "../lib/aurora-postgresql-log-archive-stack";
import { auroraPostgreSqlLogArchiveStackProperty } from "../parameter/index";

const app = new cdk.App();
new AuroraPostgresqlLogArchiveStack(app, "AuroraPostgresqlLogArchiveStack", {
  env: auroraPostgreSqlLogArchiveStackProperty.env,
  ...auroraPostgreSqlLogArchiveStackProperty.props,
});
