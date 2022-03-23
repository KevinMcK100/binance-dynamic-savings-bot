from binance_client import BinanceClient
from savings_evaluation import SavingsEvaluation
from telegram_notifier import TelegramNotifier
from threading import Thread
from time import sleep


class FailureHandler:
    """
    Binance documentation states:

    "The time frame for subscription and redemption is open from 00:10-23:50(UTC) every day."

    https://www.binance.com/en/support/faq/360034998492

    This means there is a 20 minute window around 00:00 UTC each day where we will be unable to purchase or redeem any assets from Binance Flexible Savings.
    This handler attempts to handle the occasions where this (or any other) error may occur.

    It works as follows:

     - Assets which failed to rebalance are added to the rebalance_failures set.
     - Handler will constantly monitor that set for presence of failed assets.
     - If there failures present, we wait until Binance indicates the assets are available for purchasing and redemption again before re-attempting.
     - Once assets are able to be purchased and redeemed again, the failure handler will clear down the existing failures and attempt to rebalance all savings assets.
    """

    ONE_MINUTE = 60

    def __init__(
        self, binance_client: BinanceClient, savings_evaluation: SavingsEvaluation, telegram_notifier: TelegramNotifier
    ):
        self.binance_client = binance_client
        self.savings_evaluation = savings_evaluation
        self.telegram_notifier = telegram_notifier
        failure_worker = Thread(target=self.monitor_failures)
        failure_worker.start()

    def monitor_failures(self):
        print("Start failure monitoring")
        while True:
            can_rebalance = False
            for failed_asset in self.savings_evaluation.rebalance_failures:
                # All assets must be available for purchasing and redemption before we attempt to rebalance
                can_purchase = self.binance_client.can_purchase_savings_asset(failed_asset)
                can_redeem = self.binance_client.can_redeem_savings_asset(failed_asset)
                if can_purchase and can_redeem:
                    print(f"Failed asset {failed_asset} is now available for purchasing and redemption again")
                    can_rebalance = True
                else:
                    print(
                        f"Failed asset {failed_asset} is still not available for purchasing and redemption. Will continue to monitor..."
                    )
                    can_rebalance = False
                    break
            if can_rebalance:
                print("Clearing failures and attempting to rebalance all symbols")
                self.telegram_notifier.enqueue_message("Starting retry...", is_verbose=True)
                self.savings_evaluation.rebalance_failures = set()
                self.savings_evaluation.rebalance_all_symbols()
            sleep(self.ONE_MINUTE)
