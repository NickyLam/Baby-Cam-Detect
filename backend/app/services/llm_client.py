"""LLM Vision client abstraction supporting Gemini and OpenAI."""
import json
import time
import base64
import logging
from abc import ABC, abstractmethod
from typing import Optional

import google.generativeai as genai
import openai

from app.config import get_settings
from app.schemas import AnalysisResult

logger = logging.getLogger(__name__)
settings = get_settings()


class VisionClient(ABC):
    """Abstract base class for vision LLM clients."""

    @abstractmethod
    async def analyze_frame(
        self, frame_jpeg: bytes, system_prompt: str, user_prompt: str
    ) -> tuple[AnalysisResult, dict]:
        """Analyze a single frame. Returns (result, usage_metadata)."""
        pass

    @abstractmethod
    async def analyze_multi_frame(
        self, frames: list[bytes], system_prompt: str, user_prompt: str
    ) -> tuple[AnalysisResult, dict]:
        """Analyze multiple frames for confirmation. Returns (result, usage_metadata)."""
        pass


class GeminiVisionClient(VisionClient):
    """Google Gemini Flash vision client."""

    def __init__(self):
        genai.configure(api_key=settings.gemini_api_key)
        self.model = genai.GenerativeModel(settings.gemini_model)

    async def analyze_frame(
        self, frame_jpeg: bytes, system_prompt: str, user_prompt: str
    ) -> tuple[AnalysisResult, dict]:
        start_time = time.time()

        image_part = {
            "mime_type": "image/jpeg",
            "data": frame_jpeg,
        }

        response = self.model.generate_content(
            [system_prompt, image_part, user_prompt],
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.1,
            ),
        )

        latency_ms = int((time.time() - start_time) * 1000)
        result = self._parse_response(response.text)

        usage = {
            "model": settings.gemini_model,
            "input_tokens": getattr(response.usage_metadata, "prompt_token_count", 0),
            "output_tokens": getattr(response.usage_metadata, "candidates_token_count", 0),
            "latency_ms": latency_ms,
        }

        return result, usage

    async def analyze_multi_frame(
        self, frames: list[bytes], system_prompt: str, user_prompt: str
    ) -> tuple[AnalysisResult, dict]:
        start_time = time.time()

        parts = [system_prompt]
        for i, frame in enumerate(frames):
            parts.append({"mime_type": "image/jpeg", "data": frame})
            parts.append(f"Frame {i + 1} of {len(frames)}")
        parts.append(user_prompt)

        response = self.model.generate_content(
            parts,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.1,
            ),
        )

        latency_ms = int((time.time() - start_time) * 1000)
        result = self._parse_response(response.text)

        usage = {
            "model": settings.gemini_model,
            "input_tokens": getattr(response.usage_metadata, "prompt_token_count", 0),
            "output_tokens": getattr(response.usage_metadata, "candidates_token_count", 0),
            "latency_ms": latency_ms,
        }

        return result, usage

    def _parse_response(self, text: str) -> AnalysisResult:
        try:
            data = json.loads(text)
            return AnalysisResult(**data)
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Failed to parse Gemini response: {e}, raw: {text[:200]}")
            return AnalysisResult(status="unclear", reasoning="Parse error")


class OpenAIVisionClient(VisionClient):
    """OpenAI GPT-4o vision client (fallback)."""

    def __init__(self):
        self.client = openai.AsyncOpenAI(api_key=settings.openai_api_key)

    async def analyze_frame(
        self, frame_jpeg: bytes, system_prompt: str, user_prompt: str
    ) -> tuple[AnalysisResult, dict]:
        start_time = time.time()

        b64_image = base64.b64encode(frame_jpeg).decode("utf-8")

        response = await self.client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{b64_image}",
                                "detail": "low",
                            },
                        },
                    ],
                },
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=300,
        )

        latency_ms = int((time.time() - start_time) * 1000)
        result = self._parse_response(response.choices[0].message.content)

        usage = {
            "model": settings.openai_model,
            "input_tokens": response.usage.prompt_tokens,
            "output_tokens": response.usage.completion_tokens,
            "latency_ms": latency_ms,
        }

        return result, usage

    async def analyze_multi_frame(
        self, frames: list[bytes], system_prompt: str, user_prompt: str
    ) -> tuple[AnalysisResult, dict]:
        start_time = time.time()

        content = [{"type": "text", "text": user_prompt}]
        for frame in frames:
            b64_image = base64.b64encode(frame).decode("utf-8")
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{b64_image}",
                    "detail": "low",
                },
            })

        response = await self.client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
            max_tokens=300,
        )

        latency_ms = int((time.time() - start_time) * 1000)
        result = self._parse_response(response.choices[0].message.content)

        usage = {
            "model": settings.openai_model,
            "input_tokens": response.usage.prompt_tokens,
            "output_tokens": response.usage.completion_tokens,
            "latency_ms": latency_ms,
        }

        return result, usage

    def _parse_response(self, text: str) -> AnalysisResult:
        try:
            data = json.loads(text)
            return AnalysisResult(**data)
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Failed to parse OpenAI response: {e}, raw: {text[:200]}")
            return AnalysisResult(status="unclear", reasoning="Parse error")


def get_vision_client(provider: str = "gemini") -> VisionClient:
    """Factory to get the appropriate vision client."""
    if provider == "gemini":
        return GeminiVisionClient()
    elif provider == "openai":
        return OpenAIVisionClient()
    elif provider == "openai_compatible":
        return OpenAICompatibleVisionClient()
    else:
        raise ValueError(f"Unknown provider: {provider}")


class OpenAICompatibleVisionClient(VisionClient):
    """Generic OpenAI-compatible vision client.
    
    Works with any provider that implements the OpenAI chat completions API:
    - Stepfun (step-1v, step-2v)
    - Kimi / Moonshot (moonshot-v1-vision)
    - DeepSeek (deepseek-vl)
    - Yi-Vision, Qwen-VL, etc.
    """

    def __init__(self):
        self.client = openai.AsyncOpenAI(
            api_key=settings.compatible_api_key,
            base_url=settings.compatible_api_base,
        )
        self.model = settings.compatible_model

    async def analyze_frame(
        self, frame_jpeg: bytes, system_prompt: str, user_prompt: str
    ) -> tuple[AnalysisResult, dict]:
        start_time = time.time()

        b64_image = base64.b64encode(frame_jpeg).decode("utf-8")

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{b64_image}",
                            },
                        },
                    ],
                },
            ],
            temperature=0.1,
            max_tokens=300,
        )

        latency_ms = int((time.time() - start_time) * 1000)
        result = self._parse_response(response.choices[0].message.content)

        usage = {
            "model": self.model,
            "input_tokens": getattr(response.usage, "prompt_tokens", 0),
            "output_tokens": getattr(response.usage, "completion_tokens", 0),
            "latency_ms": latency_ms,
        }

        return result, usage

    async def analyze_multi_frame(
        self, frames: list[bytes], system_prompt: str, user_prompt: str
    ) -> tuple[AnalysisResult, dict]:
        start_time = time.time()

        content: list[dict] = [{"type": "text", "text": user_prompt}]
        for frame in frames:
            b64_image = base64.b64encode(frame).decode("utf-8")
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{b64_image}",
                },
            })

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content},
            ],
            temperature=0.1,
            max_tokens=300,
        )

        latency_ms = int((time.time() - start_time) * 1000)
        result = self._parse_response(response.choices[0].message.content)

        usage = {
            "model": self.model,
            "input_tokens": getattr(response.usage, "prompt_tokens", 0),
            "output_tokens": getattr(response.usage, "completion_tokens", 0),
            "latency_ms": latency_ms,
        }

        return result, usage

    def _parse_response(self, text: str) -> AnalysisResult:
        try:
            # Some models wrap JSON in markdown code blocks
            clean = text.strip()
            if clean.startswith("```"):
                clean = clean.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            data = json.loads(clean)
            return AnalysisResult(**data)
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Failed to parse compatible API response: {e}, raw: {text[:200]}")
            return AnalysisResult(status="unclear", reasoning="Parse error")
