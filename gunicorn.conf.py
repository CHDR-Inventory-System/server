from os import path, getcwd, makedirs

# See https://docs.gunicorn.org/en/stable/settings.html
# for a complete list of configuration settings

# gunicorn needs to have its directory set to the src
# directory so that it knows where to locate app.py
chdir = "src/"

# Since gunicorn is in the src/ directory now, we need to look
# up a directory for the log folder
accesslog = "../logs/gunicorn_access.log"
errorlog = "../logs/gunicorn_error.log"
loglevel = "info"

# Ensures calls to Python's log functions get written to
# gunicorn's log directory
capture_output = True

bind = ["0.0.0.0:4565"]
wsgi_app = "app:app"
workers = 4
worker_class = "gevent"

# IMPORTANT: When gunicorn starts the application, the main process is forked
# into a bunch of individual processes. This causes the job scheduler to run
# extra times and also adds more connections to MySQL. In order to prevent this,
# we'll preload the application to tell gunicorn to load the entire application
# before forking the process: https://stackoverflow.com/a/40162246/9124220
preload_app = True

# If the logs directory doesn't exist, try to create it
try:
    current_dir = getcwd()
    log_directory = path.join(current_dir, "logs")
    makedirs(log_directory, exist_ok=True)
except Exception as err:
    print(
        f"""
        Error creating logs directory. Create a folder named 'logs'
        at the path {current_dir} before starting the server
        """,
        str(err),
    )
