import logging, pytz
import datetime as dt
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.job import Job
from savings_evaluation import SavingsEvaluation
from telegram_notifier import TelegramNotifier


class RebalanceSavingsScheduler:
    def __init__(
        self,
        savings_evaluation: SavingsEvaluation,
        telegram_notifier: TelegramNotifier,
        schedule_hour: int,
        schedule_min: int,
    ):
        self.savings_evaluation = savings_evaluation
        self.telegram_notifier = telegram_notifier
        self.schedule_hour = schedule_hour
        self.schedule_min = schedule_min
        self.job = None

    def start_scheduler(self):
        self.scheduler = BackgroundScheduler(timezone=pytz.utc)
        self.job = self.scheduler.add_job(
            self.savings_evaluation.rebalance_all_symbols, "cron", hour=self.schedule_hour, minute=self.schedule_min
        )
        self.scheduler.start()
        logging.info("Started Rebalance Savings Scheduler")

    def send_scheduler_summary(self) -> str:
        job_messages = ["Rebalancing scheduled job is not started!"]
        job: Job
        for job in self.scheduler.get_jobs():
            if job is not None:
                job_messages = []
                time = str(job.next_run_time).split("+")[0]
                zone = self.scheduler.timezone.zone
                next_run = job.next_run_time
                now = dt.datetime.now(tz=pytz.utc)
                delta = next_run - now
                fmt_delta = str(delta).split(".")[0]
                job_messages.append(f"Savings rebalance scheduled for {time} {zone}.\n\nRuns in {fmt_delta} from now")
                logging.info(f"Job summary: {job}")
        [self.telegram_notifier.enqueue_message(msg) for msg in job_messages]
