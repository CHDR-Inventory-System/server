# See https://docs.gunicorn.org/en/stable/settings.html
# for a complete list of configuration settings

accesslog = "../logs/gunicorn_access.log"
errorlog = "../logs/gunicorn_error.log"
loglevel = "info"

# Ensures calls to Python's log functions get written to
# gunicorn's log directory
capture_output = True

# gunicorn needs to have its directory set to the src
# directory so that it knows where to locate app.py
chdir = "src/"

bind = ["0.0.0.0:4565"]
wsgi_app = "app:app"
workers = 4
