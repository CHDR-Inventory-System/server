import sys
from flask import Flask, jsonify, render_template
from random import randint

app = Flask(
    __name__, template_folder='../build', static_folder='../build', static_url_path=''
)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/message')
def message():
    return jsonify({'message': 'Hello, World!'})


@app.route('/random')
def random_number():
    return jsonify({'number': randint(0, 100)})


if __name__ == '__main__':
    use_debug = '--debug' in sys.argv
    app.run(port=4565, debug=use_debug)
