from argparse import ArgumentParser
from routes.users import users_blueprint
from routes.reservation import reservation_blueprint
from routes.inventory import inventory_blueprint
import logging
from flask import Flask
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from util.scheduler import init_scheduler
from util.config import secrets
from util.email import Emailer


app = Flask(__name__)
with app.app_context():
    app.config["IMAGE_FOLDER"] = secrets["IMAGE_UPLOAD_FOLDER"]
    app.config["JWT_SECRET_KEY"] = secrets["JWT_SECRET_KEY"]
    app.config["SCHEDULER_TIMEZONE"] = "America/New_York"
    app.config["MAIL_SERVER"] = secrets["EMAIL_SERVER"]
    app.config["MAIL_PORT"] = secrets["EMAIL_PORT"]
    app.config["MAIL_USERNAME"] = secrets["EMAIL_USERNAME"]
    app.config["MAIL_PASSWORD"] = secrets["EMAIL_PASSWORD"]
    app.config["MAIL_USE_SSL"] = secrets["EMAIL_USE_SSL"]
    app.config["MAIL_USE_TLS"] = secrets["EMAIL_USE_TLS"]

with app.app_context():
    # init_db()
    CORS(app)
    JWTManager(app)
    init_scheduler(app)
    Emailer.init(app)

gunicorn_logger = logging.getLogger("gunicorn.error")
app.logger.handlers = gunicorn_logger.handlers
app.logger.setLevel(gunicorn_logger.level)

app.register_blueprint(users_blueprint, url_prefix="/api/users")
app.register_blueprint(reservation_blueprint, url_prefix="/api/reservation")
app.register_blueprint(inventory_blueprint, url_prefix="/api/inventory")


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
