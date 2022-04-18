# CHDR Inventory System - Server

## Setting Up Your Environment

Before you start, you'll need the following:
- Python >=3.7 and the [virtualenv](https://packaging.python.org/guides/installing-using-pip-and-virtual-environments/)
- [docker](https://docs.docker.com/get-docker/)
- [docker-compose](https://docs.docker.com/compose/install/)

Create a `.env` file in the root directory that looks like this:

```ini
JWT_SECRET_KEY=change-this-value

# These are the credentials to the phpmyadmin service that runs in the
# docker container (see docker-compose.yaml for details)
DB_HOST=localhost
DB_USERNAME=root
DB_PASSWORD=secret
DB_DATABASE=chdr_inventory_project

# There's additional config required to get emailing to work.
# Look at src/config.py for additional values.
```

1. Make sure you're in the root directory of the project and run `python3 -m venv ./venv` to create a virtual environment. Once that finishes, run `source ./venv/bin/activate` on macOS/Linux or `.\venv\Scripts\activate` on Windows to activate the virtual environment.

2. Run `pip install -r dev-requirements.txt` to install necessary dependencies.

3. This repo makes use of [pre-commit](https://pre-commit.com/) and [black](https://github.com/psf/black) to lint and format all files before they're committed. After you activate the virtual environment, run `pre-commit install` to set up the pre-commit script and `pre-commit run -a` to test it. If all was successful, you should see that `black` and `flake8` were run in the terminal. This step will help catch errors down the line **before** you commit.

## Running the Server

To actually start the server, make sure the virtual environment is activated.

Run `docker-compose up -d` in the root directory. This will start the mysql-server and phpmyadmin services. If that was successful, you should be able to visit http://localhost:8080 in your browser to see the phpmyadmin page. To stop the containers, run `docker-compose down`.

Run `python src/app.py` to start the server. By default this will run the server in production mode. If you want to start in debug mode, pass the `--debug` argument. You can also run `python src/app.py --reload` to start the server in auto-reload mode. This will restart the server whenever you make a change to a file. If you want to run the server using a different host or port, you can also optionally pass `--port [PORT]` or `--host [HOST]`.

For a full list of commands, run: `py src/app.py -h`


If you're on a Unix system, you can also start the server with `gunicorn -c gunicorn.conf.py`. This allows you to keep track of server logs and make use of gunicorn workers. Use `gunicorn -c gunicorn.conf.py --reload` to start the server in auto-reload mode. This won't work on Windows so if you're on a Windows system and want to test this, you'll need to set up [WSL](https://code.visualstudio.com/docs/remote/wsl).
