from __future__ import annotations

import hashlib
import os
import random
import time
from typing import Protocol

import requests


class Translator(Protocol):
    name: str

    def translate_many(self, texts: list[str]) -> list[str]:
        ...


class BaseTranslator:
    name = "Base"

    def __init__(self, source_lang: str = "auto", target_lang: str = "zh-CN") -> None:
        self.source_lang = source_lang
        self.target_lang = target_lang
        self._cache: dict[str, str] = {}

    def translate_many(self, texts: list[str]) -> list[str]:
        translated: list[str] = []
        for text in texts:
            key = text.strip()
            if not key:
                translated.append("")
                continue
            if key not in self._cache:
                self._cache[key] = self.translate_text(key)
            translated.append(self._cache[key])
        return translated

    def translate_text(self, text: str) -> str:
        raise NotImplementedError


class NoopTranslator(BaseTranslator):
    name = "不翻译"

    def translate_text(self, text: str) -> str:
        return text


class GoogleWebTranslator(BaseTranslator):
    name = "Google 免费接口"

    def __init__(self, source_lang: str = "auto", target_lang: str = "zh-CN") -> None:
        super().__init__(source_lang=source_lang, target_lang=target_lang)
        self._session = requests.Session()

    def translate_text(self, text: str) -> str:
        params = {
            "client": "gtx",
            "sl": _google_lang(self.source_lang),
            "tl": _google_lang(self.target_lang),
            "dt": "t",
            "q": text,
        }
        response = self._session.get(
            "https://translate.googleapis.com/translate_a/single",
            params=params,
            timeout=25,
        )
        response.raise_for_status()
        data = response.json()
        translated = "".join(part[0] for part in data[0] if part and part[0])
        return translated or text


class BaiduTranslator(BaseTranslator):
    name = "百度翻译"

    def __init__(self, source_lang: str = "auto", target_lang: str = "zh-CN") -> None:
        super().__init__(source_lang=source_lang, target_lang=target_lang)
        self.app_id = os.getenv("BAIDU_TRANSLATE_APP_ID", "").strip()
        self.secret = os.getenv("BAIDU_TRANSLATE_SECRET", "").strip()
        if not self.app_id or not self.secret:
            raise RuntimeError(
                "百度翻译需要环境变量 BAIDU_TRANSLATE_APP_ID 和 BAIDU_TRANSLATE_SECRET。"
            )
        self._session = requests.Session()

    def translate_text(self, text: str) -> str:
        salt = str(random.randint(100000, 999999))
        sign_raw = f"{self.app_id}{text}{salt}{self.secret}".encode("utf-8")
        params = {
            "q": text,
            "from": _baidu_lang(self.source_lang),
            "to": _baidu_lang(self.target_lang),
            "appid": self.app_id,
            "salt": salt,
            "sign": hashlib.md5(sign_raw).hexdigest(),
        }
        response = self._session.get(
            "https://fanyi-api.baidu.com/api/trans/vip/translate",
            params=params,
            timeout=25,
        )
        response.raise_for_status()
        payload = response.json()
        if "error_code" in payload:
            raise RuntimeError(f"百度翻译错误 {payload.get('error_code')}: {payload.get('error_msg')}")
        result = payload.get("trans_result") or []
        return "\n".join(item.get("dst", "") for item in result).strip() or text


class DeepTranslatorGoogle(BaseTranslator):
    name = "Deep Translator"

    def __init__(self, source_lang: str = "auto", target_lang: str = "zh-CN") -> None:
        super().__init__(source_lang=source_lang, target_lang=target_lang)
        try:
            from deep_translator import GoogleTranslator
        except Exception as exc:  # pragma: no cover - depends on optional package
            raise RuntimeError(
                "未安装 deep-translator，请运行：python -m pip install deep-translator"
            ) from exc
        self._translator = GoogleTranslator(
            source=_deep_source_lang(source_lang),
            target=_deep_target_lang(target_lang),
        )

    def translate_text(self, text: str) -> str:
        time.sleep(0.05)
        return self._translator.translate(text) or text


def create_translator(provider: str, source_lang: str = "auto", target_lang: str = "zh-CN") -> Translator:
    provider = provider.lower().strip()
    if provider == "none":
        return NoopTranslator(source_lang=source_lang, target_lang=target_lang)
    if provider == "baidu":
        return BaiduTranslator(source_lang=source_lang, target_lang=target_lang)
    if provider == "google_web":
        return GoogleWebTranslator(source_lang=source_lang, target_lang=target_lang)
    if provider == "deep_translator":
        return DeepTranslatorGoogle(source_lang=source_lang, target_lang=target_lang)
    if provider == "auto":
        if os.getenv("BAIDU_TRANSLATE_APP_ID") and os.getenv("BAIDU_TRANSLATE_SECRET"):
            return BaiduTranslator(source_lang=source_lang, target_lang=target_lang)
        try:
            return DeepTranslatorGoogle(source_lang=source_lang, target_lang=target_lang)
        except Exception:
            return GoogleWebTranslator(source_lang=source_lang, target_lang=target_lang)
    raise ValueError(f"未知翻译方式：{provider}")


def _google_lang(lang: str) -> str:
    mapping = {
        "zh": "zh-CN",
        "zh-CN": "zh-CN",
        "cn": "zh-CN",
        "jp": "ja",
        "japan": "ja",
        "kor": "ko",
        "korean": "ko",
    }
    return mapping.get(lang, lang)


def _baidu_lang(lang: str) -> str:
    mapping = {
        "auto": "auto",
        "zh": "zh",
        "zh-CN": "zh",
        "cn": "zh",
        "en": "en",
        "ja": "jp",
        "jp": "jp",
        "japan": "jp",
        "ko": "kor",
        "kor": "kor",
        "korean": "kor",
    }
    return mapping.get(lang, lang)


def _deep_source_lang(lang: str) -> str:
    if lang == "auto":
        return "auto"
    return _deep_target_lang(lang)


def _deep_target_lang(lang: str) -> str:
    mapping = {
        "zh": "chinese (simplified)",
        "zh-CN": "chinese (simplified)",
        "cn": "chinese (simplified)",
        "ja": "japanese",
        "jp": "japanese",
        "japan": "japanese",
        "ko": "korean",
        "kor": "korean",
        "korean": "korean",
        "en": "english",
    }
    return mapping.get(lang, lang)
