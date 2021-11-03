import mysql.connector
import sys
import os
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template
from random import randint

load_dotenv()

try:
    connection = mysql.connector.connect(
        host=os.getenv('DB_HOST'),
        user=os.getenv('DB_USERNAME'),
        password=os.getenv('DB_PASSWORD'),
        database=os.getenv('DB_DATABASE'),
    )
except Exception as err:
    print(err)
    exit(1)

app = Flask(
    __name__, template_folder='../build', static_folder='../build', static_url_path=''
)


def create_error_response(message, status_code):
    return jsonify({'message': message}), status_code


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/items')
def get_item():
    try:
        cursor = connection.cursor()
        cursor.execute('SELECT * FROM example')
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

        return jsonify(items)

    except Exception as err:
        print(err)
        return create_error_response('Item not found', 404)


if __name__ == '__main__':
    use_debug = '--debug' in sys.argv
    app.run(port=4565, debug=use_debug)
