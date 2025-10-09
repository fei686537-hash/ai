# coding=utf-8
import numpy as np
import pandas as pd
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
    log.info('初始股票池数量: %d' % len(stocks))
    
    # 获取当前日期
    current_date = context.current_dt
    
    # 1. 获取上市时间大于2年的股票
    stock_info = get_stock_info(stocks, ['listed_date'])
    valid_stocks = []
    for stock in stocks:
        try:
            start_date = stock_info[stock]['listed_date']
            if isinstance(start_date, str):
                try:
                    list_date = datetime.datetime.strptime(start_date, '%Y-%m-%d')  # 修改日期格式
                except ValueError:
                    try:
                        list_date = datetime.datetime.strptime(start_date, '%Y%m%d')  # 尝试另一种格式
                    except ValueError:
                        log.info('股票 %s 的日期格式无法解析: %s' % (stock, start_date))
                        continue
                days_listed = (current_date - list_date).days
                if days_listed > 365*2:
                    valid_stocks.append(stock)
        except Exception as e:
            log.info('处理股票 %s 时出错: %s' % (stock, str(e)))
            continue
            
    if not valid_stocks:
        return []
    
    log.info('上市时间筛选后数量: %d' % len(valid_stocks))
    
    # 2和3暂时跳过因为API不支持违规和问询信息
    # 4暂时跳过因为无法获取未来数据
    
    # 5. 剔除近30天内振幅最大的前5%的股票
    # log.info('开始振幅筛选，筛选前股票数量: %d' % len(valid_stocks))
    price_data = get_history(30, '1d', ['high', 'low'], security_list=valid_stocks)
    # log.info('获取到的价格数据形状: %s' % str(price_data.shape))
    
    amplitudes = {}
    for stock in valid_stocks:
        try:
            stock_data = price_data[price_data['code'] == stock]
            highs = stock_data['high'].values
            lows = stock_data['low'].values
            
            if len(highs) > 0 and len(lows) > 0:
                highs = highs[~np.isnan(highs)]  # 移除NaN值
                lows = lows[~np.isnan(lows)]     # 移除NaN值
                if len(highs) > 0 and len(lows) > 0:
                    max_high = max(highs)
                    min_low = min(lows)
                    if min_low > 0:  # 确保不会除以0
                        amplitude = (max_high - min_low) / min_low
                        amplitudes[stock] = amplitude
        except Exception as e:
            log.info('计算股票 %s 振幅时出错: %s' % (stock, str(e)))
            continue
            
    if not amplitudes:
        log.info('没有任何股票的振幅数据可用')
        return []
    
    log.info('成功计算振幅的股票数量: %d' % len(amplitudes))
    threshold = np.percentile(list(amplitudes.values()), 95)
    log.info('振幅阈值(95分位数): %.2f%%' % (threshold * 100))
    
    # 找出振幅超过阈值的股票
    high_amplitude_stocks = [stock for stock in amplitudes if amplitudes[stock] > threshold]
    # log.info('振幅过高被剔除的股票: %s' % high_amplitude_stocks)
    # log.info('被剔除的股票振幅: %s' % [(stock, '%.2f%%' % (amplitudes[stock] * 100)) for stock in high_amplitude_stocks])
    
    valid_stocks = [stock for stock in valid_stocks if stock in amplitudes and amplitudes[stock] <= threshold]
    
    if not valid_stocks:
        log.info('振幅筛选后股票池为空')
        return []
    
    log.info('振幅筛选后数量: %d' % len(valid_stocks))

        
    # 6. 剔除换手率最高的50%
    log.info('开始换手率筛选，筛选前股票数量: %d' % len(valid_stocks))
    
    try:
        # 获取估值数据中的换手率
        turnover_data = get_fundamentals(valid_stocks, 'valuation', fields=['turnover_rate'])
        log.info('获取到的换手率数据类型: %s' % type(turnover_data))
        log.info('获取到的换手率数据: %s' % str(turnover_data))
        
        if turnover_data is None or len(turnover_data) == 0:
            log.info('获取到的换手率数据为空')
            return []
            
        # 处理换手率数据
        turnovers = {}
        
        # 如果是DataFrame格式
        if hasattr(turnover_data, 'iterrows'):
            for index, row in turnover_data.iterrows():
                try:
                    stock = row.name if isinstance(row.name, str) else row['code']
                    turnover_rate = row['turnover_rate']
                    if isinstance(turnover_rate, str):
                        turnover_rate = float(turnover_rate.strip('%'))
                    if turnover_rate > 0:
                        turnovers[stock] = turnover_rate
                        # 正确log
                        # log.info('股票 %s 的换手率: %.2f%%' % (stock, turnover_rate))
                    else:
                        log.info('股票 %s 的换手率为0' % stock)
                except Exception as e:
                    log.info('处理股票换手率时出错: %s' % str(e))
                    continue
        # 如果是字典格式
        elif isinstance(turnover_data, dict):
            for stock in valid_stocks:
                try:
                    if stock in turnover_data:
                        turnover_rate = turnover_data[stock]['turnover_rate']
                        if isinstance(turnover_rate, str):
                            turnover_rate = float(turnover_rate.strip('%'))
                        if turnover_rate > 0:
                            turnovers[stock] = turnover_rate
                            # 正确 log
                            # log.info('股票 %s 的换手率: %.2f%%' % (stock, turnover_rate))
                        else:
                            log.info('股票 %s 的换手率为0' % stock)
                    else:
                        log.info('股票 %s 没有换手率数据' % stock)
                except Exception as e:
                    log.info('处理股票 %s 换手率时出错: %s' % (stock, str(e)))
                    continue
        else:
            log.info('不支持的换手率数据格式: %s' % type(turnover_data))
            return []
                
        if not turnovers:
            log.info('没有有效的换手率数据')
            return []
        
        log.info('成功获取换手率数据的股票数量: %d' % len(turnovers))
        
        # 计算换手率的中位数作为阈值
        threshold = np.median(list(turnovers.values()))
        log.info('换手率中位数阈值: %.2f%%' % threshold)
        
        # 找出换手率高于中位数的股票
        high_turnover_stocks = [(stock, turnovers[stock]) for stock in turnovers if turnovers[stock] > threshold]
        high_turnover_stocks.sort(key=lambda x: x[1], reverse=True)  # 按换手率从高到低排序
        
        if high_turnover_stocks:
            log.info('换手率最高的几只股票:')
            for stock, rate in high_turnover_stocks[:5]:  # 显示前5只换手率最高的
                log.info('  %s: %.2f%%' % (stock, rate))
        
        # 保留换手率低于等于中位数的股票
        valid_stocks = [stock for stock in valid_stocks if stock in turnovers and turnovers[stock] <= threshold]
        
        if not valid_stocks:
            log.info('换手率筛选后股票池为空')
            return []
        
        log.info('换手率筛选后数量: %d' % len(valid_stocks))
        # log.info('换手率筛选后股票: %s' % valid_stocks)
        
    except Exception as e:
        log.error('获取换手率数据时发生错误: %s' % str(e))
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
        log.info('乖离率筛选后股票池为空')
        return []
    
    log.info('乖离率筛选后数量: %d' % len(valid_stocks))
    # 正确log 
    # log.info('乖离率筛选后股票: %s' % valid_stocks)
        
    # 8. TTM股息等于0的剔除
    try:
        # 获取估值数据中的滚动股息率
        dividend_data = get_fundamentals(valid_stocks, 'valuation', fields=['dividend_ratio'])
        log.info('获取到的股息率数据类型: %s' % type(dividend_data))
        
        if dividend_data is None or len(dividend_data) == 0:
            log.info('获取到的股息率数据为空')
            return []
            
        # 处理股息率数据
        dividends = {}
        
        # 如果是DataFrame格式
        if hasattr(dividend_data, 'iterrows'):
            for index, row in dividend_data.iterrows():
                try:
                    stock = row.name if isinstance(row.name, str) else row['code']
                    dividend_str = row['dividend_ratio']
                    # API文档说明：dividend_ratio返回的是带%的字符串
                    if isinstance(dividend_str, str):
                        dividend_rate = float(dividend_str.strip('%'))
                    else:
                        dividend_rate = float(dividend_str)
                    if dividend_rate > 0:
                        dividends[stock] = dividend_rate
                        # 正确log
                        # log.info('股票 %s 的股息率: %.2f%%' % (stock, dividend_rate))
                except Exception as e:
                    log.info('处理股票股息率时出错: %s' % str(e))
                    continue
        # 如果是字典格式
        elif isinstance(dividend_data, dict):
            for stock in valid_stocks:
                try:
                    if stock in dividend_data:
                        dividend_str = dividend_data[stock]['dividend_ratio']
                        if isinstance(dividend_str, str):
                            dividend_rate = float(dividend_str.strip('%'))
                        else:
                            dividend_rate = float(dividend_str)
                        if dividend_rate > 0:
                            dividends[stock] = dividend_rate
                            # 正确log 
                            # log.info('股票 %s 的股息率: %.2f%%' % (stock, dividend_rate))
                except Exception as e:
                    log.info('处理股票 %s 股息率时出错: %s' % (stock, str(e)))
                    continue
        else:
            log.info('不支持的股息率数据格式: %s' % type(dividend_data))
            return []
                
        if not dividends:
            log.info('没有有效的股息率数据')
            return []
            
        # 保留股息率大于0的股票
        valid_stocks = [stock for stock in valid_stocks if stock in dividends]
        
        if not valid_stocks:
            log.info('股息率筛选后股票池为空')
            return []
        
        log.info('股息率筛选后数量: %d' % len(valid_stocks))
        # 正确log 
        # log.info('股息率筛选后股票: %s' % valid_stocks)
        
    except Exception as e:
        log.error('获取股息率数据时发生错误: %s' % str(e))
        return []
        
    # 9. 剔除连续亏损两年的股票
    try:
        # 获取近两年的年报净利润数据
        current_year = int(context.current_dt.strftime('%Y'))
        financial_data = get_fundamentals(valid_stocks, 'income_statement', 
                                       fields=['net_profit', 'np_parent_company_owners'],  # 同时获取净利润和归属母公司净利润
                                       start_year=str(current_year-2),  # 从当前年份往前推2年
                                       end_year=str(current_year-1), 
                                       report_types='1')  # 只看年报
        
        log.info('尝试获取的股票数量: %d' % len(valid_stocks))
        log.info('获取到的财务数据类型: %s' % type(financial_data))
        
        if financial_data is None or len(financial_data) == 0:
            log.info('获取到的财务数据为空')
            return []
            
        # 处理净利润数据
        valid_profit_stocks = []
        problematic_stocks = []  # 用于记录被剔除的股票
        
        # 处理净利润数据
        for stock in valid_stocks:
            try:
                # 获取该股票的财务数据
                if isinstance(financial_data, dict):
                    stock_data = financial_data.get(stock, {})
                else:  # DataFrame格式
                    stock_data = financial_data[financial_data.index.get_level_values('secu_code') == stock]
                
                if stock_data is not None and (isinstance(stock_data, dict) or not stock_data.empty):
                    # 优先使用归属母公司净利润
                    if 'np_parent_company_owners' in (stock_data.columns if hasattr(stock_data, 'columns') else stock_data):
                        profits = stock_data['np_parent_company_owners']
                        profit_type = '归属母公司净利润'
                    else:
                        profits = stock_data['net_profit']
                        profit_type = '净利润'
                        
                    # 确保profits是数值列表
                    if isinstance(profits, pd.Series):
                        profits = profits.values
                    elif isinstance(profits, dict):
                        profits = [v for v in profits.values() if isinstance(v, (int, float))]
                        
                    # 检查最近两年的利润
                    if len(profits) >= 2:
                        recent_profits = profits[-2:]  # 取最近两年
                        if all(p > 0 for p in recent_profits):  # 检查是否都为正
                            valid_profit_stocks.append(stock)
                            log.info('股票 %s 最近两年%s: %.2f万, %.2f万' % 
                                   (stock, profit_type, recent_profits[0]/10000, recent_profits[1]/10000))
                        else:
                            problematic_stocks.append((stock, recent_profits))
                    else:
                        log.info('股票 %s 财务数据不足两年' % stock)
                            
            except Exception as e:
                log.error('处理股票 %s 时发生错误: %s' % (stock, str(e)))
                continue
                
        # 输出被剔除的股票信息
        if problematic_stocks:
            log.info('以下股票因连续亏损被剔除:')
            for stock, profits in problematic_stocks:
                log.info('  %s: 最近两年利润: %.2f万, %.2f万' % 
                        (stock, profits[0]/10000, profits[1]/10000))
                
        # 更新有效股票池
        valid_stocks = valid_profit_stocks
        
        if not valid_stocks:
            log.info('盈利能力筛选后股票池为空')
            return []
        
        log.info('盈利能力筛选后数量: %d' % len(valid_stocks))
        # log.info('盈利能力筛选后股票: %s' % valid_stocks)
        
    except Exception as e:
        log.error('获取净利润数据时发生错误: %s' % str(e))
        return []
        
    # 10. 资产负债率大于70%的剔除
    try:
        # 获取资产负债表数据
        debt_data = get_fundamentals(valid_stocks, 'debt_paying_ability', 
                                   fields=['debt_equity_ratio'])  # 使用偿债能力表中的产权比率
        
        if debt_data is None or len(debt_data) == 0:
            log.info('获取资产负债率数据为空')
            return []
            
        filtered_stocks = []
        problematic_stocks = []
        
        for stock in valid_stocks:
            try:
                if isinstance(debt_data, dict):
                    if stock in debt_data:
                        ratio = float(debt_data[stock]['debt_equity_ratio'])
                        if ratio <= 70:  # 产权比率<=70%
                            filtered_stocks.append(stock)
                        else:
                            problematic_stocks.append((stock, ratio))
                else:  # DataFrame格式
                    stock_data = debt_data[debt_data.index.get_level_values('secu_code') == stock]
                    if not stock_data.empty:
                        ratio = float(stock_data['debt_equity_ratio'].iloc[0])
                        if ratio <= 70:
                            filtered_stocks.append(stock)
                        else:
                            problematic_stocks.append((stock, ratio))
            except Exception as e:
                log.info('处理股票 %s 资产负债率时出错: %s' % (stock, str(e)))
                continue
                
        if problematic_stocks:
            log.info('以下股票因资产负债率过高被剔除:')
            for stock, ratio in problematic_stocks:
                log.info('  %s: 资产负债率 %.2f%%' % (stock, ratio))
                
        valid_stocks = filtered_stocks
        
        if not valid_stocks:
            log.info('资产负债率筛选后股票池为空')
            return []
        
        log.info('资产负债率筛选后数量: %d' % len(valid_stocks))
        
    except Exception as e:
        log.error('获取资产负债率数据时发生错误: %s' % str(e))
        return []
        
    # 11. 剔除收盘价最高的10%
    try:
        price_data = get_history(1, '1d', ['close'], security_list=valid_stocks)
        if price_data is None or price_data.empty:
            log.info('获取价格数据为空')
            return []
            
        prices = {}
        for stock in valid_stocks:
            try:
                stock_data = price_data[price_data['code'] == stock]
                if not stock_data.empty:
                    prices[stock] = stock_data['close'].iloc[0]
            except Exception as e:
                log.info('处理股票 %s 收盘价时出错: %s' % (stock, str(e)))
                continue
                
        if not prices:
            return []
            
        threshold = np.percentile(list(prices.values()), 90)
        high_price_stocks = [(stock, price) for stock, price in prices.items() 
                            if price > threshold]
        
        if high_price_stocks:
            log.info('以下股票因收盘价过高被剔除:')
            for stock, price in sorted(high_price_stocks, key=lambda x: x[1], reverse=True):
                log.info('  %s: 收盘价 %.2f' % (stock, price))
                
        valid_stocks = [stock for stock in valid_stocks if stock in prices 
                       and prices[stock] <= threshold]
        
        if not valid_stocks:
            log.info('收盘价筛选后股票池为空')
            return []
        
        log.info('收盘价筛选后数量: %d' % len(valid_stocks))
        
    except Exception as e:
        log.error('获取收盘价数据时发生错误: %s' % str(e))
        return []
        
    # 12. 剔除总市值排名最大的95%
    try:
        # 使用valuation表获取总市值数据
        market_data = get_fundamentals(valid_stocks, 'valuation', 
                                     fields=['total_value'])  # total_value是A股总市值
        
        if market_data is None or len(market_data) == 0:
            log.info('获取市值数据为空')
            return []
            
        caps = {}
        for stock in valid_stocks:
            try:
                if isinstance(market_data, dict):
                    if stock in market_data:
                        caps[stock] = float(market_data[stock]['total_value'])
                else:  # DataFrame格式
                    stock_data = market_data[market_data.index.get_level_values('secu_code') == stock]
                    if not stock_data.empty:
                        caps[stock] = float(stock_data['total_value'].iloc[0])
            except Exception as e:
                log.info('处理股票 %s 市值数据时出错: %s' % (stock, str(e)))
                continue
                
        if not caps:
            return []
            
        threshold = np.percentile(list(caps.values()), 5)  # 只保留最小的5%
        large_cap_stocks = [(stock, cap) for stock, cap in caps.items() 
                           if cap > threshold]
        
        if large_cap_stocks:
            log.info('以下股票因市值过大被剔除:')
            for stock, cap in sorted(large_cap_stocks, key=lambda x: x[1], reverse=True)[:5]:
                log.info('  %s: 总市值 %.2f亿' % (stock, cap/100000000))
                
        valid_stocks = [stock for stock in valid_stocks if stock in caps 
                       and caps[stock] <= threshold]
        
        if not valid_stocks:
            log.info('市值筛选后股票池为空')
            return []
        
        log.info('市值筛选后数量: %d' % len(valid_stocks))
        
    except Exception as e:
        log.error('获取市值数据时发生错误: %s' % str(e))
        return []
    
    # 13. 剔除科创板、创业板、北交所、ST
    try:
        stock_info = get_stock_info(valid_stocks, ['stock_name'])
        if stock_info is None:
            log.info('获取股票信息为空')
            return []
            
        filtered_stocks = []
        excluded_stocks = []
        
        for stock in valid_stocks:
            try:
                if stock in stock_info:
                    info = stock_info[stock]
                    stock_name = info.get('stock_name', '')
                    
                    # 判断股票类型
                    is_excluded = False
                    reason = None
                    
                    if stock.startswith('688'):
                        is_excluded = True
                        reason = '科创板'
                    elif stock.startswith('300'):
                        is_excluded = True
                        reason = '创业板'
                    elif stock.startswith('8'):
                        is_excluded = True
                        reason = '北交所'
                    elif 'ST' in stock_name:
                        is_excluded = True
                        reason = 'ST股票'
                        
                    if is_excluded:
                        excluded_stocks.append((stock, stock_name, reason))
                    else:
                        filtered_stocks.append(stock)
                        
            except Exception as e:
                log.info('处理股票 %s 类型判断时出错: %s' % (stock, str(e)))
                continue
                
        if excluded_stocks:
            log.info('以下股票因类型不符被剔除:')
            for stock, name, reason in excluded_stocks:
                log.info('  %s (%s): %s' % (stock, name, reason))
                
        valid_stocks = filtered_stocks
    
        log.info('最终筛选后数量: %d' % len(valid_stocks))
        log.info('最终筛选后股票: %s' % valid_stocks)
        
        return valid_stocks
    except Exception as e:
        log.error('获取市值数据时发生错误: %s' % str(e))
        return []

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