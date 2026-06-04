from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Any

from .models import BatchOptions
from .pipeline import translate_directory


EVENT_PREFIX = "__MANGA_TRANSLATOR_EVENT__ "


class StopFile:
    def __init__(self, path: Path | None) -> None:
        self.path = path

    def is_set(self) -> bool:
        return self.path is not None and self.path.exists()


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        emit({"type": "fatal", "message": "缺少 worker 参数文件。"})
        return 2

    try:
        payload = json.loads(Path(args[0]).read_text(encoding="utf-8"))
        options = options_from_payload(payload)
        stop_file = Path(payload["stop_file"]) if payload.get("stop_file") else None
        stats = translate_directory(
            options,
            progress=emit,
            stop_event=StopFile(stop_file),
        )
        emit({"type": "worker_done", "stats": stats.as_dict()})
        return 0
    except Exception as exc:
        emit(
            {
                "type": "fatal",
                "message": str(exc),
                "traceback": traceback.format_exc(),
            }
        )
        return 1


def options_from_payload(payload: dict[str, Any]) -> BatchOptions:
    font_path = Path(payload["font_path"]) if payload.get("font_path") else None
    return BatchOptions(
        input_dir=Path(payload["input_dir"]),
        output_dir=Path(payload["output_dir"]),
        ocr_lang=payload.get("ocr_lang", "ch"),
        source_lang=payload.get("source_lang", "auto"),
        target_lang=payload.get("target_lang", "zh-CN"),
        translator=payload.get("translator", "auto"),
        recursive=bool(payload.get("recursive", False)),
        overwrite=bool(payload.get("overwrite", True)),
        min_confidence=float(payload.get("min_confidence", 0.35)),
        erase_mode=payload.get("erase_mode", "inpaint"),
        font_path=font_path,
        copy_images_without_text=bool(payload.get("copy_images_without_text", True)),
    )


def emit(event: dict[str, Any]) -> None:
    print(EVENT_PREFIX + json.dumps(event, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
