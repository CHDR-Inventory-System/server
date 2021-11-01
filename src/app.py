import sys
from flask import Flask, jsonify
from random import randint

app = Flask(__name__)

@app.route('/')
def index():
    return jsonify({'message': 'Hello, World!'})


@app.route('/random')
def random_number():
    return jsonify({'number': randint(0, 100)})


if __name__ == '__main__':
    use_debug = '--debug' in sys.argv
    app.run(port=4565, debug=use_debug)
