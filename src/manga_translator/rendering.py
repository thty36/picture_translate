from __future__ import annotations

import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .models import RenderOptions, TextBlock


def render_translated_image(
    input_path: Path,
    output_path: Path,
    blocks: list[TextBlock],
    options: RenderOptions,
) -> None:
    image = Image.open(input_path).convert("RGB")
    rendered = erase_regions(image, blocks, options)
    draw = ImageDraw.Draw(rendered)
    font_path = options.font_path or find_default_font()

    for block in blocks:
        text = block.translation.strip()
        if not text:
            continue
        box = padded_bbox(block.bbox, options.padding, rendered.size)
        draw_fit_text(draw, text, box, font_path, options)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.suffix.lower() in {".jpg", ".jpeg"}:
        rendered.save(output_path, quality=95, subsampling=0)
    else:
        rendered.save(output_path)


def erase_regions(image: Image.Image, blocks: list[TextBlock], options: RenderOptions) -> Image.Image:
    if not blocks:
        return image.copy()

    if options.erase_mode == "inpaint":
        inpainted = try_inpaint(image, blocks, options)
        if inpainted is not None:
            return inpainted

    result = image.copy()
    draw = ImageDraw.Draw(result)
    for block in blocks:
        box = padded_bbox(block.bbox, options.padding, result.size)
        if options.erase_mode == "sample":
            fill = sample_border_color(image, box)
        else:
            fill = (255, 255, 255)
        draw.rectangle(box, fill=fill)
    return result


def try_inpaint(image: Image.Image, blocks: list[TextBlock], options: RenderOptions) -> Image.Image | None:
    try:
        import cv2
        import numpy as np
    except Exception:
        return None

    width, height = image.size
    mask = np.zeros((height, width), dtype=np.uint8)
    for block in blocks:
        x1, y1, x2, y2 = padded_bbox(block.bbox, options.padding, image.size)
        cv2.rectangle(mask, (x1, y1), (x2, y2), 255, thickness=-1)

    source = np.array(image)
    restored = cv2.inpaint(source, mask, 3, cv2.INPAINT_TELEA)
    return Image.fromarray(restored)


def draw_fit_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    box: tuple[int, int, int, int],
    font_path: Path,
    options: RenderOptions,
) -> None:
    x1, y1, x2, y2 = box
    max_width = max(1, x2 - x1)
    max_height = max(1, y2 - y1)
    font, lines, line_height = fit_font(draw, text, max_width, max_height, font_path, options)
    total_height = line_height * len(lines)
    y = y1 + max(0, (max_height - total_height) // 2)

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_width = bbox[2] - bbox[0]
        x = x1 + max(0, (max_width - line_width) // 2)
        draw.text((x, y), line, font=font, fill=options.text_color)
        y += line_height


def fit_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_width: int,
    max_height: int,
    font_path: Path,
    options: RenderOptions,
) -> tuple[ImageFont.FreeTypeFont, list[str], int]:
    upper = min(options.max_font_size, max(options.min_font_size, int(max_height * 0.8)))
    for size in range(upper, options.min_font_size - 1, -1):
        font = ImageFont.truetype(str(font_path), size)
        lines = wrap_text(draw, text, font, max_width)
        line_height = max(1, int((font.getbbox("国")[3] - font.getbbox("国")[1]) * 1.18))
        total_height = line_height * len(lines)
        widest = max((text_width(draw, line, font) for line in lines), default=0)
        if total_height <= max_height and widest <= max_width:
            return font, lines, line_height

    font = ImageFont.truetype(str(font_path), options.min_font_size)
    lines = wrap_text(draw, text, font, max_width)
    line_height = max(1, int((font.getbbox("国")[3] - font.getbbox("国")[1]) * 1.18))
    return font, lines, line_height


def wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
) -> list[str]:
    clean = re.sub(r"\s+", " ", text.strip())
    if not clean:
        return [""]

    tokens = tokenize(clean)
    lines: list[str] = []
    current = ""
    for token in tokens:
        candidate = join_token(current, token)
        if current and text_width(draw, candidate, font) > max_width:
            lines.append(current)
            current = token.strip()
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [clean]


def tokenize(text: str) -> list[str]:
    if _contains_cjk(text):
        return [char for char in text if char.strip()]
    return re.findall(r"[A-Za-z0-9]+(?:[.'_-][A-Za-z0-9]+)*|[^\s]", text)


def join_token(current: str, token: str) -> str:
    if not current:
        return token.strip()
    if _contains_cjk(current[-1]) or _contains_cjk(token):
        return current + token.strip()
    if re.match(r"^[,.;:!?)]$", token):
        return current + token
    return current + " " + token


def text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def padded_bbox(
    bbox: tuple[int, int, int, int],
    padding: int,
    image_size: tuple[int, int],
) -> tuple[int, int, int, int]:
    width, height = image_size
    x1, y1, x2, y2 = bbox
    return (
        max(0, x1 - padding),
        max(0, y1 - padding),
        min(width - 1, x2 + padding),
        min(height - 1, y2 + padding),
    )


def sample_border_color(image: Image.Image, box: tuple[int, int, int, int]) -> tuple[int, int, int]:
    try:
        import numpy as np
    except Exception:
        return (255, 255, 255)

    x1, y1, x2, y2 = box
    width, height = image.size
    outer = (
        max(0, x1 - 6),
        max(0, y1 - 6),
        min(width - 1, x2 + 6),
        min(height - 1, y2 + 6),
    )
    arr = np.array(image)
    ox1, oy1, ox2, oy2 = outer
    samples = []
    samples.append(arr[oy1:y1, ox1:ox2])
    samples.append(arr[y2:oy2, ox1:ox2])
    samples.append(arr[oy1:oy2, ox1:x1])
    samples.append(arr[oy1:oy2, x2:ox2])
    pixels = [sample.reshape(-1, 3) for sample in samples if sample.size]
    if not pixels:
        return (255, 255, 255)
    merged = np.concatenate(pixels, axis=0)
    color = np.median(merged, axis=0).astype(int).tolist()
    return int(color[0]), int(color[1]), int(color[2])


def find_default_font() -> Path:
    candidates = [
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
        Path(r"C:\Windows\Fonts\Deng.ttf"),
        Path(r"C:\Windows\Fonts\simsun.ttc"),
        Path(r"C:\Windows\Fonts\arial.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError("找不到可用字体，请在界面中选择字体文件。")


def _contains_cjk(text: str) -> bool:
    return any(
        "\u3400" <= char <= "\u9fff"
        or "\u3040" <= char <= "\u30ff"
        or "\uac00" <= char <= "\ud7af"
        for char in text
    )
