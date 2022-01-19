import os
from dotenv import load_dotenv

load_dotenv()

secrets = {
    "JWT_SECRET_KEY": os.getenv("JWT_SECRET_KEY"),
    "DB_HOST": os.getenv("DB_HOST"),
    "DB_USERNAME": os.getenv("DB_USERNAME"),
    "DB_PASSWORD": os.getenv("DB_PASSWORD"),
    "DB_DATABASE": os.getenv("DB_DATABASE"),
}


for key, value in secrets.items():
    if value is None:
        raise KeyError(
            f"Expected value for {key}. Make sure {key} is set and has a value in the .env file."
        )
