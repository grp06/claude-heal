import sys
import pathlib
from datetime import datetime

DEBUG_LOG_ENABLED = True

_log_file_path = None


def _ensure_log_file_path() -> pathlib.Path:
    global _log_file_path
    if _log_file_path is None:
        script_dir = pathlib.Path(__file__).resolve().parent
        debug_dir = script_dir / "debug"
        debug_dir.mkdir(exist_ok=True)
        file_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        _log_file_path = debug_dir / f"hook_{file_timestamp}.log"
    return _log_file_path


def _is_enabled() -> bool:
    return DEBUG_LOG_ENABLED


def debug_log(message: str) -> None:
    if not _is_enabled():
        return
    try:
        log_path = _ensure_log_file_path()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        with open(log_path, "a") as f:
            f.write(f"[{timestamp}] {message}\n")
            f.flush()
    except Exception as e:
        try:
            sys.stderr.write(f"DEBUG_LOG_ERROR: {str(e)}\n")
            sys.stderr.flush()
        except Exception:
            pass


