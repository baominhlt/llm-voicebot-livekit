import datetime
import logging
import os
import random

length_type = int(os.getenv("LENGTH_TYPE", 64))

# Initialize logging
now = datetime.datetime.now()
os.makedirs("./log", exist_ok=True)
log_file_name = f"log/{now.day:02d}-{now.month:02d}-{now.year}.log"
log_formatter = logging.Formatter("timestamp=%(asctime)s, level=%(levelname)s, message=%(message)s",
                                  datefmt="%d/%m/%Y %H:%M:%S")
# terminal_handler = logging.StreamHandler()
# terminal_handler.setFormatter(log_formatter)
file_handler = logging.FileHandler(log_file_name, mode="a", encoding="utf-8")
file_handler.setFormatter(log_formatter)

logger = logging.getLogger()
logger.setLevel(logging.INFO)
# logger.addHandler(terminal_handler)
logger.addHandler(file_handler)

# Default customer's information
default_name = "Kevin"
metadata_template = {"dob": "Date of birth", "ssn": "Social Security Number",
                     "zipcode": "Local Zipcode", "ref_number": "Reference Number"}
metadata = f"Customer Information:\n- Name: {default_name}\n- Total Debt: ${random.randint(1, 10) * 1000}\n- Due Date: {(datetime.datetime.now() + datetime.timedelta(days=7)).strftime('%d/%m/%Y')}\n- T-max: {(datetime.datetime.now() + datetime.timedelta(days=5)).strftime('%d/%m/%Y')}"

# VERIFY State information
default_metadata = {"dob": "", "ssn": "", "zipcode": "", "ref_number": ""}
default_slot_value = {"dob": "NONE", "ssn": "NONE", "zipcode": "NONE", "ref_number": "NONE"}
default_prioritize_key = [""]
default_number_of_optional_params = 0
default_json_schema = "{key_name: value}"
num_min_verify_information = 1
