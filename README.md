# 漫画图片批量翻译工具

这是一个本地桌面 GUI 工具，用于选择一个全是图片的目录，批量识别图片文字、翻译文字，并把译文回填到图片上。项目默认面向漫画图片，使用 PaddleOCR 做 OCR，支持把输出保存到单独目录。

## 快速启动

```powershell
Set-Location D:\project\translate_picture
python -m pip install -r requirements.txt
python run_app.py
```

也可以双击 `start_gui.bat` 启动。

第一次运行 PaddleOCR 可能会下载模型，耗时会比较久。程序会默认关闭 PaddleOCR 的 MKLDNN 加速，以规避部分 Windows CPU 环境下的 oneDNN 兼容问题。

批量翻译任务会在独立子进程中运行，GUI 主窗口只接收进度消息；即使 OCR 或翻译比较耗时，窗口也应保持可拖动、可停止。

## 使用方式

1. 点击“选择”选择图片目录。
2. 选择 OCR 语言。日漫建议选“日文漫画”，中文/英文图片选“中文/英文”。
3. 选择翻译方式和目标语言。
4. 点击“开始翻译”。
5. 输出图片会保存到输出目录，默认是输入目录下的 `translated` 文件夹。

## 翻译方式

- 自动选择：优先使用百度翻译环境变量，其次 deep-translator，最后 Google 免费接口。
- 百度翻译：需要配置环境变量 `BAIDU_TRANSLATE_APP_ID` 和 `BAIDU_TRANSLATE_SECRET`。
- Google 免费接口：不需要密钥，但网络环境可能影响可用性。
- Deep Translator：需要安装 `deep-translator`，由 `requirements.txt` 提供。
- 不翻译：仅把识别到的原文重新绘制，方便检查 OCR 和回填效果。

## 输出内容

输出目录中会包含：

- 翻译后的图片。
- `translations.csv`：每个文字框的原文、译文、置信度和坐标。
- `failed.txt`：处理失败的图片和错误原因。

## 适配说明

当前版本是可运行 MVP，漫画翻译质量主要受三点影响：OCR 语言选择、翻译接口可用性、原图气泡/文字背景复杂度。如果后续要接入更强的模型，可以只替换 `src/manga_translator/ocr.py` 或 `src/manga_translator/translators.py`，GUI 和批处理流程不用重写。
