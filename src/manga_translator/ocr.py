from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .models import TextBlock


class OcrUnavailableError(RuntimeError):
    pass


class PaddleOcrEngine:
    name = "PaddleOCR"

    def __init__(self, lang: str = "ch", min_confidence: float = 0.35) -> None:
        self.lang = lang
        self.min_confidence = min_confidence
        self._ocr = None

    def _load(self) -> None:
        if self._ocr is not None:
            return

        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

        try:
            from paddleocr import PaddleOCR
        except Exception as exc:  # pragma: no cover - depends on optional package
            raise OcrUnavailableError(
                "未安装 PaddleOCR，请运行：python -m pip install -r requirements.txt"
            ) from exc

        self._ocr = PaddleOCR(
            lang=self.lang,
            enable_mkldnn=False,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            text_rec_score_thresh=0.0,
        )

    def recognize(self, image_path: Path) -> list[TextBlock]:
        self._load()
        assert self._ocr is not None

        try:
            result = self._ocr.predict(str(image_path))
        except Exception as exc:
            message = str(exc)
            if "ConvertPirAttribute2RuntimeAttribute" in message or "onednn" in message.lower():
                message += "。当前程序已关闭 enable_mkldnn，如果仍报错，请尝试更新 paddlepaddle。"
            raise RuntimeError(f"OCR 识别失败：{message}") from exc

        return self._parse_result(result)

    def _parse_result(self, result: Any) -> list[TextBlock]:
        blocks: list[TextBlock] = []
        if not result:
            return blocks

        for page in result:
            if isinstance(page, dict):
                blocks.extend(self._parse_predict_page(page))
            elif isinstance(page, list):
                blocks.extend(self._parse_legacy_page(page))

        return [block for block in blocks if block.text.strip() and block.score >= self.min_confidence]

    def _parse_predict_page(self, page: dict[str, Any]) -> list[TextBlock]:
        texts = page.get("rec_texts") or []
        scores = page.get("rec_scores") or []
        polys = page.get("rec_polys")
        if polys is None or len(polys) == 0:
            polys = page.get("dt_polys") or []

        blocks: list[TextBlock] = []
        for index, text in enumerate(texts):
            if index >= len(polys):
                continue
            score = float(scores[index]) if index < len(scores) else 1.0
            polygon = _polygon_from_any(polys[index])
            if len(polygon) >= 3:
                blocks.append(TextBlock(polygon=polygon, text=str(text), score=score))
        return blocks

    def _parse_legacy_page(self, page: list[Any]) -> list[TextBlock]:
        blocks: list[TextBlock] = []
        for item in page:
            if not item or len(item) < 2:
                continue
            polygon = _polygon_from_any(item[0])
            rec = item[1]
            if isinstance(rec, (list, tuple)) and len(rec) >= 2:
                text = str(rec[0])
                score = float(rec[1])
            else:
                text = str(rec)
                score = 1.0
            if len(polygon) >= 3:
                blocks.append(TextBlock(polygon=polygon, text=text, score=score))
        return blocks


def _polygon_from_any(poly: Any) -> list[tuple[int, int]]:
    if hasattr(poly, "tolist"):
        poly = poly.tolist()
    points: list[tuple[int, int]] = []
    for point in poly:
        if hasattr(point, "tolist"):
            point = point.tolist()
        if len(point) < 2:
            continue
        points.append((int(round(float(point[0]))), int(round(float(point[1])))))
    return points
