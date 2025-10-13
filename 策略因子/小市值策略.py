# coding=utf-8
import numpy as np
import pandas as pd
import datetime
import time
import traceback

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
                            # log.info('股票 %s 最近两年%s: %.2f万, %.2f万' % 
                            #        (stock, profit_type, recent_profits[0]/10000, recent_profits[1]/10000))
                        else:
                            problematic_stocks.append((stock, recent_profits))
                    else:
                        log.info('股票 %s 财务数据不足两年' % stock)
                            
            except Exception as e:
                log.error('处理股票 %s 时发生错误: %s' % (stock, str(e)))
                continue
                
        # 输出被剔除的股票信息
        # if problematic_stocks:
        #     log.info('以下股票因连续亏损被剔除:')
        #     for stock, profits in problematic_stocks:
        #         log.info('  %s: 最近两年利润: %.2f万, %.2f万' % 
        #                 (stock, profits[0]/10000, profits[1]/10000))
                
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
    log.info("==========开始资产负债率筛选==========")
    log.info("输入股票数量: {}".format(len(valid_stocks)))
    
    try:
        # 使用PTrade API获取资产负债表数据
        debt_data = get_fundamentals(valid_stocks, 'balance_statement', 
                                   fields=['total_liability', 'total_assets'], report_types='1')
        
        if debt_data is None or len(debt_data) == 0:
            log.warning('获取资产负债表数据为空，跳过资产负债率筛选')
            return []
            
        filtered_stocks = []
        removed_stocks = []
        debt_ratios = []
        
        for stock in valid_stocks:
            try:
                # 根据返回数据格式处理
                if isinstance(debt_data, dict):
                    if stock in debt_data:
                        stock_data = debt_data[stock]
                        total_liability = float(stock_data.get('total_liability', 0))
                        total_assets = float(stock_data.get('total_assets', 1))  # 避免除零
                    else:
                        log.warning("股票 {} 未找到资产负债表数据，跳过".format(stock))
                        continue
                else:  # DataFrame格式
                    # 根据API文档，返回的DataFrame中股票代码字段是secu_code
                    if 'secu_code' in debt_data.columns:
                        stock_data = debt_data[debt_data['secu_code'] == stock]
                    else:
                        # 如果没有secu_code字段，尝试使用索引
                        stock_data = debt_data[debt_data.index == stock] if stock in debt_data.index else pd.DataFrame()
                    
                    if stock_data.empty:
                        log.warning("股票 {} 未找到资产负债表数据，跳过".format(stock))
                        continue
                    
                    # 检查字段是否存在
                    if 'total_liability' not in stock_data.columns or 'total_assets' not in stock_data.columns:
                        log.warning("股票 {} 缺少必要的财务字段，跳过".format(stock))
                        continue
                        
                    total_liability = float(stock_data['total_liability'].iloc[0])
                    total_assets = float(stock_data['total_assets'].iloc[0])
                
                # 计算资产负债率
                if total_assets > 0:
                    debt_ratio = (total_liability / total_assets) * 100
                    debt_ratios.append(debt_ratio)
                    
                    if debt_ratio <= 70:  # 资产负债率<=70%
                        filtered_stocks.append(stock)
                        log.debug(f"股票 {stock} 资产负债率 {debt_ratio:.2f}% <= 70%，资产负债分别为 {total_liability:.2f}万, {total_assets:.2f}万 保留 ")
                    else:
                        removed_stocks.append((stock, debt_ratio))
                        log.debug("股票 {} 资产负债率 {:.2f}% > 70%，剔除".format(stock, debt_ratio))
                else:
                    log.warning("股票 {} 总资产为0或负数，跳过".format(stock))
                    
            except Exception as e:
                log.error('处理股票 {} 资产负债率时出错: {}'.format(stock, str(e)))
                continue
        
        # 统计信息
        if debt_ratios:
            log.info("资产负债率统计 - 最小值: {:.2f}%, 最大值: {:.2f}%, 平均值: {:.2f}%".format(
                min(debt_ratios), max(debt_ratios), sum(debt_ratios)/len(debt_ratios)))
        
        # 记录被剔除的股票
        if removed_stocks:
            log.info('以下 {} 只股票因资产负债率过高被剔除:'.format(len(removed_stocks)))
            for stock, ratio in removed_stocks[:10]:  # 只显示前10只
                log.info('  {}: 资产负债率 {:.2f}%'.format(stock, ratio))
            if len(removed_stocks) > 10:
                log.info('  ... 还有 {} 只股票被剔除'.format(len(removed_stocks) - 10))
        
        if not filtered_stocks:
            log.warning('资产负债率筛选后股票池为空')
            return []
        
        log.info('资产负债率筛选完成 - 剔除股票数: {}, 保留股票数: {}'.format(
            len(removed_stocks), len(filtered_stocks)))
        log.info("==========资产负债率筛选结束==========")
        
        valid_stocks = filtered_stocks
        
    except Exception as e:
        log.error('获取资产负债率数据时发生错误: {}'.format(str(e)))
        log.error('错误详情: {}'.format(traceback.format_exc()))
        return []
                
        if problematic_stocks:
            log.info('以下 {} 只股票因资产负债率过高被剔除:'.format(len(removed_stocks)))
            for stock, ratio in problematic_stocks:
                log.info('  %s: 资产负债率 %.2f%%' % (stock, ratio))
                
        valid_stocks = filtered_stocks
        
        if not valid_stocks:
            log.info('资产负债率筛选后股票池为空')
            return []
        
        log.info('资产负债率筛选后数量: %d' % len(valid_stocks))
        
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
        
        # if high_price_stocks:
        #     log.info('以下股票因收盘价过高被剔除:')
        #     for stock, price in sorted(high_price_stocks, key=lambda x: x[1], reverse=True):
        #         log.info('  %s: 收盘价 %.2f' % (stock, price))
                
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
        log.info('选股结果名称1: %s' % get_stock_info(stock_pool, ['stock_name']))
        
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
    
    # 获取排序需要的数据
    try:
        # 1. 获取收盘价数据
        price_data = get_history(1, '1d', ['close'], security_list=stock_pool)
        log.info('价格数据类型: %s' % type(price_data))
        log.info('价格数据形状: %s' % str(price_data.shape if hasattr(price_data, 'shape') else 'N/A'))
        log.info('价格数据列名: %s' % str(price_data.columns.tolist() if hasattr(price_data, 'columns') else 'N/A'))
        if hasattr(price_data, 'head'):
            log.info('价格数据前几行:\n%s' % str(price_data.head()))
        
        # 2. 获取股息率数据
        dividend_data = get_fundamentals(stock_pool, 'valuation', fields=['dividend_ratio'])
        log.info('股息率数据类型: %s' % type(dividend_data))
        if hasattr(dividend_data, 'head'):
            log.info('股息率数据前几行:\n%s' % str(dividend_data.head()))
        
        # 3. 获取总市值数据
        market_data = get_fundamentals(stock_pool, 'valuation', fields=['total_value'])
        log.info('总市值数据类型: %s' % type(market_data))
        if hasattr(market_data, 'head'):
            log.info('总市值数据前几行:\n%s' % str(market_data.head()))
        
        # 4. 获取净利润和股息支付率数据
        try:
            # 根据PTrade API文档，利润表支持按年份查询模式
            # 获取最近一年的净利润数据用于计算股息支付率
            current_year = int(context.current_dt.strftime('%Y'))
            
            # 获取净利润数据 - 使用年份查询模式获取最新财报数据
            financial_data = get_fundamentals(
                stock_pool, 
                'income_statement', 
                fields=['net_profit', 'np_parent_company_owners'],  # 移除secu_code，因为它通常在索引中
                start_year=str(current_year-1),
                end_year=str(current_year),
                report_types='1'  # 年报数据，修正为字符串而非列表
            )
            
            # 获取股息率数据 - 估值数据只支持按天查询模式
            # 使用前一交易日的数据，确保数据可用性
            dividend_data = get_fundamentals(
                stock_pool, 
                'valuation', 
                fields=['dividend_ratio', 'total_value'],  # 移除secu_code，因为它通常在索引中
                date=context.previous_date  # 使用前一交易日的数据，而不是当前日期
            )
            
            # 尝试获取更多历史数据作为备选
            if dividend_data is None or len(dividend_data) == 0:
                log.warning("当前日期无法获取股息率数据，尝试获取30天前的数据")
                past_date = (context.current_dt - datetime.timedelta(days=30)).strftime('%Y-%m-%d')
                dividend_data = get_fundamentals(
                    stock_pool, 
                    'valuation', 
                    fields=['dividend_ratio', 'total_value'],
                    date=past_date
                )
            
            # 打印数据结构信息用于调试
            log.info(f'财务数据结构: 类型={type(financial_data)}, 形状={financial_data.shape if hasattr(financial_data, "shape") else "无形状"}')
            log.info(f'财务数据列: {list(financial_data.columns) if hasattr(financial_data, "columns") else "无列信息"}')
            if hasattr(financial_data, 'index'):
                log.info(f'财务数据索引: {financial_data.index.names if hasattr(financial_data.index, "names") else "单级索引"}')
            
            log.info(f'股息数据结构: 类型={type(dividend_data)}, 形状={dividend_data.shape if hasattr(dividend_data, "shape") else "无形状"}')
            log.info(f'股息数据列: {list(dividend_data.columns) if hasattr(dividend_data, "columns") else "无列信息"}')
            if hasattr(dividend_data, 'index'):
                log.info(f'股息数据索引: {dividend_data.index.names if hasattr(dividend_data.index, "names") else "单级索引"}')
            
        except Exception as e:
            log.error(f'获取财务和股息数据时出错: {str(e)}')
            log.error(traceback.format_exc())
            # 创建空DataFrame作为备选
            financial_data = pd.DataFrame()
            dividend_data = pd.DataFrame()
        
        # 初始化股票因子字典
        stock_factors = {}
        
        # 创建股息支付率计算函数
        def calculate_payout_ratio(stock_code, financial_df, dividend_df):
            """
            计算股息支付率
            股息支付率 = 每股股息 / 每股收益 * 100%
            或者 股息支付率 = 总分红金额 / 净利润 * 100%
            """
            try:
                log.info('开始计算股票 %s 的股息支付率' % stock_code)
                
                # 获取净利润数据
                net_profit = 0
                if not financial_df.empty:
                    # 检查索引结构并筛选该股票的数据
                    stock_financial = None
                    
                    # 如果是MultiIndex，尝试在不同级别查找股票代码
                    if hasattr(financial_df.index, 'levels'):
                        for level in range(len(financial_df.index.levels)):
                            try:
                                if stock_code in financial_df.index.get_level_values(level):
                                    stock_financial = financial_df.xs(stock_code, level=level)
                                    log.info('股票 %s 在财务数据第%d级索引中找到' % (stock_code, level))
                                    break
                            except:
                                continue
                    else:
                        # 单级索引，直接查找
                        if stock_code in financial_df.index:
                            stock_financial = financial_df.loc[stock_code]
                            log.info('股票 %s 在财务数据单级索引中找到' % stock_code)
                    
                    if stock_financial is not None and not stock_financial.empty:
                        log.info('股票 %s 财务数据: %s' % (stock_code, str(stock_financial)))
                        # 优先使用归属于母公司股东的净利润
                        if 'net_profit_atsopc' in stock_financial.index:
                            net_profit = stock_financial['net_profit_atsopc']
                            log.info('使用net_profit_atsopc: %s' % str(net_profit))
                        elif 'net_profit' in stock_financial.index:
                            net_profit = stock_financial['net_profit']
                            log.info('使用net_profit: %s' % str(net_profit))
                        
                        net_profit = float(net_profit) if pd.notna(net_profit) and net_profit != 0 else 0
                        log.info('股票 %s 净利润: %.2f万元' % (stock_code, net_profit/10000))
                    else:
                        log.info('股票 %s 未找到财务数据' % stock_code)
                else:
                    log.info('财务数据为空')
                
                # 获取股息数据
                dividend_amount = 0
                if not dividend_df.empty:
                    stock_dividend = None
                    
                    # 检查索引结构并筛选该股票的数据
                    if hasattr(dividend_df.index, 'levels'):
                        for level in range(len(dividend_df.index.levels)):
                            try:
                                if stock_code in dividend_df.index.get_level_values(level):
                                    stock_dividend = dividend_df.xs(stock_code, level=level)
                                    log.info('股票 %s 在股息数据第%d级索引中找到' % (stock_code, level))
                                    break
                            except:
                                continue
                    else:
                        # 单级索引，直接查找
                        if stock_code in dividend_df.index:
                            stock_dividend = dividend_df.loc[stock_code]
                            log.info('股票 %s 在股息数据单级索引中找到' % stock_code)
                    
                    if stock_dividend is not None and not stock_dividend.empty:
                        log.info('股票 %s 股息数据: %s' % (stock_code, str(stock_dividend)))
                        # 从股息率和市值计算分红金额
                        dividend_ratio = 0
                        market_value = 0
                        
                        # 处理股息率
                        if isinstance(stock_dividend, pd.Series):
                            if 'dividend_ratio' in stock_dividend.index:
                                div_ratio = stock_dividend['dividend_ratio']
                                if isinstance(div_ratio, str):
                                    dividend_ratio = float(div_ratio.strip('%'))
                                else:
                                    dividend_ratio = float(div_ratio) if pd.notna(div_ratio) and div_ratio != 0 else 0
                            
                            if 'total_value' in stock_dividend.index:
                                total_val = stock_dividend['total_value']
                                market_value = float(total_val) if pd.notna(total_val) and total_val != 0 else 0
                        elif isinstance(stock_dividend, pd.DataFrame):
                            if 'dividend_ratio' in stock_dividend.columns:
                                div_ratio = stock_dividend['dividend_ratio'].iloc[0]
                                if isinstance(div_ratio, str):
                                    dividend_ratio = float(div_ratio.strip('%'))
                                else:
                                    dividend_ratio = float(div_ratio) if pd.notna(div_ratio) and div_ratio != 0 else 0
                            
                            if 'total_value' in stock_dividend.columns:
                                total_val = stock_dividend['total_value'].iloc[0]
                                market_value = float(total_val) if pd.notna(total_val) and total_val != 0 else 0
                        
                        log.info('股票 %s 股息率: %.2f%%, 市值: %.2f万元' % (stock_code, dividend_ratio, market_value/10000))
                        
                        # 计算分红金额 = 市值 * 股息率 / 100
                        dividend_amount = market_value * dividend_ratio / 100
                        log.info('股票 %s 分红金额: %.2f万元' % (stock_code, dividend_amount/10000))
                    else:
                        log.info('股票 %s 未找到股息数据' % stock_code)
                else:
                    log.info('股息数据为空')
                
                # 计算股息支付率
                # 确保net_profit和dividend_amount是标量值
                net_profit_val = float(net_profit) if pd.notna(net_profit) else 0
                dividend_amount_val = float(dividend_amount) if pd.notna(dividend_amount) else 0
                
                if net_profit_val > 0 and dividend_amount_val > 0:
                    payout_ratio = (dividend_amount_val / net_profit_val) * 100
                    final_ratio = min(payout_ratio, 100)  # 限制最大值为100%
                    log.info('股票 %s 股息支付率: %.2f%%' % (stock_code, final_ratio))
                    return final_ratio
                else:
                    log.info('股票 %s 股息支付率为0 (净利润: %.2f, 分红金额: %.2f)' % (stock_code, net_profit_val, dividend_amount_val))
                    return 0
                    
            except Exception as e:
                log.error(f'计算股票{stock_code}股息支付率时发生错误: {str(e)}')
                return 0
        
        # 处理每个股票的因子数据
        for stock in stock_pool:
            try:
                log.info('开始处理股票 %s 的因子数据' % stock)
                
                # 初始化股票因子数据
                stock_factors[stock] = {
                    'close_price': 0,
                    'dividend_ratio': 0,
                    'market_value': float('inf'),
                    'payout_ratio': 0,
                    'insider_holding': 0
                }
                
                # 1. 处理收盘价数据
                close_price = 0
                if price_data is not None and not price_data.empty:
                    # 根据PTrade API，price_data通常包含code列
                    if 'code' in price_data.columns:
                        stock_price_data = price_data[price_data['code'] == stock]
                        if not stock_price_data.empty and 'close' in stock_price_data.columns:
                            close_price = float(stock_price_data['close'].iloc[-1])
                    # 如果是以股票代码为列名的格式
                    elif stock in price_data.columns:
                        close_price = float(price_data[stock].iloc[-1])
                
                stock_factors[stock]['close_price'] = close_price
                log.info('股票 %s 收盘价: %.2f' % (stock, close_price))
                
                # 2. 处理股息率数据（从dividend_data中获取）
                log.info('开始处理股票 %s 的股息率数据' % stock)
                if not dividend_data.empty:
                    stock_dividend = None
                    
                    # 检查索引结构并筛选该股票的数据
                    if hasattr(dividend_data.index, 'levels'):
                        for level in range(len(dividend_data.index.levels)):
                            try:
                                if stock in dividend_data.index.get_level_values(level):
                                    stock_dividend = dividend_data.xs(stock, level=level)
                                    log.info('股票 %s 在股息数据第%d级索引中找到' % (stock, level))
                                    break
                            except:
                                continue
                    else:
                        # 单级索引，直接查找
                        if stock in dividend_data.index:
                            stock_dividend = dividend_data.loc[stock]
                            log.info('股票 %s 在股息数据单级索引中找到' % stock)
                    
                    if stock_dividend is not None and not stock_dividend.empty:
                        log.info('股票 %s 股息数据类型: %s' % (stock, type(stock_dividend)))
                        log.info('股票 %s 股息数据内容: %s' % (stock, str(stock_dividend)))
                        
                        # 检查数据类型并处理股息率
                        if isinstance(stock_dividend, pd.Series):
                            # 如果是Series，直接通过索引访问
                            if 'dividend_ratio' in stock_dividend.index:
                                div_ratio = stock_dividend['dividend_ratio']
                                if isinstance(div_ratio, str):
                                    stock_factors[stock]['dividend_ratio'] = float(div_ratio.strip('%'))
                                else:
                                    stock_factors[stock]['dividend_ratio'] = float(div_ratio) if pd.notna(div_ratio) and div_ratio != 0 else 0
                                log.info('股票 %s 股息率(Series): %.2f%%' % (stock, stock_factors[stock]['dividend_ratio']))
                            
                            if 'total_value' in stock_dividend.index:
                                market_val = stock_dividend['total_value']
                                stock_factors[stock]['market_value'] = float(market_val) if pd.notna(market_val) and market_val != 0 else float('inf')
                                log.info('股票 %s 市值(Series): %.2f万元' % (stock, stock_factors[stock]['market_value']/10000))
                        elif isinstance(stock_dividend, pd.DataFrame):
                            # 如果是DataFrame，检查列
                            if 'dividend_ratio' in stock_dividend.columns:
                                div_ratio = stock_dividend['dividend_ratio'].iloc[0]
                                if isinstance(div_ratio, str):
                                    stock_factors[stock]['dividend_ratio'] = float(div_ratio.strip('%'))
                                else:
                                    stock_factors[stock]['dividend_ratio'] = float(div_ratio) if pd.notna(div_ratio) and div_ratio != 0 else 0
                                log.info('股票 %s 股息率(DataFrame): %.2f%%' % (stock, stock_factors[stock]['dividend_ratio']))
                            
                            if 'total_value' in stock_dividend.columns:
                                market_val = stock_dividend['total_value'].iloc[0]
                                stock_factors[stock]['market_value'] = float(market_val) if pd.notna(market_val) and market_val != 0 else float('inf')
                                log.info('股票 %s 市值(DataFrame): %.2f万元' % (stock, stock_factors[stock]['market_value']/10000))
                    else:
                        log.info('股票 %s 未找到股息数据' % stock)
                else:
                    log.info('股息数据为空，股票 %s 跳过股息率处理' % stock)
                
                # 3. 计算股息支付率（使用新的计算函数，需要同时传递股息率和市值数据）
                # 合并dividend_data和market_data用于计算
                combined_data = pd.DataFrame()
                if not dividend_data.empty and not market_data.empty:
                    try:
                        # 尝试合并dividend_data和market_data
                        if hasattr(dividend_data.index, 'levels') and hasattr(market_data.index, 'levels'):
                            # 都是MultiIndex
                            combined_data = pd.concat([dividend_data, market_data], axis=1)
                        else:
                            # 简单合并
                            combined_data = pd.concat([dividend_data, market_data], axis=1)
                    except Exception as e:
                        log.error('合并股息和市值数据时出错: %s' % str(e))
                        combined_data = dividend_data  # 使用dividend_data作为备选
                
                stock_factors[stock]['payout_ratio'] = calculate_payout_ratio(stock, financial_data, combined_data)
                
                # 4. 高管增持比例暂时设为0，因为需要额外的数据源
                stock_factors[stock]['insider_holding'] = 0
                
                # 打印调试信息
                log.info('股票%s因子数据汇总: 收盘价=%.2f, 股息率=%.2f%%, 市值=%.2f亿, 股息支付率=%.2f%%' % 
                        (stock, stock_factors[stock]["close_price"], 
                         stock_factors[stock]["dividend_ratio"],
                         stock_factors[stock]["market_value"]/100000000,
                         stock_factors[stock]["payout_ratio"]))
                
            except Exception as e:
                log.error(f'处理股票{stock}的因子数据时发生错误: {str(e)}')
                log.error(traceback.format_exc())
                # 保持默认值，继续处理下一个股票
                continue

        # 对每个因子进行排序并分配分数
        sorted_stocks = []
        for stock in stock_pool:
            total_score = (
                -stock_factors[stock]['close_price'] +  # 收盘价从低到高
                stock_factors[stock]['dividend_ratio'] +  # 股息率从高到低
                stock_factors[stock]['payout_ratio'] +   # 股息支付率从大到小
                stock_factors[stock]['insider_holding'] + # 高管增持比例从高到低
                -stock_factors[stock]['market_value']    # 总市值从小到大
            )
            sorted_stocks.append((stock, total_score))
            
        # 根据总分排序
        sorted_stocks.sort(key=lambda x: x[1], reverse=True)
        
        # 获取排序后的股票列表
        stock_pool = [stock for stock, _ in sorted_stocks]
        
        log.info('多因子排序后的股票列表:')
        for stock, score in sorted_stocks:
            stock_info = get_stock_info([stock], ['stock_name'])[stock]
            log.info(f"{stock}({stock_info['stock_name']}): 收盘价={stock_factors[stock]['close_price']:.2f}, "
                    f"股息率={stock_factors[stock]['dividend_ratio']:.2f}%, "
                    f"股息支付率={stock_factors[stock]['payout_ratio']:.2f}, "
                    f"总市值={stock_factors[stock]['market_value']/100000000:.2f}亿")
    
    except Exception as e:
        log.error(f'多因子排序过程中发生错误: {str(e)}')
    
    log.info('选股结果名称2: %s' % get_stock_info(stock_pool, ['stock_name']))
        
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