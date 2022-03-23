from rebalance_savings_scheduler import RebalanceSavingsScheduler
from savings_evaluation import SavingsEvaluation
from telegram.ext import Updater, CommandHandler
from telegram_notifier import TelegramNotifier


class TelegramHandler:
    def __init__(
        self,
        api_key,
        telegram_notifier: TelegramNotifier,
        savings_evaluation: SavingsEvaluation,
        rebalance_savings_scheduler: RebalanceSavingsScheduler,
    ):
        self.telegram_notifier = telegram_notifier
        self.savings_evaluation = savings_evaluation
        self.rebalance_savings_scheduler = rebalance_savings_scheduler
        self.start_telegram_bot(api_key)
        self.bot_started = False

    def start_telegram_bot(self, api_key):
        # """Initialise Telegram bot."""
        self.updater = Updater(
            api_key,
            use_context=True,
            request_kwargs={"connect_timeout": 10, "read_timeout": 20},
        )

        # Add command handlers
        dp = self.updater.dispatcher
        dp.add_handler(CommandHandler("start", self.__start))  # /start
        dp.add_handler(CommandHandler("reevaluate", self.__reevaluate))  # /reevaluate
        dp.add_handler(CommandHandler("scheduler", self.__scheduler))  # /scheduler

        # Start the Telegram Bot
        self.updater.start_polling()

    def run_telegram_bot(self):
        """
        Blocking call. Signals only work in main thread so this must be the final call called in from main after setup is complete
        """
        self.updater.idle()

    def __start(self, update, context):
        """
        Starts the bot. Executes on /start command
        """
        if not self.bot_started:
            self.telegram_notifier.start_notifier(context)
            self.telegram_notifier.enqueue_message("Binance Dynamic Savings Bot started successfully")
            self.rebalance_savings_scheduler.start_scheduler()
            self.rebalance_savings_scheduler.send_scheduler_summary()
            self.bot_started = True
        else:
            self.telegram_notifier.enqueue_message("Bot is already started. Execute /help for more commands")

    def __reevaluate(self, update, context):
        """
        Reevaluates all assets and redistributes quote assets between Flexible Savings and Spot Wallet. Executes on /reevaluate command
        """
        if self.bot_started:
            self.telegram_notifier.enqueue_message("Reevaluating all quote assets")
            self.savings_evaluation.reevaluate_all_symbols()
        else:
            print("Bot is not started. Execute /start command from Telegram")

    def __scheduler(self, update, context):
        next_run_info = self.rebalance_savings_scheduler.send_scheduler_summary()
        self.telegram_notifier.enqueue_message(next_run_info)
