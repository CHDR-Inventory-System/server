import sys
import logging
from routes.reservation import reservation_blueprint
from flask import Flask, render_template
from flask_cors import CORS

app = Flask(
    __name__, template_folder="../build", static_folder="../build", static_url_path=""
)

CORS(app)

gunicorn_logger = logging.getLogger("gunicorn.error")
app.logger.handlers = gunicorn_logger.handlers
app.logger.setLevel(gunicorn_logger.level)

app.register_blueprint(reservation_blueprint, url_prefix="/api/reservations")


@app.route("/")
def index():
    return render_template("index.html")


if __name__ == "__main__":
    use_debug = "--debug" in sys.argv
    app.run(port=4565, debug=use_debug)
