# CHDR Inventory System - Server

## Getting Started

Before you start, make sure you have Python 3 and the [virtualenv](https://packaging.python.org/guides/installing-using-pip-and-virtual-environments/) package installed.

This project also relies on the [mysqlclient](https://github.com/PyMySQL/mysqlclient#install) package which requires additional packages to be installed.

* Run `python3 -m venv ./venv` in the root directory to create a virtual environment.
* Run `source ./venv/bin/activate` on macOS/Linux or `.\env\Scripts\activate` on Windows to activate the virtual environment
* Run `pip install -r requirements.txt` to install the required dependencies.
* Run `python3 src/app.py` to start the server
    * Additionally, you can also run `python3 src/app.py --debug` to start the server in debug mode
