import random


MODEL_TEXTS = [
    "DeepSeek",
    "ChatGPT",
    "Claude",
    "Meta",
    "Kimi",
    "GLM",
    "MiniMax",
    "Gemini",
]


def random_model_text() -> str:
    """从预设文本中随机返回一段内容。"""
    return random.choice(MODEL_TEXTS)
