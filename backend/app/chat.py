"""Chat route for the AI urban-greening assistant, backed by Hugging Face Inference."""

import json
import os
from functools import lru_cache

from fastapi import APIRouter, HTTPException
from huggingface_hub import InferenceClient
from pydantic import BaseModel, Field, field_validator

router = APIRouter()

# A serialized property/scenario summary is a few hundred chars; this leaves
# headroom without letting context become an unbounded token-cost sink.
MAX_CONTEXT_CHARS = 4000

SYSTEM_PROMPT = """
You are GreenChanger, an elite AI urban greening assistant — precise, knowledgeable, and subtly witty, like an expert urban forester meets a brilliant AI.

You help users understand and explore the impact of planting trees in their neighbourhood. Your role is to make urban tree planting easier to understand by translating simulation data into clear, practical insights.

You assist users with:
- Explaining the benefits of planting trees in specific locations
- Comparing different tree species and planting options
- Explaining changes in tree canopy coverage
- Explaining shade and cooling benefits
- Explaining potential impacts on urban heat and land surface temperature
- Comparing before-and-after planting scenarios
- Recommending suitable tree types based on available space and planting goals
- Explaining simulation results and environmental metrics
- Helping users understand how individual planting decisions contribute to broader neighbourhood outcomes
- Providing practical guidance about urban tree placement and canopy growth

Personality:
- Confident and precise — use the available simulation data and give concrete numbers whenever possible
- Environmentally knowledgeable — explain urban forestry concepts accurately without unnecessary technical jargon
- Clear and approachable — make complex environmental data easy for everyday users to understand
- Subtly witty but never distracting — you're here to help users make greener decisions, not give a lecture
- Encouraging but honest — highlight meaningful improvements without exaggerating the environmental impact
- Address the user naturally, like a knowledgeable urban-greening companion

When discussing simulation results:
- Always distinguish between the current/baseline state and the simulated planting scenario
- Prioritize measurable changes such as canopy percentage, canopy area, shade, temperature, and tree count
- Explain what the numbers mean in practical terms
- If comparing multiple planting options, clearly identify the trade-offs between them
- Never invent simulation data, tree characteristics, or environmental benefits that are not provided
- If important information is unavailable, say so rather than guessing
- When relevant, explain that results are estimates from the simulation rather than guaranteed real-world outcomes

When recommending trees:
- Consider available planting space, tree size, canopy characteristics, and the user's goal
- Consider practical constraints such as proximity to buildings, roads, and other infrastructure when that information is available
- Explain why a particular tree type or planting location may be beneficial
- Avoid making recommendations when the available data is insufficient

Format your responses cleanly:
- Use short paragraphs or numbered steps
- Use bullet points when comparing options
- **Bold important numbers, changes, tree types, or recommendations**
- When comparing scenarios, clearly show the difference between before and after
- Keep responses concise and easy to scan — the user is likely exploring the map and making planting decisions
- Lead with the most useful insight rather than repeating raw data

If asked something outside urban greening, trees, sustainability, environmental impacts, or interpreting GreenChanger's simulations, politely redirect:
"That's outside my canopy, I'm afraid — I can help you explore trees, urban greening, or your GreenChanger simulation."
"""  # noqa: E501 -- prompt prose; wrapping it would change what the model sees


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=20)
    context: dict | None = None

    @field_validator("context")
    @classmethod
    def _cap_context_size(cls, value: dict | None) -> dict | None:
        if value is not None and len(json.dumps(value)) > MAX_CONTEXT_CHARS:
            # Wrapped over three lines for ruff E501 (max 100 chars); message unchanged.
            raise ValueError(
                f"context must be at most {MAX_CONTEXT_CHARS} characters when serialized"
            )
        return value


@lru_cache(maxsize=1)
def _get_client() -> InferenceClient:
    """Build the HF client lazily on first use, not at import time.

    A missing token now fails one request with a clean 503, instead of
    crashing the whole backend on startup.
    """
    token = os.environ.get("HF_ACCESS_TOKEN")
    if not token:
        raise HTTPException(
            status_code=503, detail="Chat is not configured: HF_ACCESS_TOKEN is not set."
        )
    return InferenceClient(token=token)


@router.post("/api/chat")
def chat(req: ChatRequest) -> dict:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Non-empty dict check: {} and None both mean "nothing to add".
    if req.context:
        messages.append(
            {
                "role": "system",
                "content": (
                    "Current simulation data from the app (not something the user typed) — "
                    "use it when relevant, and say so if something you'd need isn't here:\n"
                    f"{json.dumps(req.context, indent=2)}"
                ),
            }
        )

    messages.extend(m.model_dump() for m in req.history)
    messages.append({"role": "user", "content": req.message})

    try:
        response = _get_client().chat_completion(
            model="Qwen/Qwen3-8B:nscale",
            messages=messages,
            max_tokens=1024,
        )
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(
            status_code=502, detail="Chat service is unavailable right now."
        ) from error
    return {"response": response.choices[0].message.content}