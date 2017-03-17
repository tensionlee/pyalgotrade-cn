from pyalgotrade import strategy
from pyalgotrade import plotter
from pyalgotrade.technical import bollinger
from pyalgotrade.stratanalyzer import sharpe
from pyalgotrade.utils import wind_feed
from WindPy import w
import copy

class turtle(strategy.BacktestingStrategy):
    def __init__(self, feed, instrument, bBandsPeriod=20, numStdDev=2, volTimesToBuy=0.5, volTimesToSell=2, sharesToBuyPerVol=0.4, DecreaseRate=0.6):
        strategy.BacktestingStrategy.__init__(self, feed)
        self.__instrument = instrument
        self.__numStdDev = numStdDev
        self.__volTimesToBuy = volTimesToBuy
        self.__volTimesToSell = volTimesToSell
        self.__sharesToBuyPerVol = sharesToBuyPerVol
        self.__DecreaseRate = DecreaseRate
        self.__bbands = bollinger.BollingerBands(feed[instrument].getCloseDataSeries(), bBandsPeriod, numStdDev)
        self.__lastprice = 0
        self.__buytime = 0 
        
    def getBollingerBands(self):
        return self.__bbands
    
    def onBars(self, bars):
        lower = self.getBollingerBands().getLowerBand()[-1]
        upper = self.getBollingerBands().getUpperBand()[-1]
        vol = self.getBollingerBands().getstdDev()[-1]
        if lower is None:
            return
        
        shares = self.getBroker().getShares(self.__instrument)
        if shares!=0:
            print shares
        bar = bars[self.__instrument]
        price = bar.getClose()
        if shares == 0:
            if  price > upper:
                sharesToBuy = int(self.getBroker().getEquity()*self.__sharesToBuyPerVol/price)
                self.__buytime = 1
                self.__lastprice = price
                self.marketOrder(self.__instrument, sharesToBuy)
        else:
            if price > self.__lastprice + self.__volTimesToBuy * vol:
                sharesToBuy = int(self.getBroker().getEquity()*self.__sharesToBuyPerVol*(self.__DecreaseRate**self.__buytime)/price)
                minShare = self.getBroker().getCash(False) / price
                self.__buytime += 1
                self.__lastprice = copy.deepcopy(price)
                self.marketOrder(self.__instrument, min(sharesToBuy,minShare))
            elif price < self.__lastprice - self.__volTimesToSell * vol:
                self.__buytime = 0
                self.__lastprice = 0
                self.marketOrder(self.__instrument, -1*shares)
        print shares
        print self.__lastprice
              
def main(plot):
    instrument = "000300.SH"
    bBandsPeriod, numStdDev = 20, 2
    volTimesToBuy, volTimesToSell, sharesToBuyPerVol, DecreaseRate = 0.5, 1.5, 0.4, 0.6
    
    w.start()
    feed = wind_feed.build_feed([instrument], None, "2011/01/01", "2016/12/31")
    strat = turtle(feed, instrument, bBandsPeriod, numStdDev, volTimesToBuy, volTimesToSell, sharesToBuyPerVol, DecreaseRate)
    sharpeRatioAnalyzer = sharpe.SharpeRatio()
    strat.attachAnalyzer(sharpeRatioAnalyzer)
    
    if plot:
        plt = plotter.StrategyPlotter(strat, True, True, True)
        plt.getInstrumentSubplot(instrument).addDataSeries("upper", strat.getBollingerBands().getUpperBand())
        plt.getInstrumentSubplot(instrument).addDataSeries("middle", strat.getBollingerBands().getMiddleBand())
        plt.getInstrumentSubplot(instrument).addDataSeries("lower", strat.getBollingerBands().getLowerBand())

    strat.run()
    print "Sharpe ratio: %.2f" % sharpeRatioAnalyzer.getSharpeRatio(0.05)

    if plot:
        plt.plot()


if __name__ == "__main__":
    main(True)

            
        