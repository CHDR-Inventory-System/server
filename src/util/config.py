import os
from dotenv import load_dotenv

load_dotenv()

secrets = {
    "JWT_SECRET_KEY": os.getenv("JWT_SECRET_KEY"),
    "DB_HOST": os.getenv("DB_HOST"),
    "DB_USERNAME": os.getenv("DB_USERNAME"),
    "DB_PASSWORD": os.getenv("DB_PASSWORD"),
    "DB_DATABASE": os.getenv("DB_DATABASE"),
    "LDAP_SERVER": os.getenv("LDAP_SERVER"),
    "BASE_DN": os.getenv("BASE_DN"),
    "DOMAIN": os.getenv("DOMAIN"),
    "IMAGE_UPLOAD_FOLDER": os.getenv("IMAGE_UPLOAD_FOLDER", default="./images"),
    "BASE_URL": os.getenv("BASE_URL", default=""),
    "SCHEDULER_ENABLED": (
        os.getenv("SCHEDULER_ENABLED", default="true").lower() == "true"
    ),
}


for key, value in secrets.items():
    if value is None:
        raise KeyError(
            f"Expected value for {key}. Make sure {key} is set and has a value in the .env file."
        )
