# utils.py
"""
通用工具模块
"""

from __future__ import annotations

import base64
import os
import time
from dataclasses import dataclass
from typing import List, Dict, Any

import requests
from requests import Response
from dotenv import load_dotenv

load_dotenv()  # 允许用 .env 文件保存 key


# --------------------------------------------------------------------------- #
# DeepSeek Client
# --------------------------------------------------------------------------- #
@dataclass
class DeepSeekClient:
    api_key: str = os.getenv("DEEPSEEK_API_KEY")
    api_url: str = "https://api.deepseek.com/chat/completions"
    default_model: str = "deepseek-chat"
    timeout: int = 30
    retries: int = 3
    cooldown: float = 1.0  # seconds

    def _post(self, payload: Dict[str, Any]) -> Response:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        last_exc = None
        for _ in range(self.retries):
            try:
                resp = requests.post(
                    self.api_url, headers=headers, json=payload, timeout=self.timeout
                )
                resp.raise_for_status()
                return resp
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                time.sleep(self.cooldown)
        raise RuntimeError(f"[DeepSeek] 请求失败: {last_exc!s}") from last_exc

    # ---- 公共调用 ---------------------------------------------------------- #
    def chat(self, messages: List[Dict[str, str]], model: str | None = None,
             temperature: float = 0.3) -> str:
        payload = {
            "model": model or self.default_model,
            "messages": messages,
            "temperature": temperature,
        }
        resp = self._post(payload).json()
        return resp["choices"][0]["message"]["content"].strip()

    # ---- 业务封装 1：金融新闻判断 ------------------------------------------ #
    def analyze_financial_news(self, news_text: str) -> Dict[str, str]:
        """返回 {'conclusion': '利好|利空|中性', 'reason': '...'}"""
        prompt = (
            "你是一个金融分析师，请根据以下新闻判断其对市场的影响，"
            "结论应为【利好】、【利空】或【中性】，并简要说明理由。"
            "\n\n新闻内容：\n"
            f"{news_text}\n\n"
            "请严格按照格式回答：\n"
            "结论：【利好/利空/中性】\n"
            "理由：XXX"
        )
        reply = self.chat([{"role": "user", "content": prompt}], model="deepseek-reasoner")
        # 简易解析
        conclusion_map = {"利好": "利好", "利空": "利空", "中性": "中性"}
        conclusion = next((c for c in conclusion_map if f"【{c}】" in reply), "未知")
        reason = reply.split("理由：")[-1].strip()
        return {"conclusion": conclusion, "reason": reason}


# --------------------------------------------------------------------------- #
# Baidu OCR Client
# --------------------------------------------------------------------------- #
@dataclass
class BaiduOCRClient:
    api_key: str = os.getenv("BAIDU_API_KEY")
    secret_key: str = os.getenv("BAIDU_SECRET_KEY")
    _token: str | None = None
    timeout: int = 30

    @property
    def token(self) -> str:
        if self._token:
            return self._token
        url = "https://aip.baidubce.com/oauth/2.0/token"
        params = {
            "grant_type": "client_credentials",
            "client_id": self.api_key,
            "client_secret": self.secret_key,
        }
        self._token = requests.post(url, params=params, timeout=self.timeout).json()[
            "access_token"
        ]
        return self._token

    @staticmethod
    def _image_to_base64(image_path: str) -> str:
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode()

    def recognize(self, image_path: str) -> List[str]:
        """返回识别到的行文本 list[str]"""
        url = (
            "https://aip.baidubce.com/rest/2.0/ocr/v1/general_basic"
            f"?access_token={self.token}"
        )
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        data = {"image": self._image_to_base64(image_path)}
        resp = requests.post(url, data=data, headers=headers, timeout=self.timeout)
        resp.raise_for_status()
        words_result = resp.json().get("words_result", [])
        return [item["words"] for item in words_result]
        
    def recognize_base64(self, image_base64: str) -> List[str]:
        """从Base64图片识别文本，返回识别到的行文本 list[str]"""
        url = (
            "https://aip.baidubce.com/rest/2.0/ocr/v1/general_basic"
            f"?access_token={self.token}"
        )
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        
        # 如果base64包含前缀(如data:image/jpeg;base64,)，需要去除
        if "," in image_base64:
            image_base64 = image_base64.split(",", 1)[1]
            
        data = {"image": image_base64}
        resp = requests.post(url, data=data, headers=headers, timeout=self.timeout)
        resp.raise_for_status()
        words_result = resp.json().get("words_result", [])
        return [item["words"] for item in words_result]


# --------------------------------------------------------------------------- #
# 公共对外函数
# --------------------------------------------------------------------------- #
# 保持单例，避免频繁刷新 Token / 建立连接
_deepseek = DeepSeekClient()
_baidu_ocr = BaiduOCRClient()


def analyze_financial_news(text: str) -> Dict[str, str]:
    """用 DeepSeek 判断新闻利好/利空/中性"""
    return _deepseek.analyze_financial_news(text)


def extract_stocks_from_image(image_path: str) -> List[str]:
    """从截图中提取 A 股"股票名称 代码"（通过文件路径，保持兼容）"""
    text_lines = _baidu_ocr.recognize(image_path)
    return _extract_stocks_from_text_lines(text_lines)


def extract_stocks_from_base64(image_base64: str) -> List[str]:
    """从Base64图片中提取A股股票（名称和代码）"""
    text_lines = _baidu_ocr.recognize_base64(image_base64)
    return _extract_stocks_from_text_lines(text_lines)


def _extract_stocks_from_text_lines(text_lines: List[str]) -> List[str]:
    """提取文本中的股票，内部辅助函数"""
    prompt = (
        "以下是股票软件截图中的所有识别行，请你提取其中所有 A 股股票信息（股票名称和6位代码）：\n"
        "- 忽略不含股票的行；\n"
        "- 忽略\"涨幅、振幅、序号、最新价\"等非股票信息；\n"
        "- 返回格式：一行一个，格式为\"股票名称 股票代码\"；\n"
        "- 如果某行含多只股票，可拆分为多行返回；\n"
        "- 不要解释说明，直接返回结果。\n"
        "【开始】\n"
        f"{chr(10).join(text_lines)}\n"
        "【结束】")

    reply = _deepseek.chat([{"role": "user", "content": prompt}], temperature=0.2)
    # 保持与 prompt 约定的 "一行一个" 输出
    return [line.strip() for line in reply.splitlines() if line.strip()]


# --------------------------------------------------------------------------- #
# CLI 便捷测试
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    import argparse
    import textwrap

    parser = argparse.ArgumentParser(
        prog="utils",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=textwrap.dedent(
            """
            Quick test for utils module.

            examples:
              python utils.py news "美联储宣布维持利率不变..."
              python utils.py ocr   path/to/screenshot.png
            """
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub_news = sub.add_parser("news")
    sub_news.add_argument("text", help="financial news text")
    sub_ocr = sub.add_parser("ocr")
    sub_ocr.add_argument("image", help="stock screenshot path")

    args = parser.parse_args()
    if args.cmd == "news":
        print(analyze_financial_news(args.text))
    else:
        print(extract_stocks_from_image(args.image))

"""
import utils

# 1. 金融新闻利好/利空判断
news = "美国劳工部最新数据显示，上月非农就业人数远低于市场预期..."
result = utils.analyze_financial_news(news)
print(result)
# ➜ {'conclusion': '利空', 'reason': '就业不及预期加剧衰退担忧...'}

# 2. 从截图提取股票
stocks = utils.extract_stocks_from_image("screenshot.png")
print(stocks)
# ➜ ['贵州茅台 600519', '宁德时代 300750', ...]
"""