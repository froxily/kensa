from configparser import ConfigParser
import os
from pathlib import Path

settings = ConfigParser()
with open("assets/collector.ini", encoding="utf-8") as stream:
    settings.read_file(stream)
print("worker:", settings["worker"]["name"], flush=True)

root = Path(os.environ["SEAGRASS_SOURCE_ROOT"])
print("entries:", len(list(root.iterdir())))
