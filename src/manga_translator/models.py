from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


Point = tuple[int, int]


@dataclass(slots=True)
class TextBlock:
    polygon: list[Point]
    text: str
    score: float
    translation: str = ""

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        xs = [point[0] for point in self.polygon]
        ys = [point[1] for point in self.polygon]
        return min(xs), min(ys), max(xs), max(ys)


@dataclass(frozen=True, slots=True)
class BatchOptions:
    input_dir: Path
    output_dir: Path
    ocr_lang: str = "ch"
    source_lang: str = "auto"
    target_lang: str = "zh-CN"
    translator: str = "auto"
    recursive: bool = False
    overwrite: bool = True
    min_confidence: float = 0.35
    erase_mode: str = "inpaint"
    font_path: Path | None = None
    copy_images_without_text: bool = True


@dataclass(frozen=True, slots=True)
class RenderOptions:
    erase_mode: str = "inpaint"
    font_path: Path | None = None
    text_color: tuple[int, int, int] = (18, 18, 18)
    min_font_size: int = 10
    max_font_size: int = 42
    padding: int = 4


@dataclass(slots=True)
class BatchStats:
    total: int = 0
    completed: int = 0
    skipped: int = 0
    failed: int = 0
    text_blocks: int = 0
    cancelled: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "completed": self.completed,
            "skipped": self.skipped,
            "failed": self.failed,
            "text_blocks": self.text_blocks,
            "cancelled": self.cancelled,
        }
