"""Apple Vision OCR 后端。所有调用在本机系统框架内完成，不上传文件。"""

from __future__ import annotations

import platform

from .base import TextBlock


class AppleVisionBackend:
    def __init__(self) -> None:
        import Vision

        self._vision = Vision
        release = platform.mac_ver()[0] or "unknown"
        self.name = f"apple-vision@{release}"

    def recognize(self, image_bytes: bytes) -> list[TextBlock]:
        import Vision
        from Foundation import NSData

        data = NSData.dataWithBytes_length_(image_bytes, len(image_bytes))
        request = Vision.VNRecognizeTextRequest.alloc().init()
        request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
        request.setUsesLanguageCorrection_(True)
        # Vision 会自动在候选语言间选择；显式排序让中英夹杂时中文不退到 fast 模式。
        request.setRecognitionLanguages_(["zh-Hans", "zh-Hant", "en-US"])

        handler = Vision.VNImageRequestHandler.alloc().initWithData_options_(data, {})
        success, error = handler.performRequests_error_([request], None)
        if not success:
            raise RuntimeError(str(error) if error is not None else "Vision request failed")

        blocks: list[TextBlock] = []
        for observation in request.results() or []:
            candidates = observation.topCandidates_(1)
            if not candidates:
                continue
            candidate = candidates[0]
            text = str(candidate.string()).strip()
            if not text:
                continue
            box = observation.boundingBox()
            # Vision 原点在左下；管道统一用左上原点。
            y0 = 1.0 - float(box.origin.y + box.size.height)
            y1 = 1.0 - float(box.origin.y)
            blocks.append(
                TextBlock(
                    text=text,
                    confidence=float(candidate.confidence()),
                    y0=max(0.0, min(1.0, y0)),
                    y1=max(0.0, min(1.0, y1)),
                )
            )
        blocks.sort(key=lambda block: (block.y0 if block.y0 is not None else 1.0))
        return blocks

