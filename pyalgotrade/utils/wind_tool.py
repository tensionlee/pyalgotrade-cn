# coding=utf8

import pandas as pd
from datetime import datetime
RT_FIELDS = ['rt_bid1', 'rt_bsize1', 'rt_ask1', 'rt_asize1', 'rt_last', 'rt_vol', 'rt_pct_chg', 'rt_latest']
# from engine.events import RT_FIELDS

from WindPy import w
if not w.isconnected():
    w.start()

import time

def rt_snapshot(tickers, fields=RT_FIELDS):
    data = w.wsq(tickers, fields)
    while not data.ErrorCode == 0:
            print 'DataEngine: error happen in get rt data'
            time.sleep(3)
            data = w.wsq(tickers, fields)
    snap_shot = {}
    i = 0
    for code in data.Codes:
        rt_data = {}
        j = 0
        for field in RT_FIELDS:
            rt_data[field] = data.Data[j][i]
            j += 1
        i += 1
        snap_shot[code] = rt_data
    return snap_shot

def close_data():
    close_data = query_wind(w.wsd, 'close,')

def query_wind(func, codes, fields, start_time, end_time=None, *args):
    if end_time is None:
        data = func(codes, fields, start_time, *args)
    else:
        data = func(codes, fields, start_time, end_time, *args)
    if data.Data is not None:
        df = wind_ts2df(data, True, False)
        # df=df.dropna()
        fmt = '%Y%m%d %HH:%MM:%SS'
        tlist = [datetime.strptime(d.strftime(fmt), fmt) for d in df.index.tolist()]
        df.index = tlist
        return df
    else:
        return None
        
def wind_ts2df(result, isTs=True, isRT=False):
    ''' change wind time series to dataframe
    Args:
        result: should be wind result, has error code, Fields and Data
        isTs: time series flag, false when option chain
        isRT: realtime flag
    TODO:
        add a format decorator to the index 
    '''
    if not result.ErrorCode == 0:
        raise IOError
    
    targetData = result.Data
    if isTs == True and isRT == False:
        if len(targetData) == 1:
            # a little difference in Times only have one day
            targetData = targetData[0]
    
    data = dict()
    i = 0
    if len(result.Fields) > 1:
        # one stock, multiple indicators
        for field in result.Fields:
            data[field] = targetData[i]
            i += 1
    elif len(result.Codes) > 1:
        # one indicator, multiple stocks
        for code in result.Codes:
            data[code] = targetData[i]
            i += 1
    elif len(result.Codes) == 1 and len(result.Fields) == 1:
        data[result.Codes[0]] = targetData
    else:
        raise AttributeError
            
    if isTs == True:
        if isRT == False:
            return pd.DataFrame(data, index=result.Times)
        else:
            # design for wsq function
            return pd.DataFrame(data, index=result.Codes)
    else:
        return pd.DataFrame(data)

if __name__ == '__main__':
    codes = ['000300.SH', 'IF00.CFE']
    fields = ['close']
    start_time = '20150101'
    end_time = '20150110'
    print query_wind(w.wsd, codes, fields, start_time, end_time, 'Fill=Previous', 'PriceAdj=F')
    #
    # print w.wsd(codes, ['close'], start_time, end_time, 'Fill=Previous', 'PriceAdj=F')
