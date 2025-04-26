# import os
# from openai import OpenAI
# import requests
# import time
# import json
# import time
#
# API_SECRET_KEY = "sk-zk2f8f0da24f104fb3b001f8c3785a46fac6720619532d2b"
# BASE_URL = "https://api.zhizengzeng.com/v1/"
#
#
# # chat with other model
# def chat_completions4(query):
#     client = OpenAI(api_key=API_SECRET_KEY, base_url=BASE_URL)
#     resp = client.chat.completions.create(
#         model="SparkDesk",
#         messages=[
#             {"role": "system", "content": "You are a helpful assistant."},
#             {"role": "user", "content": query}
#         ]
#     )
#     print(resp)
#     print(resp.choices[0].message.content)
#
#
# if __name__ == '__main__':
#     chat_completions4("你是哪个公司开发的什么模型？")

# import os
# from openai import OpenAI
# import requests
# import time
# import json
# import time
#
# API_SECRET_KEY = "sk-zk2f8f0da24f104fb3b001f8c3785a46fac6720619532d2b"
# BASE_URL = "https://api.zhizengzeng.com/v1/"
#
# # chat with other model，deepseek-chat
# def chat_completions4(query):
#     client = OpenAI(api_key=API_SECRET_KEY, base_url=BASE_URL)
#     resp = client.chat.completions.create(
#         model="deepseek-chat",
#         messages=[
#             {"role": "system", "content": "You are a helpful assistant."},
#             {"role": "user", "content": query}
#         ]
#     )
#     print(resp)
#     print(resp.choices[0].message.content)
#
#
# if __name__ == '__main__':
#     chat_completions4("你是哪个公司开发的什么模型？")

import requests
import json
import time

# 配置你的 DeepSeek API
API_URL = "https://api.deepseek.com/chat/completions"  # 改成你自己的 DeepSeek API 地址
API_KEY = "sk-282d8db1655742a7900fb9ce997fc098"

# 读取金融新闻（你可以改成从txt读取）
financial_news = [
    # "美联储宣布维持利率不变，市场普遍预期未来将降息。",
    # "苹果公司发布财报，营收与利润均高于预期。",
    # "受中东局势影响，国际油价大幅上涨。",
    "美国劳工部最新数据显示，上月非农就业人数远低于市场预期，失业率显著攀升，经济衰退风险加剧，市场情绪受挫。",
]


# 定义发送到 DeepSeek 的函数
def analyze_news(news_text):
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    prompt = f"""你是一个金融分析师，请根据以下新闻判断其对市场的影响，结论应为【利好】、【利空】或【中性】，并简要说明理由。

新闻内容：
{news_text}

请严格按照格式回答：
结论：【利好/利空/中性】
理由：XXX
"""

    data = {
        "model": "deepseek-reasoner",  
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3  # 控制回答稳定性，低温度更稳定
    }

    try:
        response = requests.post(API_URL, headers=headers, data=json.dumps(data))
        response.raise_for_status()
        result = response.json()
        reply = result['choices'][0]['message']['content']
        return reply
    except Exception as e:
        print(f"请求出错: {e}")
        return None


# 主流程
if __name__ == "__main__":
    for idx, news in enumerate(financial_news, 1):
        print(f"\n正在分析第{idx}条新闻...")
        analysis = analyze_news(news)
        if analysis:
            print(f"新闻内容：{news}")
            print(f"分析结果：\n{analysis}")
        else:
            print("分析失败。")

        time.sleep(1)  # 避免API调用太快（根据你的DeepSeek速率限制，可以适当调整）