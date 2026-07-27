import uuid
from contextlib import asynccontextmanager

import anthropic
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from config import ANTHROPIC_API_KEY, HOST, MAX_TOKENS, MODEL_ID, PORT

conversations: dict[str, list[dict]] = {}

client: anthropic.AsyncAnthropic | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global client
    if not ANTHROPIC_API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. "
            "Export it as an environment variable before starting the server."
        )
    client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    yield
    await client.close()


app = FastAPI(title="Amorfus", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")


SYSTEM_PROMPT = (
    "You are Amorfus — a helpful, knowledgeable, and friendly AI assistant. "
    "Your name comes from the concept of an amorphous state: fluid, adaptable, "
    "and without rigid boundaries. Answer questions on any topic clearly and accurately. "
    "When appropriate, use examples and structured formatting. "
    "Respond in the same language as the user's message."
)


@app.get("/", response_class=HTMLResponse)
async def index():
    with open("static/index.html", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.post("/api/chat")
async def chat(request: Request):
    body = await request.json()
    message = body.get("message", "").strip()
    conversation_id = body.get("conversation_id")

    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    if conversation_id and conversation_id in conversations:
        history = conversations[conversation_id]
    else:
        conversation_id = str(uuid.uuid4())
        history = []
        conversations[conversation_id] = history

    history.append({"role": "user", "content": message})

    async def generate():
        yield f'{{"conversation_id": "{conversation_id}"}}\n'

        full_response = ""
        async with client.messages.stream(
            model=MODEL_ID,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=history,
            thinking={"type": "adaptive"},
        ) as stream:
            async for event in stream:
                if event.type == "content_block_delta":
                    if hasattr(event.delta, "text"):
                        full_response += event.delta.text
                        yield event.delta.text

        history.append({"role": "assistant", "content": full_response})

    return StreamingResponse(generate(), media_type="text/plain")


@app.post("/api/chat/sync")
async def chat_sync(request: Request):
    body = await request.json()
    message = body.get("message", "").strip()
    conversation_id = body.get("conversation_id")

    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    if conversation_id and conversation_id in conversations:
        history = conversations[conversation_id]
    else:
        conversation_id = str(uuid.uuid4())
        history = []
        conversations[conversation_id] = history

    history.append({"role": "user", "content": message})

    response = await client.messages.create(
        model=MODEL_ID,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=history,
        thinking={"type": "adaptive"},
    )

    assistant_text = ""
    for block in response.content:
        if block.type == "text":
            assistant_text += block.text

    history.append({"role": "assistant", "content": assistant_text})

    return {
        "conversation_id": conversation_id,
        "response": assistant_text,
        "model": response.model,
        "usage": {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        },
    }


@app.post("/api/conversations/new")
async def new_conversation():
    conversation_id = str(uuid.uuid4())
    conversations[conversation_id] = []
    return {"conversation_id": conversation_id}


@app.delete("/api/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    conversations.pop(conversation_id, None)
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host=HOST, port=PORT, reload=True)
