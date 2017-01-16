# -*- coding: utf-8 -*-
"""
Created on Thur Jan. 12 14:44:12 2017

@author: Litc
"""
import pyalgotrade.utils.wind_feed as wfeed
from WindPy import w
if not w.isconnected():
    w.start()
from pyalgotrade import strategy
from pyalgotrade.strategy.stockFutureBaseStrategy import StockFutureBaseStrategy
from pyalgotrade.broker.futureBroker import FuturePercentageCommission


class MyStrategy(StockFutureBaseStrategy):
    def __init__(self, feed, instruments):
        commissionStrategy = FuturePercentageCommission(0.0003)
        StockFutureBaseStrategy.__init__(self, feed)
        self.__instruments = instruments
        self.__position = {}
        self.getFutureBroker().setCommission(commissionStrategy)

    def onBars(self, bars):
        print "============================================="
        print self.getCurrentDateTime(), self.__instruments
        # print self.getSuitableBroker("IF1702.CFE").getPositions()
        for key in self.__instruments:
            futureShare = self.getSuitableBroker(key).getPositions().get(key)
            print self.getFutureBroker().getCash()
            print futureShare.__format__("")

            if key not in self.__position.keys():
                self.__position[key] = self.enterShort(key, 1)
            else:
                self.__position[key].exitMarket()
                del self.__position[key]

stockSec = '600030.SH'
futureSec = w.wsd("IF.CFE","trade_hiscode","2017-01-10", "2017-01-10").Data[0][0]
instruments = [futureSec]
start_time =  '2017-01-03'
end_time = '2017-01-05'
feed = wfeed.build_feed(instruments, None, start_time, end_time, frequency=60)

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