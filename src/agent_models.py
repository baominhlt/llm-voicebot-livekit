from dataclasses import dataclass
from typing import Any

from livekit.plugins import elevenlabs, groq, openai


@dataclass
class AgentModel:
    STT: Any = groq.STT(model="whisper-large-v3-turbo", language="vi")
    # STT: Any = deepgram.STT(
    #         model="nova-2-conversationalai",
    #         model="nova-2-general",
    #         language="vi",
    #         smart_format=False,
    #         numerals=False
    #     )
    LLM: Any = openai.LLM.with_azure(azure_deployment="va-gpt-4o-mini", api_version="2024-10-01-preview")
    TTS: Any = elevenlabs.TTS(voice_id="ODq5zmih8GrVes37Dizd", model="eleven_flash_v2_5", language="vi")
