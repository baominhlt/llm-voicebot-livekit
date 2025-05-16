import datetime
import logging
import os

os.makedirs("./log", exist_ok=True)
now = datetime.datetime.now()
log_file_name = f"log/{now.month:02d}-{now.year}.log"
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
