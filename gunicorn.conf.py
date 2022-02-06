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

# If the logs directory doesn't exist, create it
current_dir = getcwd()
log_directory = path.join(current_dir, "logs")
makedirs(log_directory, exist_ok=True)
