from pyalgotrade import strategy
from pyalgotrade import plotter
from pyalgotrade.technical import bollinger
from pyalgotrade.stratanalyzer import sharpe
from pyalgotrade.utils import wind_feed
from WindPy import w
import copy
from pyalgotrade.technical import ma
from math import isnan

class turtle(strategy.BacktestingStrategy):
    def __init__(self, feed, instruments, bBandsPeriod, numStdDev, volTimesToBuy, volTimesToSell, sharesToBuyPerVol, DecreaseRate, bandsmaPeriod, bandwidthbreak, maxStkNum):
        strategy.BacktestingStrategy.__init__(self, feed)
        self.__instruments = instruments
        self.__numStdDev = numStdDev
        self.__volTimesToBuy = volTimesToBuy
        self.__volTimesToSell = volTimesToSell
        self.__sharesToBuyPerVol = sharesToBuyPerVol
        self.__DecreaseRate = DecreaseRate
        self.__bbands = {}
        self.__bandwidthsma = {}
        for instrument in instruments:
            self.__bbands[instrument] = bollinger.BollingerBands(feed[instrument].getCloseDataSeries(), bBandsPeriod, numStdDev)
            self.__bandwidthsma[instrument] = ma.SMA(self.__bbands[instrument].getBandWidth(), bandsmaPeriod)
        self.__lastprice = dict.fromkeys(instruments)
        self.__buytime = dict.fromkeys(instruments)
        self.__bandwidthbreak = bandwidthbreak
        self.__maxStkNum = maxStkNum
        self.__StkNum = 0
        
    def getBollingerBands(self, instrument):
        return self.__bbands[instrument]
    
    def onBars(self, bars):
        for instrument in self.__instruments:
            bar = bars[instrument]
            if bar.getDateTime().hour == 15:
                continue
            bband = self.getBollingerBands(instrument)
            lower = bband.getLowerBand()[-1]
            upper = bband.getUpperBand()[-1]
            vol = bband.getstdDev()[-1]
            width = bband.getBandWidth()[-1]
            sma = self.__bandwidthsma[instrument][-1]
            if lower is None or sma is None:
                continue
        
            shares = self.getBroker().getShares(instrument)
            price = bar.getClose()
            volume = bar.getVolume()
            if price is None or price == 0 or volume == 0 or volume is None or isnan(volume) or isnan(price):
                continue
            if shares == 0:
                if price > upper and self.__StkNum < self.__maxStkNum and width > sma * (1+self.__bandwidthbreak) and width > 0.001:
                    sharesToBuy = int(self.getBroker().getEquity()*self.__sharesToBuyPerVol/(price*self.__maxStkNum))
                    self.__buytime[instrument] = 1
                    self.__lastprice[instrument] = copy.deepcopy(price)
                    self.__StkNum += 1
                    self.marketOrder(instrument, sharesToBuy)
                    print bar.getDateTime(), "buy", instrument, self.__StkNum
            else:
                if price > self.__lastprice[instrument] + self.__volTimesToBuy * vol:
                    sharesToBuy = int(self.getBroker().getEquity()*self.__sharesToBuyPerVol*(self.__DecreaseRate**self.__buytime[instrument])/(price*self.__maxStkNum))
                    minShare = self.getBroker().getCash(False) / price
                    self.__buytime[instrument] += 1
                    self.__lastprice[instrument] = copy.deepcopy(price)
                    self.marketOrder(instrument, min(sharesToBuy,minShare))
                    print bar.getDateTime(), "add", instrument, self.__StkNum
                elif price < self.__lastprice[instrument] - self.__volTimesToSell * vol:
                    self.__buytime[instrument] = 0
                    self.__lastprice[instrument] = None
                    self.__StkNum -= 1
                    self.marketOrder(instrument, -1*shares)
                    print bar.getDateTime(), "sell", instrument, self.__StkNum
def main(plot):
    #instrument = "000300.SH"
    w.start()
    instruments = w.wset("IndexConstituent","date=20130101;windcode=000300.SH;field=wind_code").Data[0]
    #instruments.remove(instruments[29])
    bBandsPeriod, numStdDev = 40, 2
    volTimesToBuy, volTimesToSell, sharesToBuyPerVol, DecreaseRate = 0.5, 1.5, 0.4, 0.6
    maxStkNum, bandsmaPeriod, bandwidthbreak = 40, 15, 0.15
    
    feed = wind_feed.build_feed(instruments, None, "2013/01/01", "2013/12/31")
    strat = turtle(feed, instruments, bBandsPeriod, numStdDev, volTimesToBuy, volTimesToSell, sharesToBuyPerVol, DecreaseRate, bandsmaPeriod, bandwidthbreak, maxStkNum)
    sharpeRatioAnalyzer = sharpe.SharpeRatio()
    strat.attachAnalyzer(sharpeRatioAnalyzer)
    
    if plot:
        plt = plotter.StrategyPlotter(strat, False, False, True)
        #plt.getInstrumentSubplot(instrument).addDataSeries("upper", strat.getBollingerBands().getUpperBand())
        #plt.getInstrumentSubplot(instrument).addDataSeries("middle", strat.getBollingerBands().getMiddleBand())
        #plt.getInstrumentSubplot(instrument).addDataSeries("lower", strat.getBollingerBands().getLowerBand())

    strat.run()
    print "Sharpe ratio: %.2f" % sharpeRatioAnalyzer.getSharpeRatio(0.05)

    if plot:
        plt.plot()


if __name__ == "__main__":
    main(True)

            
        