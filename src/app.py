from argparse import ArgumentParser
from routes.users import users_blueprint
from routes.reservation import reservation_blueprint
from routes.inventory import inventory_blueprint
import logging
from flask import Flask, jsonify, request, Response
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from util.scheduler import init_scheduler
from util.config import secrets
from util.email import Emailer
from flask_jwt_extended import (
    get_jwt,
    set_access_cookies,
    create_access_token,
    get_jwt_identity,
    decode_token,
    jwt_required,
)
from flask_jwt_extended.config import config as jwt_config
from datetime import datetime, timedelta, timezone


app = Flask(__name__)

app.config["IMAGE_FOLDER"] = secrets["IMAGE_UPLOAD_FOLDER"]
app.config["JWT_SECRET_KEY"] = secrets["JWT_SECRET_KEY"]
app.config["SCHEDULER_TIMEZONE"] = "America/New_York"
app.config["MAIL_SERVER"] = secrets["EMAIL_SERVER"]
app.config["MAIL_PORT"] = secrets["EMAIL_PORT"]
app.config["MAIL_USERNAME"] = secrets["EMAIL_USERNAME"]
app.config["MAIL_PASSWORD"] = secrets["EMAIL_PASSWORD"]
app.config["MAIL_USE_SSL"] = secrets["EMAIL_USE_SSL"]
app.config["MAIL_USE_TLS"] = secrets["EMAIL_USE_TLS"]
app.config["JWT_SECRET_KEY"] = secrets["JWT_SECRET_KEY"]
app.config["JWT_ERROR_MESSAGE_KEY"] = "error"
app.config["JWT_TOKEN_LOCATION"] = ["cookies", "headers"]
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=12)


CORS(app)
JWTManager(app)
init_scheduler(app)
Emailer.init(app)

gunicorn_logger = logging.getLogger("gunicorn.error")
app.logger.handlers = gunicorn_logger.handlers
app.logger.setLevel(gunicorn_logger.level)

app.register_blueprint(users_blueprint, url_prefix="/api/users")
app.register_blueprint(reservation_blueprint, url_prefix="/api/reservations")
app.register_blueprint(inventory_blueprint, url_prefix="/api/inventory")


@app.after_request
def refresh_jwt(response: Response) -> Response:
    """
    If the JWT is close to it's expiration time (one hour before it expires),
    create a new one. If a JWT is already present in the request, this method
    also sets a cookie that hold the JWT's expiration time.
    """

    if request.path == "/api/refreshToken":
        # Don't generate a new JWT if the user already requested
        # to refresh the old one
        return response

    try:
        jwt = get_jwt()
        now = datetime.now(timezone.utc)
        target_timestamp = datetime.timestamp(now + timedelta(hours=1))

        # Create a new JWT if it's close to expiring then set it as a session cookie
        if target_timestamp > jwt["exp"]:
            token = create_access_token(identity=get_jwt_identity())
            jwt = decode_token(token)
            set_access_cookies(response, token)
        else:
            # Here, the JWT hasn't expired, but we'll set the csrf cookie again just
            # in case the user tampered with it on the client side
            response.set_cookie(
                jwt_config.access_csrf_cookie_name,
                value=jwt["csrf"],
                max_age=jwt_config.cookie_max_age,
                secure=jwt_config.cookie_secure,
                httponly=False,
                domain=jwt_config.cookie_domain,
                path=jwt_config.access_csrf_cookie_path,
                samesite=jwt_config.cookie_samesite,
            )

        response.set_cookie("session_exp", value=str(jwt["exp"]), expires=jwt["exp"])

        return response
    except (RuntimeError, KeyError):
        # Case where there is not a valid JWT. Just return the original respone
        return response
    except Exception as err:
        app.logger.error(str(err))
        return response


@app.route("/api/refreshToken", methods=["GET"])
@jwt_required()
def create_new_token():
    """
    Creates a new JWT from the old JWT. If a JWT wasn't found in the header
    or set as a cookie, this will return a 401
    """
    token = create_access_token(identity=get_jwt_identity())
    jwt = decode_token(token)
    response = jsonify({"token": token})

    set_access_cookies(response, token)
    response.set_cookie("session_exp", value=str(jwt["exp"]), expires=jwt["exp"])

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
