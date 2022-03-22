import pandas as pd


class AssetsDataframe:

    SYMBOL_COLUMN = "symbol"
    NEXT_SO_COLUMN = "next_so"
    QUOTE_ASSET_COLUMN = "quote_asset"

    def __init__(self):
        self.df = pd.DataFrame(columns=[self.SYMBOL_COLUMN, self.NEXT_SO_COLUMN, self.QUOTE_ASSET_COLUMN])
        self.df = self.df.set_index([self.SYMBOL_COLUMN])

    def upsert(self, symbol, next_so, quote_asset):
        self.df.loc[symbol, [self.NEXT_SO_COLUMN, self.QUOTE_ASSET_COLUMN]] = [next_so, quote_asset]

    def drop_by_quote_asset(self, quote_asset):
        self.df = self.df[self.df.quote_asset != quote_asset]

    def sum_next_orders(self, quote_asset):
        return self.df.loc[self.df.quote_asset == quote_asset, self.NEXT_SO_COLUMN].sum()

    def max_next_orders(self, quote_asset):
        return self.df.loc[self.df.quote_asset == quote_asset, self.NEXT_SO_COLUMN].max()

    def print_df(self):
        print(f"Assets Dataframe\n {self.df}")
