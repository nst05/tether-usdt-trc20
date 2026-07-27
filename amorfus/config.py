import os


ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL_ID = os.environ.get("MODEL_ID", "claude-opus-5")
MAX_TOKENS = int(os.environ.get("MAX_TOKENS", "8192"))
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8000"))
