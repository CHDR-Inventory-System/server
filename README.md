# CHDR Inventory System - Server

## Getting Started

Before you start, make sure you have Python 3 and the [virtualenv](https://packaging.python.org/guides/installing-using-pip-and-virtual-environments/) package installed.

## Running The Server
To actually start the server, execute the following commands:

* Make sure you're in the root directory of the project and run `python3 -m venv ./venv`.
* Run `source ./venv/bin/activate` on macOS/Linux or `.\env\Scripts\activate` on Windows to activate the virtual environment
* Run `pip install -r requirements.txt` to install the required dependencies.
* Run `gunicorn -c config/gunicorn.conf.py` to start the server
    * Additionally, you can also run `gunicorn -c config/gunicorn.conf.py --reload` to start the server in hot-reload mode. This will restart the workers whenever there's a change in the source code.
