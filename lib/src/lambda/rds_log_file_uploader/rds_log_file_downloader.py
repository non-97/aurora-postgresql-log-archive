import os
import time
import urllib.request
import urllib.error
from http.client import IncompleteRead
from dataclasses import dataclass
import boto3
from botocore.awsrequest import AWSRequest
import botocore.auth as auth
from aws_lambda_powertools import Logger, Tracer

from rds_log_file_uploader_constants import (
    DEFAULT_RETRIES,
    DEFAULT_RETRY_DELAY,
    CHUNK_SIZE,
)

logger = Logger()
tracer = Tracer()


@dataclass(frozen=True)
class RdsLogDownLoaderConfig:
    """RdsLogFileDownloader の設定値を管理するデータクラス"""

    db_instance_identifier: str
    log_file_name: str

    def __post_init__(self) -> None:
        """初期化後のバリデーション"""
        if not self.db_instance_identifier:
            raise ValueError("DbInstanceIdentifier is required")
        if not self.log_file_name:
            raise ValueError("LogFileName is required")


class RdsLogFileDownloader:
    """RDSログをダウンロードするクラス"""

    def __init__(self, config: RdsLogDownLoaderConfig, region: str = None):
        self.config = config
        self.session = boto3.Session(region_name=region)
        self.region = self.session.region_name or os.environ.get("AWS_REGION")

        self.credentials = self.session.get_credentials()
        self.remote_host = f"rds.{self.region}.amazonaws.com"

    def _get_signed_request(self, url: str) -> urllib.request.Request:
        """署名付きリクエストを作成"""
        sigv4auth = auth.SigV4Auth(self.credentials, "rds", self.region)
        awsreq = AWSRequest(method="GET", url=url)
        sigv4auth.add_auth(awsreq)

        return urllib.request.Request(
            url=url,
            headers={
                "Authorization": awsreq.headers["Authorization"],
                "Host": self.remote_host,
                "X-Amz-Date": awsreq.context["timestamp"],
                "X-Amz-Security-Token": self.credentials.token,
            },
        )

    @tracer.capture_method
    def download_log_file(
        self,
        output_path: str,
        retries: int = DEFAULT_RETRIES,
        delay: int = DEFAULT_RETRY_DELAY,
    ) -> bool:
        """
        RDSログファイルをダウンロード

        Args:
            output_path: 出力ファイルパス
            retries: リトライ回数
            delay: リトライ間隔（秒）

        Returns:
            bool: ダウンロード成功時True
        """

        base_url = f"https://{self.remote_host}/v13/downloadCompleteLogFile/{self.config.db_instance_identifier}/"

        logger.info(
            "Starting log file download",
            extra={
                "db_instance_identifier": self.config.db_instance_identifier,
                "log_file_name": self.config.log_file_name,
                "output_path": output_path,
            },
        )

        for attempt in range(retries):
            try:
                url = base_url + self.config.log_file_name
                req = self._get_signed_request(url)

                with (
                    urllib.request.urlopen(req) as response,
                    open(output_path, "wb") as out_file,
                ):
                    while True:
                        chunk = response.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        out_file.write(chunk)

                # ファイルサイズに関係なくダウンロード成功とみなす
                logger.info(
                    "Successfully downloaded log file",
                    extra={
                        "db_instance_identifier": self.config.db_instance_identifier,
                        "log_file_name": self.config.log_file_name,
                        "size": os.path.getsize(output_path),
                    },
                )
                return True

            except IncompleteRead as e:
                logger.warning(
                    "Incomplete read error",
                    extra={"attempt": attempt + 1, "retries": retries, "error": str(e)},
                )
            except Exception as e:
                logger.error(
                    "Download error",
                    extra={"attempt": attempt + 1, "retries": retries, "error": str(e)},
                )

            time.sleep(delay)

        logger.error(
            "Failed to download log file after all retries",
            extra={
                "db_instance_identifier": self.config.db_instance_identifier,
                "log_file_name": self.config.log_file_name,
            },
        )
        return False
