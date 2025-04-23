from __future__ import annotations

import copy
import json
import uuid
from dataclasses import dataclass
from typing import Any

import httpx
import openai
from livekit.agents import ChatContext, FunctionTool, APIConnectOptions, DEFAULT_API_CONNECT_OPTIONS, NotGivenOr, \
    NOT_GIVEN
from livekit.agents.llm import ToolChoice, llm
from livekit.agents.utils import is_given
from livekit.plugins.openai.utils import to_chat_ctx
from loguru import logger
from openai.types.chat import ChatCompletionChunk

from .dst import DST
from .globals import metadata, name

current_stage = "INTRODUCTION"

@dataclass
class _LLMOptions:
    user: NotGivenOr[str]
    temperature: NotGivenOr[float]
    parallel_tool_calls: NotGivenOr[bool]
    tool_choice: NotGivenOr[ToolChoice]
    store: NotGivenOr[bool]
    metadata: NotGivenOr[dict[str, str]]

class LLM(llm.LLM):
    def __init__(
        self,
        *,
        api_key: NotGivenOr[str] = NOT_GIVEN,
        base_url: NotGivenOr[str] = NOT_GIVEN,
        client: httpx.AsyncClient | None = None,
        user: NotGivenOr[str] = NOT_GIVEN,
        temperature: NotGivenOr[float] = NOT_GIVEN,
        parallel_tool_calls: NotGivenOr[bool] = NOT_GIVEN,
        tool_choice: NotGivenOr[ToolChoice] = NOT_GIVEN,
        store: NotGivenOr[bool] = NOT_GIVEN,
        metadata: NotGivenOr[dict[str, str]] = NOT_GIVEN,
        timeout: httpx.Timeout | None = None,
    ) -> None:
        super().__init__()
        self._base_url = base_url

        self._client = client or httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout
            if timeout
            else httpx.Timeout(connect=15.0, read=5.0, write=5.0, pool=5.0),
            follow_redirects=True,
            limits=httpx.Limits(
                max_connections=50,
                max_keepalive_connections=50,
                keepalive_expiry=120,
            ),
        )


    @staticmethod
    def with_ollama(
        *,
        base_url: str = "http://localhost:11434/v1",
        client: httpx.AsyncClient | None = None,
        temperature: NotGivenOr[float] = NOT_GIVEN,
        parallel_tool_calls: NotGivenOr[bool] = NOT_GIVEN,
        tool_choice: ToolChoice = "auto",
    ) -> LLM:
        """
        Create a new instance of Ollama LLM.
        """

        return LLM(
            api_key="ollama",
            base_url=base_url,
            client=client,
            temperature=temperature,
            parallel_tool_calls=parallel_tool_calls,
            tool_choice=tool_choice,
        )

    def chat(
        self,
        *,
        chat_ctx: ChatContext,
        tools: list[FunctionTool] | None = None,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
        parallel_tool_calls: NotGivenOr[bool] = NOT_GIVEN,
        tool_choice: NotGivenOr[ToolChoice] = NOT_GIVEN,
        extra_kwargs: NotGivenOr[dict[str, Any]] = NOT_GIVEN,
    ) -> LLMStream:
        extra = {}
        if is_given(extra_kwargs):
            extra.update(extra_kwargs)

        if is_given(parallel_tool_calls):
            extra["parallel_tool_calls"] = parallel_tool_calls

        return LLMStream(
            self,
            client=self._client,
            chat_ctx=chat_ctx,
            tools=tools or [],
            conn_options=conn_options,
            extra_kwargs=extra,
        )

END_STREAM_TOKEN = "!@#$%^&*()_+"

class LLMStream(llm.LLMStream):
    def __init__(
        self,
        llm: LLM,
        *,
        client: httpx.AsyncClient,
        chat_ctx: llm.ChatContext,
        tools: list[FunctionTool],
        conn_options: APIConnectOptions,
        extra_kwargs: dict[str, Any],
    ) -> None:
        super().__init__(llm=llm, chat_ctx=chat_ctx, tools=tools, conn_options=conn_options)
        self._client = client
        self._llm = llm
        self._extra_kwargs = extra_kwargs
        self._headers = {"Content-Type": "application/json"}

    @staticmethod
    def prepare_request_data(dialogue: Any, current_stage: str, length_type: int = 64):
        copy_dialogue = copy.deepcopy(dialogue)
        user_input = copy_dialogue[-1]["content"] if copy_dialogue[-1]["role"] == "user" else ""
        return {
            "name": name,
            "metadata": metadata,
            "user_input": user_input,
            "current_stage": current_stage,
            "chat_history": [{"role": item["role"], "message": item["content"]} for item in copy_dialogue if item["role"] in ["user", "assistant"]],
            "streaming": True,
            "length_type": length_type
        }

    async def _run(self) -> None:
        global current_stage
        self._oai_stream: None = None
        self._tool_call_id: str | None = None
        self._fnc_name: str | None = None
        self._fnc_raw_arguments: str | None = None
        self._tool_index: int | None = None

        chat_context = to_chat_ctx(self._chat_ctx, id(self._llm))
        dst_client = DST()
        dst_response = await dst_client.send(dialogue=chat_context, metadata=metadata, current_stage=current_stage)

        logger.info(dst_response)

        if dst_response is not None:
            current_stage = dst_response["data"]["next_stage"]
            logger.info({
                "id": dst_response["data"]["transaction_id"],
                "next_stage": current_stage,
                "time": dst_response["data"]["time"],
                "completion_tokens": dst_response["data"]["completion_tokens"],
                "total_tokens": dst_response["data"]["total_tokens"]
            })
        # current_stage = current_stage if current_stage != "VERIFY_" else "VERIFY"

        if current_stage != "END":
            async with httpx.AsyncClient() as client:
                payload = self.prepare_request_data(dialogue=chat_context, current_stage=current_stage)
                try:
                    async with client.stream("POST", url=self._llm._base_url, headers=self._headers, data=json.dumps(payload), timeout=20) as response:
                        response.raise_for_status()
                        end_of_chat = False
                        async for chunk in response.aiter_bytes():
                            text_chunk = chunk.decode("utf-8", errors="ignore")
                            if END_STREAM_TOKEN in text_chunk:
                                end_of_chat = True
                            if not end_of_chat:
                                # tts_stream = ChatCompletionChunk(
                                #     id=uuid.uuid4().hex,
                                #     created=1712016000,
                                #     model="emandai",
                                #     choices=[{"index": 0, "delta": {"content": text_chunk}, "finish_reason": None}],
                                #     usage={"prompt_tokens": 0, "completion_tokens": 10, "total_tokens": len(text_chunk)}
                                # )
                                # self._event_ch.send_nowait(value=tts_stream)
                                # TODO: Self-reformat text_chunk or server side reformat to log metrics
                                self._event_ch.send_nowait(value=text_chunk)
                        logger.info(response.json())
                except Exception as e:
                    raise e
        else:
            current_stage = "INTRODUCTION"
