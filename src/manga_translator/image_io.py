from __future__ import annotations

from pathlib import Path


SUPPORTED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
}


def is_image_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS


def list_images(root: Path, recursive: bool = False) -> list[Path]:
    pattern = "**/*" if recursive else "*"
    return sorted(
        [path for path in root.glob(pattern) if is_image_file(path)],
        key=lambda item: str(item).lower(),
    )


def output_path_for(input_root: Path, output_root: Path, image_path: Path) -> Path:
    relative = image_path.relative_to(input_root)
    return output_root / relative
