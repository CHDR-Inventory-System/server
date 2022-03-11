from argparse import ArgumentParser
from routes.users import users_blueprint
from routes.reservation import reservation_blueprint
from routes.inventory import inventory_blueprint
import logging
from flask import Flask
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from util.config import secrets
from util.email import Emailer
from flask_jwt_extended import (
    get_jwt,
    set_access_cookies,
    create_access_token,
    get_jwt_identity,
)
from datetime import datetime, timedelta, timezone

app = Flask(__name__)
app.config["IMAGE_FOLDER"] = secrets["IMAGE_UPLOAD_FOLDER"]
app.config["JWT_SECRET_KEY"] = secrets["JWT_SECRET_KEY"]
app.config["MAIL_SERVER"] = secrets["EMAIL_SERVER"]
app.config["MAIL_PORT"] = secrets["EMAIL_PORT"]
app.config["MAIL_USERNAME"] = secrets["EMAIL_USERNAME"]
app.config["MAIL_PASSWORD"] = secrets["EMAIL_PASSWORD"]
app.config["MAIL_USE_SSL"] = secrets["EMAIL_USE_SSL"]
app.config["MAIL_USE_TLS"] = secrets["EMAIL_USE_TLS"]
app.config["JWT_SECRET_KEY"] = secrets["JWT_SECRET_KEY"]
app.config["JWT_ERROR_MESSAGE_KEY"] = "error"
app.config["JWT_TOKEN_LOCATION"] = ["cookies"]
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=1)

CORS(app)
JWTManager(app)
Emailer.init(app)

gunicorn_logger = logging.getLogger("gunicorn.error")
app.logger.handlers = gunicorn_logger.handlers
app.logger.setLevel(gunicorn_logger.level)

app.register_blueprint(users_blueprint, url_prefix="/api/users")
app.register_blueprint(reservation_blueprint, url_prefix="/api/reservations")
app.register_blueprint(inventory_blueprint, url_prefix="/api/inventory")


@app.after_request
def refresh_jwt(response):
    """
    If the JWT is close to it's expiration time, create a new one
    """
    try:
        jwt = get_jwt()
        now = datetime.now(timezone.utc)
        target_timestamp = datetime.timestamp(now + timedelta(minutes=30))

        if target_timestamp > jwt["exp"]:
            access_token = create_access_token(identity=get_jwt_identity())
            set_access_cookies(response, access_token)

    except (RuntimeError, KeyError):
        # Case where there is not a valid JWT. Just return the original respone
        pass
    except Exception as err:
        app.logger.error(str(err))

    return response


if __name__ == "__main__":
    parser = ArgumentParser()

    parser.add_argument(
        "--debug",
        default=False,
        action="store_true",
        help="Starts the server in debug mode",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=4565,
        help="The port the server should use (default 4565)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="The host the server should use (default 127.0.0.1)",
    )
    parser.add_argument(
        "--reload",
        default=False,
        action="store_true",
        help="""
            If enabled, the server will automatically restart if there
            are any changes to the source (default false)
            """,
    )

    args = parser.parse_args()

    app.run(port=args.port, debug=args.debug, host=args.host, use_reloader=args.reload)
