import argparse
import ast
import datetime
import json
import os
import re
from typing import List

from loguru import logger
from tqdm import tqdm

patterns = {
    "begin_session": "BEGIN NEW SESSION",
    "end_session": "Usage:",
    "history_dialogue": "History:",
    "stt": "EOU metrics:",
    "llm": "LLM metrics:",
    "tts": "TTS metrics:",
    "dst": "DST Output:"
}
information_keys = {
    "stt": "end_of_utterance_delay",
    "llm": "ttft",
    "tts": "ttfb",
    "dst": "client_time",
}


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--log_file_path", type=str, default=None, help="Path of logging file.")
    parser.add_argument("--log_files_directory", type=str, default=None, required=False, help="Path of logging files directory.")
    parser.add_argument("--output_directory", type=str, default=None, help="Path of output parsed log directory")
    return parser.parse_args()

def read_log_file(file_path: str) -> List[str]:
    with open(file_path, "r") as f:
        data = f.readlines()
    return data

def split_session(data: List[str]) -> List[List[str]]:
    output = []
    session = []
    flag = False
    for line in data:
        if patterns["begin_session"] in line:
            if flag:
                if len(session) > 0:
                    output.append(session)
                session = []
            flag = True
        if flag:
            session.append(line)
        if patterns["end_session"] in line:
            flag = False
            if len(session) > 0:
                output.append(session)
            session = []
    return output

def parse_string_equal_to_dict(text: str) -> dict:
    return {item.split("=")[0]: float(item.split("=")[1]) for item in text.split(", ")}

def parse_timestamp(text: str) -> str:
    return re.sub(r"[timesap=,]", "", re.findall(r"timestamp=.+?,", text)[0])

def parse_history_log(session: List[str]) -> dict:
    # Process timestamp
    begin = parse_timestamp(text=session[0])
    end = parse_timestamp(text=session[-1])
    # Process dialogue
    dialogue = ""
    for line in session:
        if patterns["history_dialogue"] in line:
            current_dialogue = re.sub("message=.+\[", "[", re.findall("message=.+", line)[0])
            if current_dialogue not in dialogue:
                dialogue = current_dialogue
    dialogue = ast.literal_eval(dialogue.strip().replace("\n", "\\n"))
    dialogue = [turn for turn in dialogue if turn["role"] != "system" and turn["content"] != ""]
    # Process usage
    usage = re.sub(r"[()]", "", re.findall(r"\(.+\)", session[-1])[0])
    usage = parse_string_equal_to_dict(text=usage)
    return {
        "begin": begin,
        "end": end,
        "dialogue": dialogue,
        "usage": usage
    }

def get_latency_information(log: str, key: str) -> dict:
    timestamp = parse_timestamp(text=log)
    message = re.findall("message=.+", log)[0].replace(f"message={patterns[key]}", "").strip()
    if key == "dst":
        information = ast.literal_eval(message)
    else:
        information = parse_string_equal_to_dict(text=message)
    return {
        "timestamp": timestamp,
        information_keys[key]: information[information_keys[key]],
        "data": information,
    }

def parse_latency_log(session: List[str]):
    output = {"stt": [], "llm": [], "tts": [], "dst": []}
    for key in output.keys():
        logs = [line for line in session if patterns[key] in line]
        logs = list(set(logs))
        output[key] = [get_latency_information(log=log, key=key) for log in logs]
    return output



def main():
    args = parse_arguments()
    log_file_path = args.log_file_path
    log_files_directory = args.log_files_directory
    output_directory = args.output_directory

    histories = []
    latency_logs = {"stt": [], "llm": [], "tts": [], "dst": []}

    if log_file_path is not None:
        data = read_log_file(file_path=log_file_path)
        sessions = split_session(data=data)
    elif log_files_directory is not None:
        sessions = []
        for file_name in os.listdir(log_files_directory):
            data = read_log_file(file_path=file_name)
            sessions.extend(split_session(data=data))
    else:
        raise "Do not have any logging files to parse"

    loop = tqdm(sessions)
    for session in loop:
        try:
            histories.append(parse_history_log(session=session))
            output_latency_logs = parse_latency_log(session=session)
            for key in latency_logs:
                latency_logs[key].extend(output_latency_logs[key])
        except Exception:
            pass
    logger.info(f"Number of history: {len(histories)}")

    if output_directory is None:
        now = datetime.datetime.now()
        output_directory = f"./parsed_log/{now.day:02d}-{now.month:02d}-{now.year}"
    os.makedirs(output_directory, exist_ok=True)
    with open(os.path.join(output_directory, "conversation_log.json"), "w") as f:
        json.dump(histories, f, indent=2, ensure_ascii=False)
    with open(os.path.join(output_directory, "latency_log.json"), "w") as f:
        json.dump(latency_logs, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()