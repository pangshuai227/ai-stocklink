
# === 你的 API 凭证 ===
BAIDU_API_KEY = 'Bj58ogvT0wPI5OSsooBoD4PM'
BAIDU_SECRET_KEY = 'g48iyDmjWhAR8rUXpSas1nTMzBfU0hUV'
DEEPSEEK_API_KEY = 'sk-00ea6ddccdcd4d42beaaf5cd93e138e0'  # 必须替换为你自己的

import requests
import base64
import os


# 获取百度OCR访问令牌
def get_baidu_token(api_key, secret_key):
    url = 'https://aip.baidubce.com/oauth/2.0/token'
    params = {'grant_type': 'client_credentials', 'client_id': api_key, 'client_secret': secret_key}
    return requests.post(url, params=params).json()['access_token']

# 图像转Base64
def image_to_base64(image_path):
    with open(image_path, 'rb') as f:
        return base64.b64encode(f.read()).decode()

# 使用百度OCR识别图像
def baidu_ocr(image_path, access_token):
    url = f'https://aip.baidubce.com/rest/2.0/ocr/v1/general_basic?access_token={access_token}'
    headers = {'Content-Type': 'application/x-www-form-urlencoded'}
    img_b64 = image_to_base64(image_path)
    data = {'image': img_b64}
    res = requests.post(url, data=data, headers=headers)
    return [item['words'] for item in res.json().get('words_result', [])]

# 调用 DeepSeek 提取所有股票信息
def ask_deepseek_batch(text_lines):
    joined_text = "\n".join(text_lines)
    prompt = f"""
以下是股票软件截图中的所有识别行，请你提取其中所有 A 股股票信息（股票名称和6位代码）：
- 忽略不含股票的行；
- 忽略“涨幅、振幅、序号、最新价”等非股票信息；
- 返回格式：一行一个，格式为“股票名称 股票代码”；
- 如果某行含多只股票，可拆分为多行返回；
- 不要解释说明，直接返回结果。
【开始】
{joined_text}
【结束】
"""

    url = "https://api.deepseek.com/chat/completions"
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2
    }

    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()['choices'][0]['message']['content'].strip().splitlines()
    except Exception as e:
        print(f"[DeepSeek 错误] {e}")
        return []

# 主程序
def main():
    image_path = input("📁 请输入股票截图图片路径（支持拖入）：").strip('"')

    if not os.path.exists(image_path):
        print("❌ 图片路径无效")
        return

    print("🔍 正在识别图片文本...")
    baidu_token = get_baidu_token(BAIDU_API_KEY, BAIDU_SECRET_KEY)
    text_lines = baidu_ocr(image_path, baidu_token)

    print("\n📄 OCR识别文本：")
    for line in text_lines:
        print(line)

    print("\n🧠 使用 DeepSeek 识别全部股票信息中...")
    extracted = ask_deepseek_batch(text_lines)

    if not extracted:
        print("❌ 没有识别到股票信息。")
    else:
        print("\n📈 提取到的股票：")
        for item in extracted:
            print(f"✔ {item}")

        # 可选保存
        with open("stocks_extracted.txt", "w", encoding="utf-8") as f:
            for item in extracted:
                f.write(item + "\n")
        print("✅ 已保存到 stocks_extracted.txt")

if __name__ == '__main__':
    main()
