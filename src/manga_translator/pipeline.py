from __future__ import annotations

import csv
import traceback
from pathlib import Path
from threading import Event
from time import perf_counter
from typing import Callable, Any

from .image_io import list_images, output_path_for
from .models import BatchOptions, BatchStats, RenderOptions, TextBlock
from .ocr import PaddleOcrEngine
from .rendering import render_translated_image
from .translators import create_translator


ProgressCallback = Callable[[dict[str, Any]], None]


def translate_directory(
    options: BatchOptions,
    progress: ProgressCallback | None = None,
    stop_event: Event | None = None,
) -> BatchStats:
    input_dir = options.input_dir
    output_dir = options.output_dir
    if not input_dir.exists() or not input_dir.is_dir():
        raise ValueError(f"输入目录不存在：{input_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)
    images = exclude_output_dir(
        list_images(input_dir, recursive=options.recursive),
        output_dir,
    )
    stats = BatchStats(total=len(images))
    report_rows: list[dict[str, str]] = []
    failures: list[str] = []

    emit(progress, type="scan", total=len(images), message=f"发现 {len(images)} 张图片。")
    if not images:
        write_reports(output_dir, report_rows, failures)
        return stats

    emit(progress, type="message", message="正在初始化 OCR 和翻译引擎，首次运行可能需要下载模型。")
    ocr_engine = PaddleOcrEngine(lang=options.ocr_lang, min_confidence=options.min_confidence)
    translator = create_translator(
        options.translator,
        source_lang=options.source_lang,
        target_lang=options.target_lang,
    )
    emit(progress, type="message", message=f"OCR：{ocr_engine.name}，翻译：{translator.name}。")

    for index, image_path in enumerate(images, start=1):
        if stop_event is not None and stop_event.is_set():
            stats.cancelled = True
            emit(progress, type="cancelled", index=index - 1, total=len(images), message="已停止。")
            break

        output_path = output_path_for(input_dir, output_dir, image_path)
        emit(
            progress,
            type="file_start",
            index=index,
            total=len(images),
            file=str(image_path),
            message=f"[{index}/{len(images)}] {image_path.name}",
        )

        if output_path.exists() and not options.overwrite:
            stats.skipped += 1
            emit(progress, type="file_skip", index=index, total=len(images), file=str(image_path))
            continue

        started = perf_counter()
        try:
            blocks = ocr_engine.recognize(image_path)
            translate_blocks(blocks, translator)

            if blocks or options.copy_images_without_text:
                render_options = RenderOptions(
                    erase_mode=options.erase_mode,
                    font_path=options.font_path,
                )
                render_translated_image(image_path, output_path, blocks, render_options)

            rows = rows_for_image(input_dir, image_path, output_path, blocks)
            report_rows.extend(rows)
            stats.completed += 1
            stats.text_blocks += len(blocks)
            elapsed = perf_counter() - started
            emit(
                progress,
                type="file_done",
                index=index,
                total=len(images),
                file=str(image_path),
                output=str(output_path),
                blocks=len(blocks),
                elapsed=elapsed,
                message=f"完成：{image_path.name}，文字框 {len(blocks)} 个，用时 {elapsed:.1f}s。",
            )
        except Exception as exc:
            stats.failed += 1
            detail = f"{image_path}: {exc}"
            failures.append(detail)
            emit(
                progress,
                type="file_error",
                index=index,
                total=len(images),
                file=str(image_path),
                error=str(exc),
                traceback=traceback.format_exc(),
                message=f"失败：{image_path.name}，{exc}",
            )

    write_reports(output_dir, report_rows, failures)
    emit(progress, type="done", stats=stats.as_dict(), message="批处理结束。")
    return stats


def translate_blocks(blocks: list[TextBlock], translator: Any) -> None:
    texts = [block.text for block in blocks]
    if not texts:
        return
    try:
        translations = translator.translate_many(texts)
    except Exception as exc:
        raise RuntimeError(f"翻译失败：{exc}") from exc
    for block, translated in zip(blocks, translations, strict=False):
        block.translation = translated


def rows_for_image(
    input_dir: Path,
    image_path: Path,
    output_path: Path,
    blocks: list[TextBlock],
) -> list[dict[str, str]]:
    relative = str(image_path.relative_to(input_dir))
    rows: list[dict[str, str]] = []
    for block in blocks:
        rows.append(
            {
                "image": relative,
                "output": str(output_path),
                "source_text": block.text,
                "translated_text": block.translation,
                "score": f"{block.score:.4f}",
                "bbox": ",".join(str(value) for value in block.bbox),
            }
        )
    return rows


def write_reports(output_dir: Path, rows: list[dict[str, str]], failures: list[str]) -> None:
    report_path = output_dir / "translations.csv"
    with report_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["image", "output", "source_text", "translated_text", "score", "bbox"],
        )
        writer.writeheader()
        writer.writerows(rows)

    failed_path = output_dir / "failed.txt"
    if failures:
        failed_path.write_text("\n".join(failures), encoding="utf-8")
    elif failed_path.exists():
        failed_path.unlink()


def exclude_output_dir(images: list[Path], output_dir: Path) -> list[Path]:
    output_root = output_dir.resolve()
    kept: list[Path] = []
    for image in images:
        try:
            if image.resolve().is_relative_to(output_root):
                continue
        except OSError:
            pass
        kept.append(image)
    return kept


def emit(progress: ProgressCallback | None, **event: Any) -> None:
    if progress is not None:
        progress(event)
