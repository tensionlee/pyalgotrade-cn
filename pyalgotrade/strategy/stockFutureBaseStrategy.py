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
from pyalgotrade.broker.futureBroker import futureBroker as FutureBroker
from pyalgotrade.strategy import stockFuturePosition

LOGGER_NAME = "strategy"


class StockFutureBaseStrategy(object):
    """Base class for backtesting strategies supporting stock and future at the same time"""

    def __init__(self, barFeed, stockCash=1000000, futureCash=1000000, futureTypes=None, futureMultiplier= None, futureMarginRate=None):
        if isinstance(stockCash, pyalgotrade.broker.Broker):
            stockBroker = stockCash
        else:
            stockBroker = backtesting.Broker(stockCash, barFeed)

        if futureTypes is None:
            self.futureTypes = ['IF', 'IC', 'IH']
        else:
            self.futureTypes = futureTypes
        if futureMultiplier is None:
            self.futureMutiplier = {'IF': 300, 'IC': 200, 'IH': 300}
        else:
            self.futureMutiplier = futureMultiplier
        if futureMarginRate is None:
            self.futureMarginRate = {'IF': 0.1, 'IC': 0.1, 'IH': 0.1}
        else:
            self.futureMarginRate = futureMarginRate

        if isinstance(futureCash, pyalgotrade.broker.Broker):
            futureBroker = futureCash
        else:
            futureBroker = FutureBroker(futureCash, barFeed, self.futureTypes, self.futureMutiplier, self.futureMarginRate)

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

        self.__useAdjustedValues = False
        self.setUseEventDateTimeInLogs(True)
        self.setDebugMode(True)

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

    def setUseEventDateTimeInLogs(self, useEventDateTime):
        if useEventDateTime:
            logger.Formatter.DATETIME_HOOK = self.getDispatcher().getCurrentDateTime
        else:
            logger.Formatter.DATETIME_HOOK = None

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

    def limitOrder(self, instrument, limitPrice, quantity, goodTillCanceled=False, allOrNone=False):
        """Submits a limit order.

        :param instrument: Instrument identifier.
        :type instrument: string.
        :param limitPrice: Limit price.
        :type limitPrice: float.
        :param quantity: The amount of shares. Positive means buy, negative means sell.
        :type quantity: int/float.
        :param goodTillCanceled: True if the order is good till canceled. If False then the order gets automatically canceled when the session closes.
        :type goodTillCanceled: boolean.
        :param allOrNone: True if the order should be completely filled or not at all.
        :type allOrNone: boolean.
        :rtype: The :class:`pyalgotrade.broker.LimitOrder` submitted.
        """

        if self.isFutureOrNot(instrument):
            broker = self.getFutureBroker()
        else:
            broker = self.getStockBroker()

        ret = None
        if quantity > 0:
            ret = broker.createLimitOrder(pyalgotrade.broker.Order.Action.BUY, instrument, limitPrice, quantity)
        elif quantity < 0:
            ret = broker.createLimitOrder(pyalgotrade.broker.Order.Action.SELL, instrument, limitPrice, quantity*-1)
        if ret:
            ret.setGoodTillCanceled(goodTillCanceled)
            ret.setAllOrNone(allOrNone)
            broker.submitOrder(ret)
        return ret

    def stopOrder(self, instrument, stopPrice, quantity, goodTillCanceled=False, allOrNone=False):
        """Submits a stop order.

        :param instrument: Instrument identifier.
        :type instrument: string.
        :param stopPrice: Stop price.
        :type stopPrice: float.
        :param quantity: The amount of shares. Positive means buy, negative means sell.
        :type quantity: int/float.
        :param goodTillCanceled: True if the order is good till canceled. If False then the order gets automatically canceled when the session closes.
        :type goodTillCanceled: boolean.
        :param allOrNone: True if the order should be completely filled or not at all.
        :type allOrNone: boolean.
        :rtype: The :class:`pyalgotrade.broker.StopOrder` submitted.
        """

        if self.isFutureOrNot(instrument):
            broker = self.getFutureBroker()
        else:
            broker = self.getStockBroker()

        ret = None
        if quantity > 0:
            ret = broker.createStopOrder(pyalgotrade.broker.Order.Action.BUY, instrument, stopPrice, quantity)
        elif quantity < 0:
            ret = broker.createStopOrder(pyalgotrade.broker.Order.Action.SELL, instrument, stopPrice, quantity*-1)
        if ret:
            ret.setGoodTillCanceled(goodTillCanceled)
            ret.setAllOrNone(allOrNone)
            broker.submitOrder(ret)
        return ret

    def stopLimitOrder(self, instrument, stopPrice, limitPrice, quantity, goodTillCanceled=False, allOrNone=False):
        """Submits a stop limit order.

        :param instrument: Instrument identifier.
        :type instrument: string.
        :param stopPrice: Stop price.
        :type stopPrice: float.
        :param limitPrice: Limit price.
        :type limitPrice: float.
        :param quantity: The amount of shares. Positive means buy, negative means sell.
        :type quantity: int/float.
        :param goodTillCanceled: True if the order is good till canceled. If False then the order gets automatically canceled when the session closes.
        :type goodTillCanceled: boolean.
        :param allOrNone: True if the order should be completely filled or not at all.
        :type allOrNone: boolean.
        :rtype: The :class:`pyalgotrade.broker.StopLimitOrder` submitted.
        """
        if self.isFutureOrNot(instrument):
            broker = self.getFutureBroker()
        else:
            broker = self.getStockBroker()

        ret = None
        if quantity > 0:
            ret = broker.createStopLimitOrder(pyalgotrade.broker.Order.Action.BUY, instrument, stopPrice, limitPrice, quantity)
        elif quantity < 0:
            ret = broker.createStopLimitOrder(pyalgotrade.broker.Order.Action.SELL, instrument, stopPrice, limitPrice, quantity*-1)
        if ret:
            ret.setGoodTillCanceled(goodTillCanceled)
            ret.setAllOrNone(allOrNone)
            broker.submitOrder(ret)
        return ret

    def enterLong(self, instrument, quantity, goodTillCanceled=False, allOrNone=False):
        """Generates a buy :class:`pyalgotrade.broker.MarketOrder` to enter a long position.

        :param instrument: Instrument identifier.
        :type instrument: string.
        :param quantity: Entry order quantity.
        :type quantity: int.
        :param goodTillCanceled: True if the entry order is good till canceled. If False then the order gets automatically canceled when the session closes.
        :type goodTillCanceled: boolean.
        :param allOrNone: True if the orders should be completely filled or not at all.
        :type allOrNone: boolean.
        :rtype: The :class:`pyalgotrade.strategy.position.Position` entered.
        """

        return stockFuturePosition.LongPosition(self, instrument, None, None, quantity, goodTillCanceled, allOrNone)

    def enterShort(self, instrument, quantity, goodTillCanceled=False, allOrNone=False):
        """Generates a sell short :class:`pyalgotrade.broker.MarketOrder` to enter a short position.

        :param instrument: Instrument identifier.
        :type instrument: string.
        :param quantity: Entry order quantity.
        :type quantity: int.
        :param goodTillCanceled: True if the entry order is good till canceled. If False then the order gets automatically canceled when the session closes.
        :type goodTillCanceled: boolean.
        :param allOrNone: True if the orders should be completely filled or not at all.
        :type allOrNone: boolean.
        :rtype: The :class:`pyalgotrade.strategy.position.Position` entered.
        """

        return stockFuturePosition.ShortPosition(self, instrument, None, None, quantity, goodTillCanceled, allOrNone)

    def enterLongLimit(self, instrument, limitPrice, quantity, goodTillCanceled=False, allOrNone=False):
        """Generates a buy :class:`pyalgotrade.broker.LimitOrder` to enter a long position.

        :param instrument: Instrument identifier.
        :type instrument: string.
        :param limitPrice: Limit price.
        :type limitPrice: float.
        :param quantity: Entry order quantity.
        :type quantity: int.
        :param goodTillCanceled: True if the entry order is good till canceled. If False then the order gets automatically canceled when the session closes.
        :type goodTillCanceled: boolean.
        :param allOrNone: True if the orders should be completely filled or not at all.
        :type allOrNone: boolean.
        :rtype: The :class:`pyalgotrade.strategy.position.Position` entered.
        """

        return stockFuturePosition.LongPosition(self, instrument, None, limitPrice, quantity, goodTillCanceled, allOrNone)

    def enterShortLimit(self, instrument, limitPrice, quantity, goodTillCanceled=False, allOrNone=False):
        """Generates a sell short :class:`pyalgotrade.broker.LimitOrder` to enter a short position.

        :param instrument: Instrument identifier.
        :type instrument: string.
        :param limitPrice: Limit price.
        :type limitPrice: float.
        :param quantity: Entry order quantity.
        :type quantity: int.
        :param goodTillCanceled: True if the entry order is good till canceled. If False then the order gets automatically canceled when the session closes.
        :type goodTillCanceled: boolean.
        :param allOrNone: True if the orders should be completely filled or not at all.
        :type allOrNone: boolean.
        :rtype: The :class:`pyalgotrade.strategy.position.Position` entered.
        """

        return stockFuturePosition.ShortPosition(self, instrument, None, limitPrice, quantity, goodTillCanceled, allOrNone)

    def enterLongStop(self, instrument, stopPrice, quantity, goodTillCanceled=False, allOrNone=False):
        """Generates a buy :class:`pyalgotrade.broker.StopOrder` to enter a long position.

        :param instrument: Instrument identifier.
        :type instrument: string.
        :param stopPrice: Stop price.
        :type stopPrice: float.
        :param quantity: Entry order quantity.
        :type quantity: int.
        :param goodTillCanceled: True if the entry order is good till canceled. If False then the order gets automatically canceled when the session closes.
        :type goodTillCanceled: boolean.
        :param allOrNone: True if the orders should be completely filled or not at all.
        :type allOrNone: boolean.
        :rtype: The :class:`pyalgotrade.strategy.position.Position` entered.
        """

        return stockFuturePosition.LongPosition(self, instrument, stopPrice, None, quantity, goodTillCanceled, allOrNone)

    def enterShortStop(self, instrument, stopPrice, quantity, goodTillCanceled=False, allOrNone=False):
        """Generates a sell short :class:`pyalgotrade.broker.StopOrder` to enter a short position.

        :param instrument: Instrument identifier.
        :type instrument: string.
        :param stopPrice: Stop price.
        :type stopPrice: float.
        :param quantity: Entry order quantity.
        :type quantity: int.
        :param goodTillCanceled: True if the entry order is good till canceled. If False then the order gets automatically canceled when the session closes.
        :type goodTillCanceled: boolean.
        :param allOrNone: True if the orders should be completely filled or not at all.
        :type allOrNone: boolean.
        :rtype: The :class:`pyalgotrade.strategy.position.Position` entered.
        """

        return stockFuturePosition.ShortPosition(self, instrument, stopPrice, None, quantity, goodTillCanceled, allOrNone)

    def enterLongStopLimit(self, instrument, stopPrice, limitPrice, quantity, goodTillCanceled=False, allOrNone=False):
        """Generates a buy :class:`pyalgotrade.broker.StopLimitOrder` order to enter a long position.

        :param instrument: Instrument identifier.
        :type instrument: string.
        :param stopPrice: Stop price.
        :type stopPrice: float.
        :param limitPrice: Limit price.
        :type limitPrice: float.
        :param quantity: Entry order quantity.
        :type quantity: int.
        :param goodTillCanceled: True if the entry order is good till canceled. If False then the order gets automatically canceled when the session closes.
        :type goodTillCanceled: boolean.
        :param allOrNone: True if the orders should be completely filled or not at all.
        :type allOrNone: boolean.
        :rtype: The :class:`pyalgotrade.strategy.position.Position` entered.
        """

        return stockFuturePosition.LongPosition(self, instrument, stopPrice, limitPrice, quantity, goodTillCanceled, allOrNone)

    def enterShortStopLimit(self, instrument, stopPrice, limitPrice, quantity, goodTillCanceled=False, allOrNone=False):
        """Generates a sell short :class:`pyalgotrade.broker.StopLimitOrder` order to enter a short position.

        :param instrument: Instrument identifier.
        :type instrument: string.
        :param stopPrice: The Stop price.
        :type stopPrice: float.
        :param limitPrice: Limit price.
        :type limitPrice: float.
        :param quantity: Entry order quantity.
        :type quantity: int.
        :param goodTillCanceled: True if the entry order is good till canceled. If False then the order gets automatically canceled when the session closes.
        :type goodTillCanceled: boolean.
        :param allOrNone: True if the orders should be completely filled or not at all.
        :type allOrNone: boolean.
        :rtype: The :class:`pyalgotrade.strategy.position.Position` entered.
        """

        return stockFuturePosition.ShortPosition(self, instrument, stopPrice, limitPrice, quantity, goodTillCanceled, allOrNone)

    def onEnterOk(self, position):
        """Override (optional) to get notified when the order submitted to enter a position was filled. The default implementation is empty.

        :param position: A position returned by any of the enterLongXXX or enterShortXXX methods.
        :type position: :class:`pyalgotrade.strategy.position.Position`.
        """
        pass

    def onEnterCanceled(self, position):
        """Override (optional) to get notified when the order submitted to enter a position was canceled. The default implementation is empty.

        :param position: A position returned by any of the enterLongXXX or enterShortXXX methods.
        :type position: :class:`pyalgotrade.strategy.position.Position`.
        """
        pass

    # Called when the exit order for a position was filled.
    def onExitOk(self, position):
        """Override (optional) to get notified when the order submitted to exit a position was filled. The default implementation is empty.

        :param position: A position returned by any of the enterLongXXX or enterShortXXX methods.
        :type position: :class:`pyalgotrade.strategy.position.Position`.
        """
        pass

    # Called when the exit order for a position was canceled.
    def onExitCanceled(self, position):
        """Override (optional) to get notified when the order submitted to exit a position was canceled. The default implementation is empty.

        :param position: A position returned by any of the enterLongXXX or enterShortXXX methods.
        :type position: :class:`pyalgotrade.strategy.position.Position`.
        """
        pass

    """Base class for strategies. """
    def onStart(self):
        """Override (optional) to get notified when the strategy starts executing. The default implementation is empty. """
        pass

    def onFinish(self, bars):
        """Override (optional) to get notified when the strategy finished executing. The default implementation is empty.

        :param bars: The last bars processed.
        :type bars: :class:`pyalgotrade.bar.Bars`.
        """
        pass

    def onIdle(self):
        """Override (optional) to get notified when there are no events.

       .. note::
            In a pure backtesting scenario this will not be called.
        """
        pass

    @abc.abstractmethod
    def onBars(self, bars):
        """Override (**mandatory**) to get notified when new bars are available. The default implementation raises an Exception.

        **This is the method to override to enter your trading logic and enter/exit positions**.

        :param bars: The current bars.
        :type bars: :class:`pyalgotrade.bar.Bars`.
        """
        raise NotImplementedError()

    def onOrderUpdated(self, order):
        """Override (optional) to get notified when an order gets updated.

        :param order: The order updated.
        :type order: :class:`pyalgotrade.broker.Order`.
        """
        pass

    def __onIdle(self):
        # Force a resample check to avoid depending solely on the underlying
        # barfeed events.
        for resampledBarFeed in self.__resampledBarFeeds:
            resampledBarFeed.checkNow(self.getCurrentDateTime())

        self.onIdle()

    def __onOrderEvent(self, broker_, orderEvent):
        order = orderEvent.getOrder()
        self.onOrderUpdated(order)

        # Notify the position about the order event.
        pos = self.__orderToPosition.get(order.getId(), None)
        if pos is not None:
            # Unlink the order from the position if its not active anymore.
            if not order.isActive():
                self.unregisterPositionOrder(pos, order)

            pos.onOrderEvent(orderEvent)

    def __onBars(self, dateTime, bars):
        # THE ORDER HERE IS VERY IMPORTANT

        # 1: Let analyzers process bars.
        self.__notifyAnalyzers(lambda s: s.beforeOnBars(self, bars))

        if bars.isOpenBar():
            # 2.1: Check if future position explosion
            # 2.2: Filter current closing future deals in restricted tickers
            # 2.3: Let the strategy process current bars and submit orders. Note to check if the tickers are in the restricted tickers
            self.onBars(bars)
            # 2.4: If there's any closing future deal, close it.

        # 3: Notify that the bars were processed.
        self.__barsProcessedEvent.emit(self, bars)



    def run(self):
        """Call once (**and only once**) to run the strategy."""
        self.__dispatcher.run()

        if self.__barFeed.getCurrentBars() is not None:
            self.onFinish(self.__barFeed.getCurrentBars())
        else:
            raise Exception("Feed was empty")

    def stop(self):
        """Stops a running strategy."""
        self.__dispatcher.stop()

    def attachAnalyzer(self, strategyAnalyzer):
        """Adds a :class:`pyalgotrade.stratanalyzer.StrategyAnalyzer`."""
        self.attachAnalyzerEx(strategyAnalyzer)

    def getNamedAnalyzer(self, name):
        return self.__namedAnalyzers.get(name, None)

    def debug(self, msg):
        """Logs a message with level DEBUG on the strategy logger."""
        self.getLogger().debug(msg)

    def info(self, msg):
        """Logs a message with level INFO on the strategy logger."""
        self.getLogger().info(msg)

    def warning(self, msg):
        """Logs a message with level WARNING on the strategy logger."""
        self.getLogger().warning(msg)

    def error(self, msg):
        """Logs a message with level ERROR on the strategy logger."""
        self.getLogger().error(msg)

    def critical(self, msg):
        """Logs a message with level CRITICAL on the strategy logger."""
        self.getLogger().critical(msg)

    def resampleBarFeed(self, frequency, callback):
        """
        Builds a resampled barfeed that groups bars by a certain frequency.

        :param frequency: The grouping frequency in seconds. Must be > 0.
        :param callback: A function similar to onBars that will be called when new bars are available.
        :rtype: :class:`pyalgotrade.barfeed.BaseBarFeed`.
        """
        ret = resampled.ResampledBarFeed(self.getFeed(), frequency)
        ret.getNewValuesEvent().subscribe(callback)
        self.getDispatcher().addSubject(ret)
        self.__resampledBarFeeds.append(ret)
        return ret