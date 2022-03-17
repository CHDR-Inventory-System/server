import os
from dotenv import load_dotenv

load_dotenv()

secrets = {
    "JWT_SECRET_KEY": os.getenv("JWT_SECRET_KEY"),
    "DB_HOST": os.getenv("DB_HOST"),
    "DB_USERNAME": os.getenv("DB_USERNAME"),
    "DB_PASSWORD": os.getenv("DB_PASSWORD"),
    "DB_DATABASE": os.getenv("DB_DATABASE"),
    "EMAIL_USERNAME": os.getenv("EMAIL_USERNAME"),
    "EMAIL_PASSWORD": os.getenv("EMAIL_PASSWORD"),
    "EMAIL_SERVER": os.getenv("EMAIL_SERVER"),
    "EMAIL_PORT": os.getenv("EMAIL_PORT"),
    "EMAIL_USE_SSL": os.getenv("EMAIL_USE_SSL").lower() == "true",
    "EMAIL_USE_TLS": os.getenv("EMAIL_USE_TLS").lower() == "true",
    "IMAGE_UPLOAD_FOLDER": os.getenv("IMAGE_UPLOAD_FOLDER", default="./images"),
    "BASE_URL": os.getenv("BASE_URL", default="http://127.0.0.1/4565"),
}


for key, value in secrets.items():
    if value is None:
        raise KeyError(
            f"Expected value for {key}. Make sure {key} is set and has a value in the .env file."
        )
