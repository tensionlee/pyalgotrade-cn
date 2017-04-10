#coding: utf-8
from pyalgotrade import strategy
from pyalgotrade import plotter
from pyalgotrade.technical import bollinger
from pyalgotrade.stratanalyzer import sharpe
from pyalgotrade.utils import wind_feed
from pyalgotrade.stratanalyzer import drawdown
from WindPy import w
import copy
from pyalgotrade.technical import ma
from math import isnan
import pandas as pd
import sys
reload(sys)
sys.setdefaultencoding('utf-8')

class plate(strategy.BacktestingStrategy):
    def __init__(self, feed, instrumentByClass, longPeriod, shortPeriod):
        strategy.BacktestingStrategy.__init__(self, feed)
        self.__instrumentByClass = instrumentByClass
        
    def onBars(self, bars):
        
    def run(self):
        super(plate, self).run()  
        self.__orders.to_csv(u'F:\学习资料\开源证券实习\\板块关联系统交易记录.csv')
        return
    
def main(plot):
    w.start()
    instrumentClass = w.wset(u"SectorConstituent","date=20110101;sector=WIND中国行业指数;field=wind_code").Data[0]
    instrumentByClass = dict.fromkeys(instrumentClass.extend("index"))
    instruments = instrumentClass.extend("000300.SH")
    for assetClass in instrumentByClass:
        instrumentByClass[assetClass] = w.wset(u"IndexConstituent","date=20110101", wincode=assetClass,"field=wind_code").Data[0]
        instruments.extend(instrumentByClass[assetClass])
    instrumentByClass["index"] = instrumentClass
    
    longPeriod, shortPeriod = 40, 5
     
    feed = wind_feed.build_feed(instruments, None, "2011/01/01", "2016/12/31")
    strat = plate(feed, instrumentByClass, longPeriod, shortPeriod)
    sharpeRatioAnalyzer = sharpe.SharpeRatio(False)
    strat.attachAnalyzer(sharpeRatioAnalyzer)
    drawDownAnalyzer = drawdown.DrawDown()
    strat.attachAnalyzer(drawDownAnalyzer)
  
    if plot:
        plt = plotter.StrategyPlotter(strat, False, False, True)
    strat.run()
    print "Sharpe ratio: %.2f" % sharpeRatioAnalyzer.getSharpeRatio(0.03)
    print "Maximum DrawDown: %.2f" % drawDownAnalyzer.getMaxDrawDown()
    if plot:
        plt.plot()


if __name__ == "__main__":
    main(True)

            
        
    
    