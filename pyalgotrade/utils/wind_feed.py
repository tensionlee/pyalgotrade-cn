# coding=utf8
import pyalgotrade.logger
from pyalgotrade.barfeed import csvfeed
from pyalgotrade.utils import bar
from pyalgotrade import dataseries

from WindPy import w
from wind_tool import query_wind
import pytz
import datetime
from pyalgotrade.utils import dt
import math

######################################################################
## NinjaTrader CSV parser
# Each bar must be on its own line and fields must be separated by semicolon (;).
#
# Minute Bars Format:
# yyyyMMdd HHmmss;open price;high price;low price;close price;volume
#
# Daily Bars Format:
# yyyyMMdd;open price;high price;low price;close price;volume
#
# The exported data will be in the UTC time zone.

class Frequency(object):
    MINUTE = pyalgotrade.bar.Frequency.MINUTE
    DAILY = pyalgotrade.bar.Frequency.DAY
    MINUTE_15 = pyalgotrade.bar.Frequency.MINUTE_15
    MINUTE_5 = pyalgotrade.bar.Frequency.MINUTE_5
    HOUR = pyalgotrade.bar.Frequency.HOUR


# China Equities Regular Trading Hours filter
# Monday ~ Friday
# 9:30 ~ 15 (GMT-5)
class ShanghaiEquitiesRTH(csvfeed.DateRangeFilter):
    timezone = pytz.timezone("Asia/Shanghai")

    def __init__(self, fromDate=None, toDate=None):
        super(ShanghaiEquitiesRTH, self).__init__(fromDate, toDate)

        self.__fromTime = datetime.time(9, 30, 0)
        self.__toTime = datetime.time(15, 00, 0)

    def includeBar(self, bar_):
        ret = super(ShanghaiEquitiesRTH, self).includeBar(bar_)
        if ret:
            # Check bar data validation
            close = bar_.getClose()
            if math.isnan(close):
                return False

            # Check day of week
            barDay = bar_.getDateTime().weekday()
            if barDay > 4:
                return False

            # Check time
            barTime = dt.localize(bar_.getDateTime(), ShanghaiEquitiesRTH.timezone).time()
            if barTime < self.__fromTime:
                return False
            if barTime > self.__toTime:
                return False
        return ret


def build_feed(instruments, fields=None, fromDate=None, toDate=None, frequency=bar.Frequency.DAY, timezone=None,
               skipErrors=False):
    """
    :param fields: wind func parameter, eg:'open,high,low,close,volume,amt'
    """
    ret = Feed(frequency, timezone)
    if frequency == bar.Frequency.MINUTE:
        ret.setBarFilter(ShanghaiEquitiesRTH())
    if fields is None:
        fields = 'open,high,low,close,volume,amt'

    for instrument in instruments:
        try:
            if frequency == bar.Frequency.DAY:
                w_df = query_wind(w.wsd, instrument, fields, fromDate, toDate, "Period=D;PriceAdj=F")
            elif frequency == bar.Frequency.MINUTE:
                w_df = query_wind(w.wsi, instrument, fields, fromDate, toDate, "Period=M;PriceAdj=F")
            elif frequency == bar.Frequency.WEEK:
                w_df = query_wind(w.wsd, instrument, fields, fromDate, toDate, "Period=W;PriceAdj=F")
            else:
                raise Exception("Invalid frequency")
        except Exception, e:
            if skipErrors:
                ret.getLogger().error(str(e))
                continue
            else:
                raise e
        ret.addBarsFromDataFrame(instrument, w_df, frequency)
    return ret


class Feed(csvfeed.BarFeed):
    """A :class:`pyalgotrade.barfeed.csvfeed.BarFeed` that loads bars from CSV files exported from NinjaTrader.
    :param frequency: The frequency of the bars. Only **pyalgotrade.bar.Frequency.MINUTE** or **pyalgotrade.bar.Frequency.DAY**
        are supported.
    :param timezone: The default timezone to use to localize bars. Check :mod:`pyalgotrade.marketsession`.
    :type timezone: A pytz timezone.
    :param maxLen: The maximum number of values that the :class:`pyalgotrade.dataseries.bards.BarDataSeries` will hold.
        Once a bounded length is full, when new items are added, a corresponding number of items are discarded from the
        opposite end. If None then dataseries.DEFAULT_MAX_LEN is used.
    :type maxLen: int.
    """

    def __init__(self, frequency, timezone=None, maxLen=dataseries.DEFAULT_MAX_LEN):
        if isinstance(timezone, int):
            raise Exception(
                "timezone as an int parameter is not supported anymore. Please use a pytz timezone instead.")

        if frequency not in [bar.Frequency.MINUTE, bar.Frequency.DAY, bar.Frequency.WEEK]:
            raise Exception("Invalid frequency.")

        csvfeed.BarFeed.__init__(self, frequency, maxLen)
        # super(Feed, self).__init__(frequency, maxLen)
        self.__timezone = timezone
        self.__sanitizeBars = False
        self.__frequency = frequency
        self.__logger = pyalgotrade.logger.getLogger("wind")

    def getFrequency(self):
        return self.__frequency

    def isOpenBar(self):
        if self.getFrequency() != bar.Frequency.DAY:
            return True
        if self.getCurrentDateTime().hour == 0:
            return True
        return False

    def isCloseBar(self):
        if self.getFrequency() != bar.Frequency.DAY:
            return True
        if self.getCurrentDateTime().hour == 15:
            return True
        return False

    def sanitizeBars(self, sanitize):
        self.__sanitizeBars = sanitize

    def barsHaveAdjClose(self):
        return True

    def getLogger(self):
        return self.__logger

    def addBarsFromDataFrame(self, instrument, w_df, frequency):
        loadedBars = []
        for _, row in w_df.iterrows():
            tmp_extra = {}
            if frequency in [bar.Frequency.DAY, bar.Frequency.WEEK]:
                for key in row.keys():
                    if key not in ['index', 'OPEN', 'HIGH', 'LOW', 'CLOSE', 'VOLUME', 'AMT']:
                        tmp_extra[key] = row[key]
                bar_open = bar.BasicBar(_, row['OPEN'], row['HIGH'], row['LOW'], row['CLOSE'], row['VOLUME'], row['AMT'],
                                    row['CLOSE'], self.getFrequency(), tmp_extra)
                close_time = _ + datetime.timedelta(hours=15)
                bar_close = bar.BasicBar(close_time, row['OPEN'], row['HIGH'], row['LOW'], row['CLOSE'], row['VOLUME'], row['AMT'],
                                    row['CLOSE'], self.getFrequency(), tmp_extra)
                if bar_open is not None and (self.getBarFilter() is None or self.getBarFilter().includeBar(bar_open)):
                    loadedBars.append(bar_open)
                if bar_close is not None and (self.getBarFilter() is None or self.getBarFilter().includeBar(bar_close)):
                    loadedBars.append(bar_close)

            if frequency in [bar.Frequency.MINUTE]:
                for key in row.keys():
                    if key not in ['index', 'open', 'high', 'low', 'close', 'volume', 'amount']:
                        tmp_extra[key] = row[key]
                bar_ = bar.BasicBar(_, row['open'], row['high'], row['low'], row['close'], row['volume'], row['amount'],
                                    row['close'], self.getFrequency(), tmp_extra)
                if bar_ is not None and (self.getBarFilter() is None or self.getBarFilter().includeBar(bar_)):
                    loadedBars.append(bar_)

        self.addBarsFromSequence(instrument, loadedBars)
