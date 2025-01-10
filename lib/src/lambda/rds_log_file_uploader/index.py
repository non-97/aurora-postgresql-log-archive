import sys
import os
import tempfile
from typing import Dict, Any
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.utilities.typing import LambdaContext

from rds_log_file_downloader import RdsLogFileDownloader, RdsLogDownLoaderConfig
from rds_log_file_uploader import RdsFileLogUploader, RdsFileLogUploaderConfig

logger = Logger()
tracer = Tracer()


@logger.inject_lambda_context
@tracer.capture_lambda_handler
def lambda_handler(event: Dict[str, Any], context: LambdaContext) -> Dict[str, Any]:
    """Lambda関数のハンドラー"""
    try:
        logger.debug("Processing event", extra={"event": event})

        rds_log_file_downloader_config = RdsLogDownLoaderConfig(
            db_instance_identifier=event["DbInstanceIdentifier"],
            log_file_name=event["LogFileName"],
        )

        rds_log_file_uploader_config = RdsFileLogUploaderConfig(
            db_instance_identifier=event["DbInstanceIdentifier"],
            log_destination_bucket=event["LogDestinationBucket"],
            last_written=event["LastWritten"],
            object_key=event["ObjectKey"],
        )

        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_path = temp_file.name

        try:
            downloader = RdsLogFileDownloader(rds_log_file_downloader_config)
            if not downloader.download_log_file(temp_path):
                raise Exception("Failed to download log file")

            uploader = RdsFileLogUploader(rds_log_file_uploader_config)
            if not uploader.upload_log_file(
                temp_path,
            ):
                raise Exception("Failed to upload log file")

            return {
                "statusCode": 200,
                "body": {
                    "message": "Successfully processed log file",
                    "db_instance": event["DbInstanceIdentifier"],
                    "log_file": event["LogFileName"],
                    "object_key": event["ObjectKey"],
                    "last_written": event["LastWritten"],
                },
            }

        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    except Exception as e:
        logger.exception("Unexpected error", error=str(e))
        sys.exit(1)
