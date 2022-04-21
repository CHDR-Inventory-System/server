from flask_apscheduler import APScheduler
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_MISSED
import background_tasks.debug
import background_tasks.notification
from util.config import secrets


def on_job_missed(app, event):
    app.logger.error("Scheduled job was missed")

    if event.traceback:
        app.logger.error(str(event.traceback))


def init_scheduler(app):
    scheduler = APScheduler()
    scheduler.init_app(app)
    scheduler.add_listener(lambda event: on_job_missed(app, event), EVENT_JOB_MISSED)

    # flake8: noqa: E501
    # For a list a parameters you can pass to the scheduler when adding a job, see:
    # https://apscheduler.readthedocs.io/en/3.x/modules/schedulers/base.html#apscheduler.schedulers.base.BaseScheduler.add_job
    scheduler.add_job(
        func=lambda: background_tasks.notification.due_date_iterator(app),
        id="tick",
        name="tick",
        trigger="interval",
        hours=24,
        max_instances=1,
    )

    """
    scheduler.add_job(
        func=lambda:background_tasks.debug.tick(app),
        id="location",
        name="location",
        trigger="interval",
        seconds=60,
        max_instances=1,
    )
    """

    if secrets["SCHEDULER_ENABLED"]:
        app.logger.info("Scheduler initialized")
        scheduler.start()
