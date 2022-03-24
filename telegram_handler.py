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
        dry_run: bool = False,
    ):
        self.telegram_notifier = telegram_notifier
        self.savings_evaluation = savings_evaluation
        self.rebalance_savings_scheduler = rebalance_savings_scheduler
        self.dry_run = dry_run
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
        dp.add_handler(CommandHandler("rebalance", self.__rebalance))  # /rebalance
        dp.add_handler(CommandHandler("scheduler", self.__scheduler))  # /scheduler
        dp.add_handler(CommandHandler("test", self.__test))  # /test

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
            if self.dry_run:
                self.telegram_notifier.enqueue_message(
                    "Running in dry-run mode. Will not move any assets between spot and savings"
                )
        else:
            self.telegram_notifier.enqueue_message("Bot is already started. Execute /help for more commands")

    def __rebalance(self, update, context):
        """
        Reevaluates all assets and redistributes quote assets between Flexible Savings and Spot Wallet. Executes on /reevaluate command
        """
        if self.bot_started:
            self.savings_evaluation.rebalance_all_symbols()
        else:
            print("Bot is not started. Execute /start command from Telegram")

    def __scheduler(self, update, context):
        if self.bot_started:
            next_run_info = self.rebalance_savings_scheduler.send_scheduler_summary()
            self.telegram_notifier.enqueue_message(next_run_info)
        else:
            print("Bot is not started. Execute /start command from Telegram")

    def __test(self, update, context):
        self.savings_evaluation.reevaluate_symbol("MATICUSDT")
