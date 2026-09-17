"""POST /api/chat is mounted, fails cleanly without a token, and relays the model reply."""

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app import chat
from app.main import app


def test_chat_without_token_returns_503_not_404(monkeypatch):
    monkeypatch.delenv("HF_ACCESS_TOKEN", raising=False)
    chat._get_client.cache_clear()
    response = TestClient(app).post("/api/chat", json={"message": "hi"})
    assert response.status_code == 503


def test_chat_returns_the_model_reply(monkeypatch):
    sent = {}

    class FakeClient:
        def chat_completion(self, model, messages, max_tokens):
            sent["messages"] = messages
            reply = SimpleNamespace(message=SimpleNamespace(content="Plant a Water Gum."))
            return SimpleNamespace(choices=[reply])

    monkeypatch.setattr(chat, "_get_client", FakeClient)
    response = TestClient(app).post("/api/chat", json={"message": "What should I plant?"})
    assert response.status_code == 200
    assert response.json() == {"response": "Plant a Water Gum."}
    assert sent["messages"][0]["role"] == "system"
    assert sent["messages"][-1] == {"role": "user", "content": "What should I plant?"}
