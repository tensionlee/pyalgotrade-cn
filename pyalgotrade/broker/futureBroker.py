from pyalgotrade.broker import backtesting
from pyalgotrade.broker import Order
from pyalgotrade import broker
from pyalgotrade.broker.backtesting import Broker

class FuturePercentageCommission(backtesting.Commission):
    """A :class:`Commission` class that charges a percentage of the whole trade.

    :param percentage: The percentage to charge. 0.01 means 1%, and so on. It must be smaller than 1.
    :type percentage: float.
    """
    def __init__(self, percentage):
        super(FuturePercentageCommission, self).__init__()
        assert(percentage < 1)
        self.__percentage = percentage

    def calculate(self, order, price, quantity, multiplier):
        return price * quantity * self.__percentage * multiplier

class FutureShare(object):
    def __init__(self, instrument, longPosition=0, longMargin=0, shortPosition=0, shortMargin=0):
        self.instrument = instrument
        self.setFutureShare(longPosition, longMargin, shortPosition, shortMargin)

    def setFutureShare(self, longPosition=0, longMargin=0, shortPosition=0, shortMargin=0):
        self.longPosition = longPosition
        self.longMargin = longMargin
        self.shortPosition = shortPosition
        self.shortMargin = shortMargin

    def getInstrument(self):
        return self.instrument

    def getLongPosition(self):
        return self.longPosition

    def getLongMargin(self):
        return self.longMargin

    def getShortPosition(self):
        return self.shortPosition

    def getShortMargin(self):
        return self.shortMargin

    def __format__(self, *args, **kwargs):
        return "instrument is : " + str(self.getInstrument()) + "; long position is : " \
               + str(self.getLongPosition()) + "; short position is : " + str(self.getShortPosition()) + \
               ";\r\nlong margin is : " + str(self.getLongMargin()) + "; short margin is : " + str(self.getShortMargin())

import abc

class futureBroker(backtesting.Broker):
    __metaclass__ = abc.ABCMeta

    def __init__(self, cash, barFeed, futureTypes, futureMutiplier, futureMarginRate, commission=None):
        super(futureBroker, self).__init__(cash, barFeed, commission)
        # Broker(cash, barFeed, commission)

        self.futureTypes = futureTypes
        self.futureMutiplier = futureMutiplier
        self.futureMarginRate = futureMarginRate

    def getInstrumentType(self, instrument):
        return instrument[0:2]

    def commitOrderExecution(self, order, dateTime, fillInfo):
        price = fillInfo.getPrice()
        quantity = fillInfo.getQuantity()
        multiplier = self.futureMutiplier[self.getInstrumentType(order.getInstrument())]
        marginRate = self.futureMarginRate[self.getInstrumentType(order.getInstrument())]

        # cost = -price * quantity * multiplier * marginRate
        # assert (cost > 0)

        if order.getAction() == Order.Action.BUY:
            longPositionDelta = quantity
            margin = -price * quantity * multiplier * marginRate
            assert (margin < 0)
        elif order.getAction() == Order.Action.SELL_SHORT: # ?? shortPosition ?? eg:?-3-5?
            shortPositionDelta = -quantity
            margin = price * quantity * multiplier * marginRate
            assert (margin > 0)
        elif order.getAction() == Order.Action.SELL:
            longPositionDelta = -quantity
            margin = -price * quantity * multiplier * marginRate
            assert (margin < 0)
        elif order.getAction() == Order.Action.BUY_TO_COVER:  # ?? ??shortPosition???0
            shortPositionDelta = quantity
            margin = price * quantity * multiplier * marginRate
            assert (margin > 0)
        else:  # Unknown action
            assert (False)

        # todo : need to modify commission calculation logic
        commission = self.getCommission().calculate(order, price, quantity, multiplier)
        print "commission : ", commission
        resultingCash = self.getCash() + margin - commission

        # Check that we're ok on cash after the commission.
        if resultingCash >= 0 or self.getAllowNegativeCash():

            # Update the order before updating internal state since addExecutionInfo may raise.
            # addExecutionInfo should switch the order state.
            orderExecutionInfo = broker.OrderExecutionInfo(price, quantity, commission, dateTime)
            order.addExecutionInfo(orderExecutionInfo)

            # Commit the order execution.
            self.__cash = resultingCash

            if order.getInstrument() in self.getPositions().keys():
                futureShare = self.getShares(order.getInstrument())
            else:
                futureShare = FutureShare(order.getInstrument())

            updatedLongPosition = futureShare.getLongPosition()
            updatedShortPosition = futureShare.getShortPosition()
            if order.getAction() == Order.Action.BUY or order.getAction() == Order.Action.SELL:
                updatedLongPosition = order.getInstrumentTraits().roundQuantity(
                    futureShare.getLongPosition() + longPositionDelta)

            elif order.getAction() == Order.Action.SELL_SHORT or order.getAction() == Order.Action.BUY_TO_COVER:
                updatedShortPosition = order.getInstrumentTraits().roundQuantity(
                    futureShare.getShortPosition() + shortPositionDelta
                )

            if updatedLongPosition == 0 and updatedShortPosition == 0:
                del self.getPositions()[order.getInstrument()]
            else:
                updatedLongMargin = updatedLongPosition * multiplier * marginRate * price
                updatedShortMargin = updatedShortPosition * multiplier * marginRate * price
                futureShare.setFutureShare(updatedLongPosition, updatedLongMargin, updatedShortPosition, updatedShortMargin)
                self.getPositions()[order.getInstrument()] = futureShare

            # Let the strategy know that the order was filled.
            self.getFillStrategy().onOrderFilled(self, order)

            # Notify the order update
            if order.isFilled():
                self._unregisterOrder(order)
                self.notifyOrderEvent(broker.OrderEvent(order, broker.OrderEvent.Type.FILLED, orderExecutionInfo))
            elif order.isPartiallyFilled():
                self.notifyOrderEvent(
                    broker.OrderEvent(order, broker.OrderEvent.Type.PARTIALLY_FILLED, orderExecutionInfo)
                )
            else:
                assert (False)
        else:
            self.getLogger().debug("Not enough cash to fill %s order [%s] for %s share/s" % (
                order.getInstrument(),
                order.getId(),
                order.getRemaining()
            ))
