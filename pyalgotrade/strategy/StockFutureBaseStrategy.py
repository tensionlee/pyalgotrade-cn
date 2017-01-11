# PyAlgoTrade
#
# Copyright 2017-2018 Li Taicheng
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
.. moduleauthor:: Li Taicheng <tensionlee@aliyun.com>
"""

import abc
import logging

from pyalgotrade import strategy
import pyalgotrade.broker
from pyalgotrade.broker import backtesting
from pyalgotrade import observer
from pyalgotrade import dispatcher
import pyalgotrade.strategy.position
from pyalgotrade import logger
from pyalgotrade.barfeed import resampled

LOGGER_NAME = "strategy"


class StockFutureBaseStrategy(object):
    """Base class for backtesting strategies supporting stock and future at the same time"""

    def __init__(self, barFeed, stockCash=1000000, futureCash=1000000):
        if isinstance(stockCash, pyalgotrade.broker.Broker):
            stockBroker = stockCash
        else:
            stockBroker = backtesting.Broker(stockCash, barFeed)

        if isinstance(futureCash, pyalgotrade.broker.Broker):
            futureBroker = futureCash
        else:
            futureBroker = backtesting.Broker(futureCash, barFeed)

        self.__useAdjustedValues = False
        self.setUseEventDateTimeInLogs(True)
        self.setDebugMode(True)

        self.futureTypes = ['IF', 'IC', 'IH']
        self.futureMutiplier = {'IF': 300, 'IC': 200, 'IH': 300}
        self.futureMarginRate = {'IF': 1, 'IC': 1, 'IH': 1}

        # To support stock and future at the same time, the following is to replace BackStrategy.__init__(...)
        self.__barFeed = barFeed
        self.__stockBroker = stockBroker
        self.__futureBroker = futureBroker
        self.__activePositions = set()
        self.__orderToPosition = {}
        self.__barsProcessedEvent = observer.Event()
        self.__analyzers = []
        self.__namedAnalyzers = {}
        self.__resampledBarFeeds = []
        self.__dispatcher = dispatcher.Dispatcher()
        self.__stockBroker.getOrderUpdatedEvent().subscribe(self.__onOrderEvent)
        self.__futureBroker.getOrderUpdatedEvent().subscribe(self.__onOrderEvent)
        self.__barFeed.getNewValuesEvent().subscribe(self.__onBars)

        self.__dispatcher.getStartEvent().subscribe(self.onStart)
        self.__dispatcher.getIdleEvent().subscribe(self.__onIdle)

        # It is important to dispatch broker events before feed events, specially if we're backtesting.
        self.__dispatcher.addSubject(self.__stockBroker)
        self.__dispatcher.addSubject(self.__futureBroker)
        self.__dispatcher.addSubject(self.__barFeed)

        # Initialize logging.
        self.__logger = logger.getLogger(LOGGER_NAME)

    def getUseAdjustedValues(self):
        return self.__useAdjustedValues

    def setUseAdjustedValues(self, useAdjusted):
        self.getFeed().setUseAdjustedValues(useAdjusted)
        self.getStockBroker().setUseAdjustedValues(useAdjusted)
        self.getFutureBroker().setUseAdjustedValues(useAdjusted)
        self.__useAdjustedValues = useAdjusted

    def setDebugMode(self, debugOn):
        """Enable/disable debug level messages in the strategy and backtesting broker.
        This is enabled by default."""
        level = logging.DEBUG if debugOn else logging.INFO
        self.getLogger().setLevel(level)
        self.getStockBroker().getLogger().setLevel(level)
        self.getFutureBroker().getLogger().setLevel(level)

    # To support stock and future at the same time, the following is to replace BackStrategy
    def getStockBroker(self):
        return self.__stockBroker

    def getFutureBroker(self):
        return self.__futureBroker

    def _setStockBroker(self, stockBroker):
        self.__stockBroker = stockBroker

    def _setFutureBroker(self, futureBroker):
        self.__futureBroker = futureBroker

    def getLogger(self):
        return self.__logger

    def getActivePositions(self):
        return self.__activePositions

    def getOrderToPosition(self):
        return self.__orderToPosition

    def getDispatcher(self):
        return self.__dispatcher

    # todo: need to refactor the equity() of future broker
    def getResult(self):
        return self.getStockBroker().getEquity() + self.getFutureBroker().getEquity()

    def getBarsProcessedEvent(self):
        return self.__barsProcessedEvent

    def getUseAdjustedValues(self):
        return False

    def registerPositionOrder(self, position, order):
        self.__activePositions.add(position)
        assert (order.isActive())  # Why register an inactive order ?
        self.__orderToPosition[order.getId()] = position

    def unregisterPositionOrder(self, position, order):
        del self.__orderToPosition[order.getId()]

    def unregisterPosition(self, position):
        assert (not position.isOpen())
        self.__activePositions.remove(position)

    def __notifyAnalyzers(self, lambdaExpression):
        for s in self.__analyzers:
            lambdaExpression(s)

    def attachAnalyzerEx(self, strategyAnalyzer, name=None):
        if strategyAnalyzer not in self.__analyzers:
            if name is not None:
                if name in self.__namedAnalyzers:
                    raise Exception("A different analyzer named '%s' was already attached" % name)
                self.__namedAnalyzers[name] = strategyAnalyzer

            strategyAnalyzer.beforeAttach(self)
            self.__analyzers.append(strategyAnalyzer)
            strategyAnalyzer.attached(self)

    def getLastPrice(self, instrument):
        ret = None
        bar = self.getFeed().getLastBar(instrument)
        if bar is not None:
            ret = bar.getPrice()
        return ret

    def getFeed(self):
        """Returns the :class:`pyalgotrade.barfeed.BaseBarFeed` that this strategy is using."""
        return self.__barFeed

    def getCurrentDateTime(self):
        """Returns the :class:`datetime.datetime` for the current :class:`pyalgotrade.bar.Bars`."""
        return self.__barFeed.getCurrentDateTime()

    def isFutureOrNot(self, instrument):
        # True - future, False - stock
        flag = False
        for key in self.futureTypes:
            if instrument.find(key):
                flag = True
                break
        return flag

    def getSuitableBroker(self, instrument):
        if self.isFutureOrNot(instrument):
            broker = self.getFutureBroker()
        else:
            broker = self.getStockBroker()

        return broker

    def marketOrder(self, instrument, quantity, onClose=False, goodTillCanceled=False, allOrNone=False):
        """Submits a market order.

        :param instrument: Instrument identifier.
        :type instrument: string.
        :param quantity: The amount of shares. Positive means buy, negative means sell.
        :type quantity: int/float.
        :param onClose: True if the order should be filled as close to the closing price as possible (Market-On-Close order). Default is False.
        :type onClose: boolean.
        :param goodTillCanceled: True if the order is good till canceled. If False then the order gets automatically canceled when the session closes.
        :type goodTillCanceled: boolean.
        :param allOrNone: True if the order should be completely filled or not at all.
        :type allOrNone: boolean.
        :rtype: The :class:`pyalgotrade.broker.MarketOrder` submitted.
        """

        if self.isFutureOrNot(instrument):
            broker = self.getFutureBroker()
        else:
            broker = self.getStockBroker()

        ret = None
        if quantity > 0:
            ret = broker.createMarketOrder(pyalgotrade.broker.Order.Action.BUY, instrument, quantity, onClose)
        elif quantity < 0:
            ret = broker.createMarketOrder(pyalgotrade.broker.Order.Action.SELL, instrument, quantity * -1, onClose)
        if ret:
            ret.setGoodTillCanceled(goodTillCanceled)
            ret.setAllOrNone(allOrNone)
            broker.submitOrder(ret)
        return ret
