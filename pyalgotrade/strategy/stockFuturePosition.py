from pyalgotrade.strategy.position import Position
from pyalgotrade import broker

# This class is reponsible for order management in long positions.
class LongPosition(Position):
    def __init__(self, strategy, instrument, stopPrice, limitPrice, quantity, goodTillCanceled, allOrNone):
        suitableBroker = strategy.getSuitableBroker(instrument)
        if limitPrice is None and stopPrice is None:
            entryOrder = suitableBroker.createMarketOrder(broker.Order.Action.BUY, instrument, quantity, False)
        elif limitPrice is not None and stopPrice is None:
            entryOrder = suitableBroker.createLimitOrder(broker.Order.Action.BUY, instrument, limitPrice, quantity)
        elif limitPrice is None and stopPrice is not None:
            entryOrder = suitableBroker.createStopOrder(broker.Order.Action.BUY, instrument, stopPrice, quantity)
        elif limitPrice is not None and stopPrice is not None:
            entryOrder = suitableBroker.createStopLimitOrder(broker.Order.Action.BUY, instrument, stopPrice, limitPrice, quantity)
        else:
            assert(False)

        super(LongPosition, self).__init__(strategy, entryOrder, goodTillCanceled, allOrNone)

    def buildExitOrder(self, stopPrice, limitPrice):
        quantity = self.getShares()
        assert(quantity > 0)

        suitableBroker = self.getStrategy().getSuitableBroker(self.getInstrument())

        if limitPrice is None and stopPrice is None:
            ret = suitableBroker.createMarketOrder(broker.Order.Action.SELL, self.getInstrument(), quantity, False)
        elif limitPrice is not None and stopPrice is None:
            ret = suitableBroker.createLimitOrder(broker.Order.Action.SELL, self.getInstrument(), limitPrice, quantity)
        elif limitPrice is None and stopPrice is not None:
            ret = suitableBroker.createStopOrder(broker.Order.Action.SELL, self.getInstrument(), stopPrice, quantity)
        elif limitPrice is not None and stopPrice is not None:
            ret = suitableBroker.createStopLimitOrder(broker.Order.Action.SELL, self.getInstrument(), stopPrice, limitPrice, quantity)
        else:
            assert(False)

        return ret


# This class is reponsible for order management in short positions.
class ShortPosition(Position):
    def __init__(self, strategy, instrument, stopPrice, limitPrice, quantity, goodTillCanceled, allOrNone):
        suitableBroker = strategy.getSuitableBroker(instrument)
        if limitPrice is None and stopPrice is None:
            entryOrder = suitableBroker.createMarketOrder(broker.Order.Action.SELL_SHORT, instrument, quantity, False)
        elif limitPrice is not None and stopPrice is None:
            entryOrder = suitableBroker.createLimitOrder(broker.Order.Action.SELL_SHORT, instrument, limitPrice, quantity)
        elif limitPrice is None and stopPrice is not None:
            entryOrder = suitableBroker.createStopOrder(broker.Order.Action.SELL_SHORT, instrument, stopPrice, quantity)
        elif limitPrice is not None and stopPrice is not None:
            entryOrder = suitableBroker.createStopLimitOrder(broker.Order.Action.SELL_SHORT, instrument, stopPrice, limitPrice, quantity)
        else:
            assert(False)

        super(ShortPosition, self).__init__(strategy, entryOrder, goodTillCanceled, allOrNone)

    def buildExitOrder(self, stopPrice, limitPrice):
        quantity = self.getShares() * -1
        assert(quantity > 0)

        suitableBroker = self.getStrategy().getSuitableBroker(self.getInstrument())

        if limitPrice is None and stopPrice is None:
            ret = suitableBroker.createMarketOrder(broker.Order.Action.BUY_TO_COVER, self.getInstrument(), quantity, False)
        elif limitPrice is not None and stopPrice is None:
            ret = suitableBroker.createLimitOrder(broker.Order.Action.BUY_TO_COVER, self.getInstrument(), limitPrice, quantity)
        elif limitPrice is None and stopPrice is not None:
            ret = suitableBroker.createStopOrder(broker.Order.Action.BUY_TO_COVER, self.getInstrument(), stopPrice, quantity)
        elif limitPrice is not None and stopPrice is not None:
            ret = suitableBroker.createStopLimitOrder(broker.Order.Action.BUY_TO_COVER, self.getInstrument(), stopPrice, limitPrice, quantity)
        else:
            assert(False)

        return ret