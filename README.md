# CHDR Inventory System - Server

## Setting Up Your Environment

Before you start, make sure you have Python >=3.5 and the [virtualenv](https://packaging.python.org/guides/installing-using-pip-and-virtual-environments/) package installed.

Create a `.env` file in the root directory that looks like this:

```ini
DB_HOST=some-ip
DB_USERNAME=some-username
DB_PASSWORD=some-password
DB_DATABASE=some-database-name
```

1. Make sure you're in the root directory of the project and run `python3 -m venv ./venv` to create a virtual environment. Once that finishes, run `source ./venv/bin/activate` on macOS/Linux or `.\env\Scripts\activate` on Windows to activate the virtual environment.

2. Run `pip3 install -r dev-requirements.txt` to install necessary dependencies.

3. This repo makes use of [pre-commit](https://pre-commit.com/) and [black](https://github.com/psf/black) to lint and format all files before they're committed. After you activate the virtual environment, run `pre-commit install` to set up the pre-commit script and `pre-commit run -a` to test it. If all was successful, you should see that `black` and `flake8` were run in the terminal. This step will help catch errors down the line **before** you commit.

## Running the Server

To actually start the server, make sure the virtual environment is activated.

Run `python3 src/app.py` to start the server. You can also run `python3 src/app.py --debug` to start the server in auto-reload mode. This will restart the server whenever you make a change to a file. If you want to run the server using a different host or port, you can also optionally pass `--port [PORT]` or `--host [HOST]`.


If you're on a Unix system, you can also start the server with `gunicorn -c gunicorn.conf.py`. This allows you to keep track of server logs and make use of gunicorn workers. Use `gunicorn -c gunicorn.conf.py --reload` to start the server in auto-reload mode.
