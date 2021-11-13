import mysql.connector
from flask import Blueprint, jsonify, current_app
from util.database import Database
from util.response_util import create_error_response

inventory_blueprint = Blueprint("inventory", __name__)


@inventory_blueprint.route("/")
@Database.with_connection
def get_all(**kwargs):
    cursor = kwargs["cursor"]

    try:
        cursor.execute("SELECT * FROM example")
        items = []

        for row in cursor.fetchall():
            items.append(
                {
                    "id": row["ID"],
                    "name": row["NAME"],
                    "description": row["Description"],
                    "date": row["Date"],
                    "moveable": bool(row["Moveable"]),
                    "quantity": row["Quantity"],
                }
            )

        return jsonify(items)

    except mysql.connector.Error as err:
        current_app.logger.exception(str(err))
        return create_error_response("An unexpected error occurred", 500)
