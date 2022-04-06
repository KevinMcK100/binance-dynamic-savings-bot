from dataclasses import dataclass


@dataclass
class BalanceUpdate:
    asset: str
    balance_delta: float
    event_time: int
    clear_time: int
