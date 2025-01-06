from dataclasses import dataclass
from typing import Dict, Any


@dataclass(frozen=True)
class LogFile:
    """ログファイル情報を表すデータクラス"""

    LastWritten: int
    LogFileName: str
    ObjectKey: str

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "LastWritten": self.LastWritten,
            "LogFileName": self.LogFileName,
            "ObjectKey": self.ObjectKey,
        }
