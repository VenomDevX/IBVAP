import os
import urllib.request

from loguru import logger

os.makedirs("data/demo", exist_ok=True)

samples = {
    "street_traffic.mp4": "https://github.com/intel-iot-devkit/sample-videos/raw/master/person-bicycle-car-detection.mp4",
    "people_walking.mp4": "https://github.com/intel-iot-devkit/sample-videos/raw/master/head-pose-face-detection-female-and-male.mp4",
    "highway_border.mp4": "https://github.com/intel-iot-devkit/sample-videos/raw/master/car-detection.mp4",
    "indoor_checkpoint.mp4": "https://github.com/intel-iot-devkit/sample-videos/raw/master/classroom.mp4",
}

for name, url in samples.items():
    filepath = f"data/demo/{name}"
    if not os.path.exists(filepath):
        logger.info(f"Downloading {name}...")
        try:
            urllib.request.urlretrieve(url, filepath)
            logger.success(f"Downloaded {name}")
        except Exception as e:
            logger.error(f"Failed to download {name}: {e}")
    else:
        logger.info(f"{name} already exists.")
