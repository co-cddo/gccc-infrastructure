import os
import boto3
import time
import json

AWS_REGION = os.getenv("AWS_REGION", "eu-west-2")
ATHENA_OUTPUT_S3_URI = os.getenv("ATHENA_OUTPUT_S3_URI")

catalog_name = "AwsDataCatalog"


def get_databases() -> list:
    databases = []

    athena = boto3.client("athena", region_name=AWS_REGION)

    paginator = athena.get_paginator("list_databases")
    response_iterator = paginator.paginate(CatalogName=catalog_name)

    for page in response_iterator:
        databases.extend((i["Name"] for i in page["DatabaseList"]))

    return databases


def get_tables(database_name: str) -> dict:
    tables = {}

    athena = boto3.client("athena", region_name=AWS_REGION)

    paginator = athena.get_paginator("list_table_metadata")
    response_iterator = paginator.paginate(
        CatalogName=catalog_name, DatabaseName=database_name
    )
    for page in response_iterator:
        for i in page["TableMetadataList"]:
            if i["Name"] not in tables:
                tables[i["Name"]] = i

    return tables


def get_partitioned_tables() -> dict:
    tables = {}
    for database in get_databases():
        all_tables = get_tables(database_name=database)
        for table_name in all_tables:
            table = all_tables[table_name]
            partitions = len(table.get("PartitionKeys", []))
            if partitions > 0:
                tables[table_name] = {"database": database, "partitions": partitions}
    return tables


def load_patitions(database, table_name, max_execution=20) -> dict:
    if not ATHENA_OUTPUT_S3_URI:
        return {"error": "ATHENA_OUTPUT_S3_URI not set"}

    try:
        athena = boto3.client("athena", region_name=AWS_REGION)

        sql = f"MSCK REPAIR TABLE `{table_name}`;"

        execution = athena.start_query_execution(
            QueryString=sql,
            QueryExecutionContext={
                "Database": database,
                "Catalog": catalog_name,
            },
            WorkGroup="primary",
            ResultConfiguration={
                "OutputLocation": ATHENA_OUTPUT_S3_URI,
                "EncryptionConfiguration": {
                    "EncryptionOption": "SSE_S3",
                },
            },
            ResultReuseConfiguration={
                "ResultReuseByAgeConfiguration": {
                    "Enabled": False,
                }
            },
        )

        execution_id = execution["QueryExecutionId"]
        state = "RUNNING"

        while max_execution > 0 and state in ["RUNNING", "QUEUED"]:
            max_execution = max_execution - 1
            response = athena.get_query_execution(QueryExecutionId=execution_id)

            if (
                "QueryExecution" in response
                and "Status" in response["QueryExecution"]
                and "State" in response["QueryExecution"]["Status"]
            ):
                state = response["QueryExecution"]["Status"]["State"]
                if state == "FAILED":
                    return {"error": "athena_failed"}
                elif state == "SUCCEEDED":
                    return athena.get_query_results(QueryExecutionId=execution_id)

            time.sleep(4)

    except Exception as e:
        return {"error": str(e)}

    return {"error": "timeout"}


def process_tables():
    ptables = get_partitioned_tables()

    for table_name in ptables:
        database = ptables[table_name]["database"]
        print(
            json.dumps(
                {
                    "message": "Running 'MSCK REPAIR TABLE' on table",
                    "table_name": table_name,
                    "database": database,
                },
                default=str,
            )
        )
        lp = load_patitions(database=database, table_name=table_name, max_execution=5)
        print(
            json.dumps(
                {
                    "result": lp,
                    "table_name": table_name,
                    "database": database,
                },
                default=str,
            )
        )


def lambda_handler(event, context):
    process_tables()
