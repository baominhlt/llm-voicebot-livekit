import copy
import json
import os
from typing import Optional, List, Dict, Any

import httpx
from httpx import URL
from loguru import logger

DEFAULT_TIMEOUT = 10
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

    async def send(self, dialogue: Any, metadata: dict, current_stage: str, pre_slot_value: str = ""):
        request_data = {
            "length_type": 64,
            "name": "Yasuo",
            "dialogue": self.preprocess_dialogue(dialogue=dialogue),
            "current_stage": current_stage
        }
        if current_stage in metadata:
            url = self.urls[current_stage]
            dialogue_metadata = metadata[current_stage]
            request_data["pre_slot_value"] = {"dob": "NONE", "ref_number": "NONE", "zipcode": "NONE", "ssn": "NONE"}
            request_data["prioritize_params"] = ["ref_number"]
            request_data["number_of_optional_params"] = 1
            request_data["json_schema"] = "{key_name: value}"
        else:
            url = self.urls[OUT_OF_STATE]
            dialogue_metadata = metadata[OUT_OF_STATE]
        request_data["metadata"] = dialogue_metadata

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url=url, headers=self.headers, data=json.dumps(request_data), timeout=DEFAULT_TIMEOUT)
                response.raise_for_status()
                response = response.json()
                if current_stage == "VERIFY":
                    response["data"]["next_stage"] = "STATE_PURPOSE" if response["data"]["result"] else "VERIFY"
                return response
            except httpx.HTTPError as e:
                logger.exception(f"{e}")
                return None
