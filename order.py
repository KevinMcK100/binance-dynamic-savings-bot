from dataclasses import dataclass, field


@dataclass
class Order:
    symbol: str
    base_asset: str
    quote_asset: str
    price: float
    quantity: float
    order_id: str
    status: str
    side: str
    timestamp: int
    quote_qty: float = field(init=False)

    def __post_init__(self):
        self.quote_qty = float(self.price) * float(self.quantity)

    def get_deal_id(self) -> str:
        return self.order_id.split("_")[-2]

    def is_new_order(self) -> bool:
        return self.status == "NEW"

    def is_filled_order(self) -> bool:
        return self.status == "FILLED"

    def is_new_or_filled_order(self) -> bool:
        return self.status in ["NEW", "FILLED"]

    def is_buy_order(self) -> bool:
        return self.side == "BUY"

    def is_sell_order(self) -> bool:
        return self.side == "SELL"
