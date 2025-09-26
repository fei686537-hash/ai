# coding=utf-8
from ptrade import *
import numpy as np
import datetime
import time

def initialize(context):
    """
    初始化函数 
    1. 设置股票池更新频率
    2. 设置基准
    3. 设置佣金
    4. 设置滑点
    """
    # 设置基准为沪深300
    set_benchmark('000300.SS')
    # 设置佣金为万分之二(手续费等)
    set_commission(commission_ratio=0.0002, min_commission=5.0)
    # 设置滑点为千分之二
    set_slippage(0.002)
    # 设置成交量比例 
    set_volume_ratio(0.1)
    # 每天运行
    context.refresh_rate = 1
    context.day_counter = 0

def get_stock_pool(context):
    """
    获取符合条件的股票池
    """
    # 获取所有A股代码
    stocks = get_Ashares()
    
    # 获取当前日期
    current_date = context.current_dt
    
    # 1. 获取上市时间大于2年的股票
    stock_info = get_stock_info(stocks, ['start_date'])
    valid_stocks = []
    for stock in stocks:
        try:
            start_date = stock_info[stock]['start_date']
            if isinstance(start_date, str):
                list_date = datetime.datetime.strptime(start_date, '%Y%m%d')
                if (current_date - list_date).days > 365*2:
                    valid_stocks.append(stock)
        except:
            continue
            
    if not valid_stocks:
        return []
    
    # 2和3暂时跳过因为API不支持违规和问询信息
    # 4暂时跳过因为无法获取未来数据
    
    # 5. 剔除近30天内振幅最大的前5%的股票
    price_data = get_history(30, '1d', ['high', 'low'], security_list=valid_stocks)
    amplitudes = {}
    for stock in valid_stocks:
        try:
            highs = price_data.query(f'code == "{stock}"')['high']
            lows = price_data.query(f'code == "{stock}"')['low']
            if len(highs) > 0 and len(lows) > 0:
                amplitude = (max(highs) - min(lows)) / min(lows)
                amplitudes[stock] = amplitude
        except:
            continue
            
    if not amplitudes:
        return []
    
    threshold = np.percentile(list(amplitudes.values()), 95)
    valid_stocks = [stock for stock in valid_stocks if stock in amplitudes and amplitudes[stock] <= threshold]
    
    if not valid_stocks:
        return []
        
    # 6. 剔除换手率最高的50%
    turnover_data = get_history(1, '1d', ['turnover_ratio'], security_list=valid_stocks)
    turnovers = {}
    for stock in valid_stocks:
        try:
            turnover = turnover_data.query(f'code == "{stock}"')['turnover_ratio'].iloc[0]
            turnovers[stock] = turnover
        except:
            continue
            
    if not turnovers:
        return []
        
    threshold = np.median(list(turnovers.values()))
    valid_stocks = [stock for stock in valid_stocks if stock in turnovers and turnovers[stock] <= threshold]
    
    if not valid_stocks:
        return []
        
    # 7. 20日乖离率10至90%的剔除 
    price_data = get_history(20, '1d', ['close'], security_list=valid_stocks)
    current_data = get_history(1, '1d', ['close'], security_list=valid_stocks)
    bias = {}
    for stock in valid_stocks:
        try:
            ma20 = price_data.query(f'code == "{stock}"')['close'].mean()
            current_price = current_data.query(f'code == "{stock}"')['close'].iloc[0]
            if ma20 > 0:
                bias[stock] = (current_price - ma20) / ma20 * 100
        except:
            continue
            
    if not bias:
        return []
        
    bias_values = list(bias.values())
    lower = np.percentile(bias_values, 10)
    upper = np.percentile(bias_values, 90)
    valid_stocks = [stock for stock in valid_stocks if stock in bias and lower <= bias[stock] <= upper]
    
    if not valid_stocks:
        return []
        
    # 8. TTM股息等于0的剔除
    fundamental_data = get_fundamentals(valid_stocks, 'eps', ['ttm_dividend']) 
    valid_stocks = [stock for stock in valid_stocks if stock in fundamental_data and fundamental_data[stock]['ttm_dividend'] > 0]
    
    if not valid_stocks:
        return []
        
    # 9. 剔除连续亏损两年的股票
    financial_data = get_fundamentals(valid_stocks, 'income_statement', ['net_profit'])
    filtered_stocks = []
    for stock in valid_stocks:
        try:
            if stock in financial_data:
                profits = financial_data[stock]['net_profit']
                if not all(p <= 0 for p in profits[-2:]):  # 检查最近两年是否连续亏损
                    filtered_stocks.append(stock)
        except:
            continue
    valid_stocks = filtered_stocks
    
    if not valid_stocks:
        return []
        
    # 10. 资产负债率大于70%的剔除
    financial_data = get_fundamentals(valid_stocks, 'balance_statement', ['total_liability', 'total_assets'])
    filtered_stocks = []
    for stock in valid_stocks:
        try:
            if stock in financial_data:
                liability = financial_data[stock]['total_liability']
                assets = financial_data[stock]['total_assets']
                if assets > 0 and liability/assets <= 0.7:
                    filtered_stocks.append(stock)
        except:
            continue
    valid_stocks = filtered_stocks
    
    if not valid_stocks:
        return []
        
    # 11. 剔除收盘价最高的10%
    price_data = get_history(1, '1d', ['close'], security_list=valid_stocks)
    prices = {}
    for stock in valid_stocks:
        try:
            price = price_data.query(f'code == "{stock}"')['close'].iloc[0]
            prices[stock] = price
        except:
            continue
            
    if not prices:
        return []
            
    threshold = np.percentile(list(prices.values()), 90)
    valid_stocks = [stock for stock in valid_stocks if stock in prices and prices[stock] <= threshold]
    
    if not valid_stocks:
        return []
        
    # 12. 剔除总市值排名最大的95%
    market_data = get_fundamentals(valid_stocks, 'valuation', ['market_cap'])
    caps = {}
    for stock in valid_stocks:
        try:
            if stock in market_data:
                cap = market_data[stock]['market_cap']
                caps[stock] = cap
        except:
            continue
            
    if not caps:
        return []
            
    threshold = np.percentile(list(caps.values()), 5)  # 只保留最小的5%
    valid_stocks = [stock for stock in valid_stocks if stock in caps and caps[stock] <= threshold]
    
    if not valid_stocks:
        return []
    
    # 13. 剔除科创板、创业板、北交所、ST
    stock_names = get_stock_info(valid_stocks)
    filtered_stocks = []
    for stock in valid_stocks:
        if not (stock.startswith('688') or  # 科创板
                stock.startswith('300') or  # 创业板
                stock.startswith('8') or    # 北交所
                'ST' in stock_names[stock]['display_name']):  # ST股票
            filtered_stocks.append(stock)
            
    valid_stocks = filtered_stocks
    
    return valid_stocks

def handle_data(context, data):
    """
    交易逻辑主函数
    """
    # 每天调仓
    if context.day_counter % context.refresh_rate == 0:
        # 获取当前符合条件的股票池
        stock_pool = get_stock_pool(context)
        
        # 打印选股结果
        log.info('选股结果数量: %d' % len(stock_pool))
        log.info('选股结果: %s' % stock_pool)
        
        # 这里可以添加您的交易逻辑
        # 例如：等权重分配资金到选中的股票
        if stock_pool:
            # 计算每只股票的目标持仓比例
            target_percent = 1.0 / len(stock_pool)
            
            # 对所有持仓股票检查是否在新的股票池中
            current_positions = context.portfolio.positions
            for stock in current_positions:
                if stock not in stock_pool:
                    # 不在新股票池中的股票清仓
                    order_target_value(stock, 0)
                    
            # 对新的股票池进行调仓
            for stock in stock_pool:
                order_target_percent(stock, target_percent)
                
    context.day_counter += 1
        log.info('选股结果数量: %d' % len(stock_pool))
        log.info('选股结果: %s' % stock_pool)
        
        # 这里可以添加您的交易逻辑
        # 例如：等权重分配资金到选中的股票
        target_position = {}
        if stock_pool:
            weight = 1.0 / len(stock_pool)
            for stock in stock_pool:
                target_position[stock] = weight
        
        # 调整仓位
        adjust_position(context, target_position)
    
    context.day_counter += 1

def adjust_position(context, target_position):
    """调整持仓到目标仓位"""
    for stock in context.portfolio.positions:
        if stock not in target_position:
            order_target_percent(stock, 0)  # 卖出不在目标池的股票
    
    for stock in target_position:
        order_target_percent(stock, target_position[stock])  # 调整到目标仓位
