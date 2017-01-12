# -*- coding: utf-8 -*-
"""
Created on Thur Jan. 12 14:44:12 2017

@author: Litc
"""
import pyalgotrade.utils.wind_feed as wfeed
from pyalgotrade import strategy
from pyalgotrade.strategy.stockFutureBaseStrategy import StockFutureBaseStrategy


class MyStrategy(StockFutureBaseStrategy):
    def __init__(self, feed, instruments):
        StockFutureBaseStrategy.__init__(self, feed)
        self.__instruments = instruments

    def onBars(self, bars):
        for key in self.__instruments:
            bar = bars[key]
            # self.info("datetime - " + str(bar.getDateTime()))
            # self.info("instrument - " + key)
            # self.info("close - " + str(bar.getClose()) + "; adjclose - " + str(bar.getAdjClose()))
            # self.info(bar.getAmount())
            # self.info("------------------------------")
            order = self.marketOrder(key, -3)
            print order.getQuantity()
        print self.getCurrentDateTime(), self.getSuitableBroker(key).getPositions()

stockSec = '600030.SH'
futureSec = 'IF1702.CFE'
instruments = [futureSec]
start_time = '20161221'
end_time = '20170104'
feed = wfeed.build_feed(instruments, None, start_time, end_time)

# Evaluate the strategy with the feed's bars.
myStrategy = MyStrategy(feed, instruments)

# retAnalyzer = returns.Returns()
# myStrategy.attachAnalyzer(retAnalyzer)
# sharpeRatioAnalyzer = sharpe.SharpeRatio()
# myStrategy.attachAnalyzer(sharpeRatioAnalyzer)
# drawDownAnalyzer = drawdown.DrawDown()
# myStrategy.attachAnalyzer(drawDownAnalyzer)
# tradesAnalyzer = trades.Trades()
# myStrategy.attachAnalyzer(tradesAnalyzer)

# plt = plotter.StrategyPlotter(myStrategy, True, True, True)
myStrategy.run()

# plt.plot()