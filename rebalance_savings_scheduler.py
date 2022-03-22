import datetime as dt

from savings_evaluation import SavingsEvaluation
from scheduler import Scheduler


class RebalanceSavingsScheduler:

    UTC = dt.timezone.utc

    def __init__(self, savings_evaluation: SavingsEvaluation, schedule_hour: int, schedule_min: int):
        self.savings_evaluation = savings_evaluation
        self.schedule_hour = schedule_hour
        self.schedule_min = schedule_min
        self.job = None

    def start_scheduler(self):
        schedule = Scheduler(tzinfo=self.UTC)
        self.job = schedule.daily(
            dt.time(hour=self.schedule_hour, minute=self.schedule_min, tzinfo=self.UTC),
            self.savings_evaluation.reevaluate_all_symbols,
        )
        print(f"\n- - Started Rebalance Savings Scheduler - -\n\n{schedule}")

    def get_next_run_info(self) -> str:
        next_run_info = "Rebalancing scheduled job is not started!"
        if self.job is not None:
            time = self.job.datetime.strftime("%m/%d/%Y %H:%M:%S")
            zone = self.job.datetime.tzname()
            run_in = str(self.job.timedelta()).split(".")[0]
            next_run_info = f"Savings rebalance scheduled for {time} {zone}. Runs in {run_in} from now"
        return next_run_info
