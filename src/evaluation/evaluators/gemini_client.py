"""
Gemini 2.5 Flash API 客户端（API易）
支持文本和多模态（图片）输入
"""

import os
import json
import base64
import time
from typing import Dict, List, Optional, Union
from pathlib import Path
import requests
from PIL import Image
import io

try:
    from json_repair import repair_json
    HAS_JSON_REPAIR = True
except ImportError:
    HAS_JSON_REPAIR = False


class GeminiClient:
    """Gemini 2.5 Flash API 客户端（通过 API易）"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "<YOUR_LLM_PROXY>/v1",
        model: str = "gemini-2.5-flash-preview-09-2025",
        max_retries: int = 3,
        timeout: int = 60
    ):
        """
        初始化 Gemini 客户端

        Args:
            api_key: API密钥（默认从环境变量 OPENAI_API_KEY 读取）
            base_url: API易的 base URL
            model: 模型名称
            max_retries: 最大重试次数
            timeout: 请求超时时间（秒）
        """
        # API易 的 API key
        self.api_key = api_key or os.getenv("OPENAI_API_KEY") or "<YOUR_API_KEY>"

        self.base_url = base_url.rstrip('/')
        self.model = model
        self.max_retries = max_retries
        self.timeout = timeout

        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        })

    def _encode_image(self, image_path: Union[str, Path]) -> str:
        """将图片编码为 base64"""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode('utf-8')

    def _build_messages(
        self,
        prompt: str,
        image_path: Optional[Union[str, Path]] = None,
        system_prompt: Optional[str] = None
    ) -> List[Dict]:
        """构建消息列表"""
        messages = []

        # 添加系统提示词
        if system_prompt:
            messages.append({
                "role": "system",
                "content": system_prompt
            })

        # 构建用户消息
        if image_path:
            # 多模态消息（图片 + 文本）
            image_b64 = self._encode_image(image_path)

            # 检测图片格式
            img_format = Path(image_path).suffix.lower()
            media_type = {
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.png': 'image/png',
                '.gif': 'image/gif',
                '.webp': 'image/webp'
            }.get(img_format, 'image/jpeg')

            messages.append({
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{media_type};base64,{image_b64}"
                        }
                    },
                    {
                        "type": "text",
                        "text": prompt
                    }
                ]
            })
        else:
            # 纯文本消息
            messages.append({
                "role": "user",
                "content": prompt
            })

        return messages

    def chat(
        self,
        prompt: str,
        image_path: Optional[Union[str, Path]] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        json_mode: bool = True
    ) -> Dict:
        """
        调用 Gemini API 进行对话

        Args:
            prompt: 用户提示词
            image_path: 可选的图片路径（多模态）
            system_prompt: 可选的系统提示词
            temperature: 温度参数（0.0 = 确定性）
            max_tokens: 最大生成 token 数
            json_mode: 是否启用 JSON 模式

        Returns:
            API 响应字典，包含 'content' 和 'usage' 字段
        """
        messages = self._build_messages(prompt, image_path, system_prompt)

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }

        # 启用 JSON 模式
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        # 重试逻辑
        for attempt in range(self.max_retries):
            try:
                response = self.session.post(
                    f"{self.base_url}/chat/completions",
                    json=payload,
                    timeout=self.timeout
                )
                response.raise_for_status()

                result = response.json()

                return {
                    "content": result["choices"][0]["message"]["content"],
                    "usage": result.get("usage", {}),
                    "model": result.get("model", self.model)
                }

            except requests.exceptions.RequestException as e:
                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt  # 指数退避
                    print(f"API 调用失败，{wait_time}秒后重试... (尝试 {attempt + 1}/{self.max_retries})")
                    time.sleep(wait_time)
                else:
                    raise RuntimeError(f"Gemini API 调用失败: {e}")

    def extract_json(self, response: Dict) -> Dict:
        """从响应中提取 JSON 数据"""
        content = response["content"]

        # 尝试提取 JSON 代码块
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            # 可能是没有标记语言的代码块
            parts = content.split("```")
            if len(parts) >= 2:
                content = parts[1].strip()

        # 首先尝试直接解析
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            # 使用 json_repair 库修复
            if HAS_JSON_REPAIR:
                try:
                    repaired = repair_json(content, return_objects=True)
                    if isinstance(repaired, dict):
                        return repaired
                    elif isinstance(repaired, list):
                        return {"data": repaired}
                    else:
                        raise ValueError(f"json_repair 返回了非预期类型: {type(repaired)}")
                except Exception as repair_error:
                    raise ValueError(f"JSON 修复失败: {repair_error}\n原始内容: {content[:500]}...")
            else:
                # 没有 json_repair 库，使用简单修复
                try:
                    return self._simple_fix_json(content)
                except:
                    raise ValueError(f"无法解析 JSON 响应: {content[:500]}...")

    def _simple_fix_json(self, content: str) -> Dict:
        """简单的 JSON 修复（当 json_repair 不可用时）"""
        content = content.strip()

        # 计算未闭合的括号
        open_braces = content.count('{') - content.count('}')
        open_brackets = content.count('[') - content.count(']')

        # 找到最后一个完整的元素
        last_comma = content.rfind(',')
        if last_comma > 0 and (open_braces > 0 or open_brackets > 0):
            content = content[:last_comma]

        # 重新计算
        open_braces = content.count('{') - content.count('}')
        open_brackets = content.count('[') - content.count(']')

        # 闭合所有未闭合的括号
        content += ']' * open_brackets + '}' * open_braces

        return json.loads(content)

    def batch_chat(
        self,
        prompts: List[str],
        image_paths: Optional[List[Union[str, Path]]] = None,
        **kwargs
    ) -> List[Dict]:
        """
        批量调用 API

        Args:
            prompts: 提示词列表
            image_paths: 可选的图片路径列表
            **kwargs: 传递给 chat() 的其他参数

        Returns:
            响应列表
        """
        if image_paths is None:
            image_paths = [None] * len(prompts)

        if len(prompts) != len(image_paths):
            raise ValueError("prompts 和 image_paths 长度必须一致")

        results = []
        for prompt, image_path in zip(prompts, image_paths):
            result = self.chat(prompt, image_path, **kwargs)
            results.append(result)
            time.sleep(0.1)  # 避免速率限制

        return results


# 全局客户端实例（单例模式）
_global_client: Optional[GeminiClient] = None


def get_gemini_client() -> GeminiClient:
    """获取全局 Gemini 客户端实例"""
    global _global_client
    if _global_client is None:
        _global_client = GeminiClient()
    return _global_client


def reset_gemini_client():
    """重置全局客户端实例（用于测试）"""
    global _global_client
    _global_client = None
