from flask import Blueprint, jsonify, current_app
from util.database import Database
from util.response_util import create_error_response

inventory_blueprint = Blueprint('inventory', __name__)


@inventory_blueprint.route('/')
def get_all():
    try:
        cursor = Database.execute_query('SELECT * FROM example')
        items = []

        for row in cursor.fetchall():
            item_id, name, desc, date, moveable, quantity = row

            items.append(
                {
                    'id': item_id,
                    'name': name,
                    'description': desc,
                    'date': date,
                    'moveable': bool(moveable),
                    'quantity': quantity,
                }
            )

        cursor.close()
        Database.close_connection()

        return jsonify(items)

    except Exception as err:
        current_app.logger.exception(str(err))
        return create_error_response('An unexpected error occurred', 500)
