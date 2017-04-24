#coding: utf-8
from pyalgotrade import strategy
from pyalgotrade import plotter
from pyalgotrade.technical import bollinger
from pyalgotrade.stratanalyzer import sharpe
from pyalgotrade.utils import wind_feed
from pyalgotrade.stratanalyzer import drawdown
from pyalgotrade.broker import backtesting
from pyalgotrade.broker import slippage
from WindPy import w
import copy
from pyalgotrade.technical import ma
from math import isnan
import pandas as pd
import sys
reload(sys)
sys.setdefaultencoding('utf-8')

class turtle(strategy.BacktestingStrategy):
    def __init__(self, feed, instruments, bBandsPeriod, numStdDev, volTimesToBuy, volTimesToSell, sharesToBuyPerVol, SellShareIncrease, DecreaseRate_buy, DecreaseRate_sell, bandsmaPeriod, bandwidthbreak, maxStkNum, maxBandWidth, maPeriod, bullLevel):
        strategy.BacktestingStrategy.__init__(self, feed, backtesting.Broker(1000000, feed, backtesting.TradePercentage_asymm(0.0003, 0.0013)))
        self.getBroker().getFillStrategy().setSlippageModel(slippage.NormalSlippage())
        self.__instruments = instruments
        self.__numStdDev = numStdDev
        self.__volTimesToBuy = volTimesToBuy
        self.__volTimesToSell = volTimesToSell
        self.__sharesToBuyPerVol = sharesToBuyPerVol
        self.__SellShareIncrease = SellShareIncrease
        self.__buyDecreaseRate = DecreaseRate_buy
        self.__sellDecreaseRate = DecreaseRate_sell
        self.__maxBandWidth = maxBandWidth
        self.__bbands = {}
        self.__bandwidthsma = {}
        self.__pricesma = {}
        self.__instrumentnum = 0
        self.__bullLevel = bullLevel
        self.__preclose = dict.fromkeys(instruments)
        for instrument in instruments:
            self.__bbands[instrument] = bollinger.BollingerBands_AddBarVersion(feed[instrument].getCloseDataSeries(), bBandsPeriod, numStdDev)
            self.__bandwidthsma[instrument] = ma.SMA_AddBarVersion(self.__bbands[instrument].getBandWidth(), bandsmaPeriod)
            self.__pricesma[instrument] = ma.SMA_AddBarVersion(feed[instrument].getCloseDataSeries(), maPeriod)
            self.__instrumentnum += 1
        self.__lastprice = dict.fromkeys(instruments)
        self.__buytime = dict.fromkeys(instruments)
        self.__bandwidthbreak = bandwidthbreak
        self.__maxStkNum = maxStkNum
        self.__StkNum = 0
        self.__abovepercent = pd.Series(0, index = ['initial'])
        self.__orders = pd.DataFrame(columns = ["time", "direction", "instrument", "shares", "price", "equityLevel", "pnl"])
        self.__boll = pd.DataFrame(columns=["time","instrument","middle","upper","close"])
        
    def getBollingerBands(self, instrument):
        return self.__bbands[instrument]
    
    def marketSituation(self):
        return self.__abovepercent
    
    def onBars(self, bars):
        for instrument in self.__instruments:
            bar = bars[instrument]
            currentTime = bar.getDateTime()
            if currentTime.hour == 15:
                continue
            
            feed = self.getFeed()
            shares = self.getBroker().getShares(instrument)
            price_open = bar.getOpen()
            price_close = bar.getClose()
            bband = self.getBollingerBands(instrument)
            upper = bband.getUpperBand()[-1]
            width = bband.getBandWidth()[-1]
            sma = self.__bandwidthsma[instrument][-1]
            vol = bband.getStdDev()[-1]
            pricesma = self.__pricesma[instrument][-1]
            volume = bar.getVolume()
            orders = self.__orders
            cash = self.getBroker().getCash()
            equity = self.getBroker().getEquity()
            low = feed[instrument].getLowDataSeries()[-1]
            high = feed[instrument].getHighDataSeries()[-1]
            preclose = self.__preclose[instrument]
            
            middle = bband.getMiddleBand()[-1]
            self.__boll.loc[len(self.__boll)] = [currentTime, instrument, middle, upper, price_close]
             
            if pricesma is None:
                self.__preclose[instrument] = copy.deepcopy(price_close)
                continue
            if currentTime not in self.__abovepercent:
                self.__abovepercent[currentTime] = 0.0
            if price_close >= pricesma:
                self.__abovepercent[currentTime] = self.__abovepercent[currentTime]+1.0/self.__instrumentnum
            if sma is None or price_open is None or price_open == 0 or volume == 0 or volume is None or isnan(volume) or isnan(price_open):
                self.__preclose[instrument] = copy.deepcopy(price_close)
                continue
                                   
            if shares == 0:
                if (self.__abovepercent[-2] > self.__bullLevel and price_open > upper and self.__StkNum < self.__maxStkNum and width > sma * (1+self.__bandwidthbreak) and width > 0.001 and width < self.__maxBandWidth): 
                    if preclose is not None and low < preclose * 1.098:
                        sharesToBuy = int(equity*self.__sharesToBuyPerVol/(price_open*self.__maxStkNum))
                        self.__buytime[instrument] = 1
                        self.__lastprice[instrument] = copy.deepcopy(price_open)
                        self.__StkNum += 1
                        self.marketOrder(instrument, sharesToBuy)
                        orders.loc[len(orders)] = [currentTime, "buy", instrument, sharesToBuy, price_open, 1-cash/equity, equity]
            else:
                if price_open > self.__lastprice[instrument] + self.__volTimesToBuy*vol:
                    sharesToBuy = int(equity*self.__sharesToBuyPerVol*(self.__buyDecreaseRate**self.__buytime[instrument])/(price_open*self.__maxStkNum))
                    minShare = int(cash / price_open)
                    self.__buytime[instrument] += 1
                    self.__lastprice[instrument] = copy.deepcopy(price_open)
                    if preclose is not None and low < preclose * 1.098:
                        self.marketOrder(instrument, min(sharesToBuy,minShare))
                        orders.loc[len(orders)] = [currentTime, "add", instrument, min(sharesToBuy,minShare), price_open, 1-cash/equity, equity]
                elif price_open < self.__lastprice[instrument] - (self.__volTimesToSell+self.__SellShareIncrease*self.__sellDecreaseRate**self.__buytime[instrument]) * vol:
                    if preclose is not None and high > preclose / 1.098:
                        self.__buytime[instrument] = 0
                        self.__lastprice[instrument] = None
                        self.__StkNum -= 1
                        self.marketOrder(instrument, -1*shares)
                        orders.loc[len(orders)] = [currentTime, "sell", instrument, -1*shares, price_open, 1-cash/equity, equity]                     
            self.__preclose[instrument] = copy.deepcopy(price_close)
            
    def run(self):
        super(turtle,self).run()  
        self.__orders.to_csv(u'F:\学习资料\开源证券实习\\海归系统交易记录_1.csv')
        self.__boll.to_csv(u'F:\学习资料\开源证券实习\\testboll.csv')
        return
              
def main(plot):
    w.start()
    instruments = w.wset("IndexConstituent","date=20110101;windcode=000300.SH;field=wind_code").Data[0][0:1]
    bBandsPeriod, numStdDev, maPeriod, bullLevel = 26, 2, 40, 0.75
    volTimesToBuy, volTimesToSell, sharesToBuyPerVol, SellShareIncrease, DecreaseRate_buy, DecreaseRate_sell = 1, 0.8, 0.5, 0.5, 0.5, 0.8
    maxStkNum, bandsmaPeriod, bandwidthbreak, maxBandWidth = 3, 10, -1, 0.03
    
    feed = wind_feed.build_feed(instruments, None, "2011/01/01", "2016/12/31")
    strat = turtle(feed, instruments, bBandsPeriod, numStdDev, volTimesToBuy, volTimesToSell, sharesToBuyPerVol, SellShareIncrease, DecreaseRate_buy, DecreaseRate_sell, bandsmaPeriod, bandwidthbreak, maxStkNum, maxBandWidth, maPeriod, bullLevel)
    sharpeRatioAnalyzer = sharpe.SharpeRatio_AddBarVersion()
    strat.attachAnalyzer(sharpeRatioAnalyzer)
    drawDownAnalyzer = drawdown.DrawDown()
    strat.attachAnalyzer(drawDownAnalyzer)
    
    if plot:
        plt = plotter.StrategyPlotter(strat, False, False, True)
        
    strat.run()
    print "Sharpe ratio: %.2f" % sharpeRatioAnalyzer.getSharpeRatio(0)
    print "Maximum DrawDown: %.2f" % drawDownAnalyzer.getMaxDrawDown()

    if plot:
        plt.plot()


if __name__ == "__main__":
    main(True)

            
        