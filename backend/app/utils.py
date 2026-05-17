"""共通ユーティリティ"""
import math
from typing import Any


def clean_for_json(obj: Any) -> Any:
    """再帰的にNaN/Infをnullに変換"""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: clean_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean_for_json(v) for v in obj]
    return obj
