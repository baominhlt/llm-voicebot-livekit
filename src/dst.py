import copy
import json
import os
from typing import Any, Dict, List, Optional

import httpx
from httpx import URL

from src.globals import (default_json_schema, default_metadata, default_name,
                         default_number_of_optional_params, default_prioritize_key, default_slot_value,
                         length_type, logger, metadata, metadata_template, num_min_verify_information)

DEFAULT_TIMEOUT = 30
VERIFY_STATE = "VERIFY"
STATE_PURPOSE_STATE = "STATE_PURPOSE"
OUT_OF_STATE = "OTHER"


class DST:
    def __init__(self, base_url: Optional[URL] = None, verify_url: Optional[URL] = None, api_key: Optional[str] = None):
        self.urls = {
            "VERIFY": verify_url if verify_url is not None else os.getenv("DST_VERIFY_ENDPOINT", None),
            "OTHER": base_url if base_url is not None else os.getenv("DST_ENDPOINT", None)
        }
        self.headers = {"Content-Type": "application/json"}
        self.prepare_authorization(api_key=api_key)

    def prepare_authorization(self, api_key: Optional[str]):
        api_key = api_key if api_key is not None else os.getenv("DST_API_KEY", None)
        if api_key is not None:
            self.headers.update({"Authorization": api_key})

    @staticmethod
    def preprocess_dialogue(dialogue: List[Dict[str, str]]) -> str:
        mapping_role_dict = {"user": "Debtor", "assistant": "Debt Collector"}
        dialogue_str = ""
        current_role = ""
        deep_copy_dialogue = copy.deepcopy(dialogue)
        for turn in deep_copy_dialogue:
            if turn["role"] in mapping_role_dict:
                if turn["role"] != current_role and turn["content"] != "":
                    dialogue_str += f"{mapping_role_dict[turn['role']]}: {turn['content']}\n"
                    current_role = turn["role"]
                else:
                    dialogue_str = dialogue_str.strip() + " " + turn["content"]
        return dialogue_str.strip()

    def validate_verify_information(self, information: dict) -> bool:
        information = {key: str(value).replace("NONE", "None") for key, value in information.items()}
        return len(information) - list(information.values()).count("None") >= num_min_verify_information

    def add_information_into_metadata(self, information: dict):
        global metadata
        for key, value in information.items():
            if str(value).lower() != "none" and metadata_template[key] not in metadata:
                metadata += f"\n- {metadata_template[key]}: {value}"
        return metadata

    async def send(self, dialogue: Any, current_stage: str):
        global metadata
        request_data = {
            "length_type": length_type,
            "name": default_name,
            "dialogue": self.preprocess_dialogue(dialogue=dialogue),
            "current_stage": current_stage
        }
        try:
            if current_stage == VERIFY_STATE:
                url = self.urls[current_stage]
                verify_request_data = copy.deepcopy(request_data)
                verify_request_data.update({
                    "metadata": default_metadata,
                    "pre_slot_value": default_slot_value,
                    "prioritize_params": default_prioritize_key,
                    "number_of_optional_params": default_number_of_optional_params,
                    "json_schema": default_json_schema
                })
                response = await self.send_request(url=url, request_data=verify_request_data)
                logger.info(f"Slot filling DST output: {response}")
                metadata = self.add_information_into_metadata(information=response["data"]["reply"])
                if self.validate_verify_information(information=response["data"]["reply"]):
                    response["data"]["next_stage"] = STATE_PURPOSE_STATE
                    return response
        except Exception as e:
            logger.error(str(e))

        url = self.urls[OUT_OF_STATE]
        request_data["metadata"] = metadata
        if current_stage == VERIFY_STATE:
            request_data["json_schema"] = default_json_schema
        response = await self.send_request(url=url, request_data=request_data)
        return response

    async def send_request(self, url: URL, request_data: dict) -> Any:
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url=url, headers=self.headers, data=json.dumps(request_data),
                                             timeout=DEFAULT_TIMEOUT)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPError as e:
                logger.exception(f"{e}\nLog input request: {request_data}")
                return None
