# CHDR Inventory System - Server

## Getting Started

Before you start, make sure you have Python 3 and the [virtualenv](https://packaging.python.org/guides/installing-using-pip-and-virtual-environments/) package installed.

You'll also need to create a `.env` file in the root directory that looks like this:

```ini
DB_HOST=some-ip
DB_USERNAME=some-username
DB_PASSWORD=-some-password
DB_DATABASE=some-database-name
# How long before a connection to the database times out.
# The default is 60 seconds.
DB_CONNECTION_TIMEOUT=60
```

## Running The Server
To actually start the server, execute the following commands:

* Make sure you're in the root directory of the project and run `python3 -m venv ./venv`.
* Run `source ./venv/bin/activate` on macOS/Linux or `.\env\Scripts\activate` on Windows to activate the virtual environment
* Run `pip install -r requirements.txt` to install the required dependencies.
* Run `python3 src/app.py` to start the server
    * You can also run `python3 src/app.py --debug` to start the server in debug mode.
    * If you're on a Unix system, you can also start the server with `gunicorn -c config/gunicorn.conf.py`.
