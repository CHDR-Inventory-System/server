import sys
from routes.users import users_blueprint
from routes.reservation import reservation_blueprint
from routes.inventory import inventory_blueprint
import logging
from flask import Flask, render_template
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from util.config import secrets

app = Flask(__name__)
app.config["IMAGE_FOLDER"] = "./images"
app.config["JWT_SECRET_KEY"] = secrets["JWT_SECRET_KEY"]

CORS(app)
JWTManager(app)

gunicorn_logger = logging.getLogger("gunicorn.error")
app.logger.handlers = gunicorn_logger.handlers
app.logger.setLevel(gunicorn_logger.level)

app.register_blueprint(users_blueprint, url_prefix="/api/users")
app.register_blueprint(reservation_blueprint, url_prefix="/api/reservations")
app.register_blueprint(inventory_blueprint, url_prefix="/api/inventory")


@app.route("/")
def index():
    return render_template("index.html")


if __name__ == "__main__":
    use_debug = "--debug" in sys.argv
    app.run(port=4565, debug=use_debug)
