# coding=utf-8
import numpy as np
import pandas as pd
import datetime
import time
import traceback
import re

# 为兼容环境中可能缺少的 log.debug 方法：若无则回退到 info
try:
    if 'log' in globals() and not hasattr(log, 'debug'):
        log.debug = log.info
except Exception:
    pass

def initialize(context):
    """
    初始化函数 
    1. 设置股票池更新频率
    2. 设置基准
    3. 设置佣金
    4. 设置滑点
    5. 初始化全局变量
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
    # 周五选股设置：每周五选股并调仓（weekday=0，周一=0）
    context.weekly_buy_weekday = 4  # 周五选股买入
    # 选股数量设置
    context.selection_count = 5  # 每次选择5只股票
    # 记录上周一选股结果，用于对比
    context.last_friday_selection = []
    context.last_selection_date = None
    # 记录当天是否已执行选股，避免同日重复执行
    context.last_buy_date = None
    
    # 交易结束日期设置（写死的日期）
    context.trading_end_date = datetime.date(2025, 1, 13)  # 设置交易结束日期为2024年12月30日（周一）
    
    # 初始化全局变量
    g.recent_orders = []  # 用于跟踪最近的订单

def _normalize_local(code):
    """本地代码规范化函数 - 保留完整的股票代码格式"""
    if isinstance(code, str):
        s = code
    else:
        # 处理Position或Security对象
        s = str(getattr(code, 'security', None) or getattr(code, 'sid', None) or getattr(code, 'code', None) or code)
    
    # 标准化股票代码格式，保留后缀
    # 处理常见格式：000001.SZ, SZ000001, 000001.XSHE, 600000.SS, SH600000
    s = s.strip()
    
    # 如果是 SZ000001 或 SH600000 格式，转换为 000001.SZ 或 600000.SS
    if s.startswith('SZ') and len(s) == 8:
        return s[2:] + '.SZ'
    elif s.startswith('SH') and len(s) == 8:
        return s[2:] + '.SS'
    # 如果是 000001.XSHE 格式，转换为 000001.SZ
    elif s.endswith('.XSHE'):
        return s.replace('.XSHE', '.SZ')
    # 如果已经是标准格式（000001.SZ, 600000.SS），直接返回
    elif '.' in s and (s.endswith('.SZ') or s.endswith('.SS')):
        return s
    # 如果只有6位数字，需要根据前缀判断市场
    elif re.match(r'^\d{6}$', s):
        if s.startswith(('000', '002', '003', '300')):
            return s + '.SZ'  # 深市
        elif s.startswith(('600', '601', '603', '605', '688')):
            return s + '.SS'  # 沪市
        else:
            return s + '.SZ'  # 默认深市
    else:
        # 提取6位数字并添加后缀
        m = re.search(r'(\d{6})', s)
        if m:
            code = m.group(1)
            if code.startswith(('000', '002', '003', '300')):
                return code + '.SZ'
            elif code.startswith(('600', '601', '603', '605', '688')):
                return code + '.SS'
            else:
                return code + '.SZ'
        return s

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

        

        
    # 7. 20日乖离率10至90%的剔除 
    log.info('开始乖离率筛选，输入股票数量: %d' % len(valid_stocks))
    
    # 获取价格数据，增加异常保护
    try:
        price_data = get_history(20, '1d', ['close'], security_list=valid_stocks)
        current_data = get_history(1, '1d', ['close'], security_list=valid_stocks)
        
        if price_data is None or getattr(price_data, 'empty', False):
            log.warning('无法获取20日历史价格数据，跳过乖离率筛选')
            return valid_stocks
        if current_data is None or getattr(current_data, 'empty', False):
            log.warning('无法获取当前价格数据，跳过乖离率筛选')
            return valid_stocks
        
        # 尽量给出数据量级，便于排查
        try:
            log.info('成功获取价格数据，20日数据行数: %d，当前数据行数: %d' % (len(price_data), len(current_data)))
        except Exception:
            pass
    except Exception as e:
        log.error('获取价格数据时发生错误: %s' % str(e))
        return valid_stocks
    
    # 计算乖离率
    bias = {}
    failed_stocks = []
    for stock in valid_stocks:
        try:
            stock_price_data = price_data.query('code == "%s"' % stock)['close']
            stock_current_data = current_data.query('code == "%s"' % stock)['close']
            if getattr(stock_price_data, 'empty', False) or getattr(stock_current_data, 'empty', False):
                failed_stocks.append((stock, '数据为空'))
                continue
            ma20 = stock_price_data.mean()
            current_price = stock_current_data.iloc[0]
            if ma20 > 0 and not np.isnan(ma20) and not np.isnan(current_price):
                bias[stock] = (current_price - ma20) / ma20 * 100
            else:
                failed_stocks.append((stock, '无效数据: ma20=%s, current=%s' % (ma20, current_price)))
        except Exception as e:
            failed_stocks.append((stock, '计算异常: %s' % str(e)))
            continue
    
    if failed_stocks:
        log.info('乖离率计算失败的股票数量: %d' % len(failed_stocks))
        # 可按需打开详细日志
        # log.debug('失败详情: %s' % failed_stocks[:5])
    
    if not bias:
        log.warning('所有股票的乖离率计算都失败，返回原股票列表')
        return valid_stocks
    
    bias_values = list(bias.values())
    # 根据样本量动态选择分位范围
    if len(bias_values) < 10:
        lower = np.percentile(bias_values, 5)
        upper = np.percentile(bias_values, 95)
        log.info('股票数量较少(%d只)，放宽乖离率筛选条件至5%%-95%%' % len(bias_values))
    else:
        lower = np.percentile(bias_values, 10)
        upper = np.percentile(bias_values, 90)
    
    try:
        log.info('乖离率筛选范围: %.2f%% 到 %.2f%%' % (lower, upper))
    except Exception:
        pass
    
    valid_stocks = [stock for stock in valid_stocks if stock in bias and lower <= bias[stock] <= upper]
    
    if not valid_stocks:
        log.warning('乖离率筛选后股票池为空，可能筛选条件过于严格')
        # 回退：至少返回有乖离率数据的股票，避免空列表
        valid_stocks = list(bias.keys())
        log.info('返回所有有乖离率数据的股票，数量: %d' % len(valid_stocks))
    
    log.info('乖离率筛选后数量: %d' % len(valid_stocks))
        
    # 8. TTM股息等于0的剔除
    try:
        # 获取估值数据中的滚动股息率
        dividend_data = get_fundamentals(valid_stocks, 'valuation', fields=['dividend_ratio'])
        # log.info('获取到的股息率数据类型: %s' % type(dividend_data))
        
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
        # log.info('获取到的财务数据类型: %s' % type(financial_data))
        
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
                                   fields=['total_liability', 'total_assets'])
        
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
                        # log.debug(f"股票 {stock} 资产负债率 {debt_ratio:.2f}% <= 70%，资产负债分别为 {total_liability:.2f}万, {total_assets:.2f}万 保留 ")
                    else:
                        removed_stocks.append((stock, debt_ratio))
                        # log.debug("股票 {} 资产负债率 {:.2f}% > 70%，剔除".format(stock, debt_ratio))
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
        # if removed_stocks:
        #     log.info('以下 {} 只股票因资产负债率过高被剔除:'.format(len(removed_stocks)))
        #     for stock, ratio in removed_stocks[:10]:  # 只显示前10只
        #         log.info('  {}: 资产负债率 {:.2f}%'.format(stock, ratio))
        #     if len(removed_stocks) > 10:
        #         log.info('  ... 还有 {} 只股票被剔除'.format(len(removed_stocks) - 10))
        
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
    
# 6. 剔除换手率最高的50%
    log.info("==========开始换手率筛选==========")
    log.info("输入股票数量: {}".format(len(valid_stocks)))
    try:
        # 使用PTrade API获取估值数据中的换手率
        turnover_data = get_fundamentals(valid_stocks, 'valuation', 
                                       fields=['turnover_rate'])
        
        if turnover_data is None or len(turnover_data) == 0:
            log.warning('获取换手率数据为空，跳过换手率筛选')
            return []
            
        # 处理换手率数据
        turnovers = {}
        invalid_data_count = 0
        
        # 根据返回数据格式处理
        if isinstance(turnover_data, dict):
            for stock in valid_stocks:
                try:
                    if stock in turnover_data:
                        stock_data = turnover_data[stock]
                        turnover_rate = stock_data.get('turnover_rate', '0%')
                        
                        # 处理带%的字符串格式
                        if isinstance(turnover_rate, str):
                            turnover_rate = float(turnover_rate.strip('%'))
                        else:
                            turnover_rate = float(turnover_rate)
                            
                        if turnover_rate > 0:
                            turnovers[stock] = turnover_rate
                            # log.debug("股票 {} 换手率: {:.2f}%".format(stock, turnover_rate))
                        else:
                            log.debug("股票 {} 换手率为0，跳过".format(stock))
                            invalid_data_count += 1
                    else:
                        log.warning("股票 {} 未找到换手率数据".format(stock))
                        invalid_data_count += 1
                        
                except Exception as e:
                    log.error("处理股票 {} 换手率时出错: {}".format(stock, str(e)))
                    invalid_data_count += 1
                    continue
                    
        else:  # DataFrame格式
            for stock in valid_stocks:
                try:
                    # 根据API文档，返回的DataFrame中股票代码字段是secu_code
                    if hasattr(turnover_data, 'columns') and 'secu_code' in turnover_data.columns:
                        stock_data = turnover_data[turnover_data['secu_code'] == stock]
                    else:
                        # 备用方案：使用索引查找
                        stock_data = turnover_data[turnover_data.index == stock] if stock in turnover_data.index else pd.DataFrame()
                    
                    if stock_data.empty:
                        log.warning("股票 {} 未找到换手率数据".format(stock))
                        invalid_data_count += 1
                        continue
                        
                    if 'turnover_rate' not in stock_data.columns:
                        log.warning("股票 {} 缺少换手率字段".format(stock))
                        invalid_data_count += 1
                        continue
                        
                    turnover_rate = stock_data['turnover_rate'].iloc[0]
                    
                    # 处理带%的字符串格式
                    if isinstance(turnover_rate, str):
                        turnover_rate = float(turnover_rate.strip('%'))
                    else:
                        turnover_rate = float(turnover_rate)
                        
                    if turnover_rate > 0:
                        turnovers[stock] = turnover_rate
                        # log.debug("股票 {} 换手率: {:.2f}%".format(stock, turnover_rate))
                    else:
                        log.debug("股票 {} 换手率为0，跳过".format(stock))
                        invalid_data_count += 1
                        
                except Exception as e:
                    log.error("处理股票 {} 换手率时出错: {}".format(stock, str(e)))
                    invalid_data_count += 1
                    continue
                
        if not turnovers:
            log.warning('没有有效的换手率数据，跳过换手率筛选')
            return []
        
        log.info('成功获取换手率数据的股票数量: {}, 无效数据数量: {}'.format(len(turnovers), invalid_data_count))
        
        # 统计换手率分布
        turnover_values = list(turnovers.values())
        log.info("换手率统计 - 最小值: {:.2f}%, 最大值: {:.2f}%, 平均值: {:.2f}%".format(
            min(turnover_values), max(turnover_values), sum(turnover_values)/len(turnover_values)))
        
        # 方法：直接按换手率排序，剔除最高的50%
        # 将股票按换手率从高到低排序
        sorted_stocks = sorted(turnovers.items(), key=lambda x: x[1], reverse=True)
        # log.info('股票总数: {}'.format(len(sorted_stocks)))
        
        # 计算要剔除的股票数量（最高的50%）
        remove_count = len(sorted_stocks) // 2
        # log.info('计划剔除换手率最高的 {} 只股票（占比 {:.1f}%）'.format(
        #     remove_count, remove_count * 100.0 / len(sorted_stocks)))
        
        # 获取被剔除的股票（换手率最高的50%）
        high_turnover_stocks = sorted_stocks[:remove_count]
        
        # 获取保留的股票（换手率较低的50%）
        keep_stocks = sorted_stocks[remove_count:]
        
        # 记录阈值（最后一个被剔除股票的换手率）
        if high_turnover_stocks:
            threshold = high_turnover_stocks[-1][1]  # 最后一个被剔除股票的换手率
            log.info('换手率剔除阈值: {:.2f}%（高于此值的股票被剔除）'.format(threshold))
        else:
            threshold = 0
            log.info('无股票被剔除')
        
        # 保留的股票列表
        filtered_stocks = [stock for stock, rate in keep_stocks if stock in valid_stocks]
        
        # 记录被剔除的股票
        if high_turnover_stocks:
            log.info('以下 {} 只股票因换手率过高被剔除:'.format(len(high_turnover_stocks)))
            for stock, rate in high_turnover_stocks[:10]:  # 只显示前10只
                log.info('  {}: 换手率 {:.2f}%'.format(stock, rate))
            if len(high_turnover_stocks) > 10:
                log.info('  ... 还有 {} 只股票被剔除'.format(len(high_turnover_stocks) - 10))
        
        if not filtered_stocks:
            log.warning('换手率筛选后股票池为空')
            return []
        
        log.info('换手率筛选完成 - 剔除股票数: {}, 保留股票数: {}'.format(
            len(high_turnover_stocks), len(filtered_stocks)))
        log.info("==========换手率筛选结束==========")
        
        # 对筛选后的股票按股票代码前6位数字排序
        filtered_stocks = sorted(filtered_stocks, key=lambda x: x[:6])
        # log.info('股票列表已按代码前6位排序，保留股票: {}'.format(filtered_stocks))
        
        valid_stocks = filtered_stocks
        
    except Exception as e:
        log.error('获取换手率数据时发生错误: {}'.format(str(e)))
        log.error('错误详情: {}'.format(traceback.format_exc()))
        return []
        
    log.info('最终筛选后数量: %d' % len(valid_stocks))
    # log.info('最终筛选后股票: %s' % valid_stocks) 
    
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
                    
                    if stock.startswith('68'):
                        is_excluded = True
                        reason = '科创板'
                    elif stock.startswith('3'):
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
                
        valid_stocks = filtered_stocks
    
        log.info('科创板等剔除后数量: %d' % len(valid_stocks))
        # log.info('科创板等剔除后股票: %s' % valid_stocks)
        
    except Exception as e:
        log.error('获取股票信息时发生错误: %s' % str(e))
        return []
    
    return valid_stocks

def handle_data(context, data):
    """
    交易逻辑主函数 - 周五选股轮换策略
    每周五选股5只，与上周五选股对比：
    - 保留重复的股票（不卖出）
    - 卖出上周五不重复的股票
    - 买入本周五新增的股票
    
    特殊逻辑：
    - 如果到达交易结束日期，执行清仓操作
    - 如果交易结束日期是周五，不执行买入操作，只执行清仓
    """
    # 检查是否到达交易结束日期
    today = context.current_dt.date()
    trading_end_date = getattr(context, 'trading_end_date', None)
    
    if trading_end_date and today >= trading_end_date:
        log.info('已到达交易结束日期 %s，执行清仓操作' % trading_end_date)
        # 执行清仓操作
        try:
            current_positions = get_positions()
            if current_positions:
                log.info('开始清仓，当前持仓: %s' % list(current_positions.keys()))
                for pos_key, position in current_positions.items():
                    # 检查持仓数量，避免重复清仓和重复log
                    position_amount = 0
                    if hasattr(position, 'total_amount'):
                        position_amount = position.total_amount
                    elif hasattr(position, 'amount'):
                        position_amount = position.amount
                    
                    if position_amount > 0:
                        order_target_percent(pos_key, 0)
                        log.info('清仓股票: %s (持仓数量: %s)' % (pos_key, position_amount))
                log.info('清仓操作完成')
            else:
                log.info('当前无持仓，无需清仓')
        except Exception as e:
            log.error('清仓操作失败: %s' % str(e))
        return
    
    # 仅在每周一执行选股和调仓
    try:
        current_time = context.current_dt.time()
        weekday = context.current_dt.weekday()
        weekly_buy_weekday = getattr(context, 'weekly_buy_weekday', 0)
        
        if weekday != weekly_buy_weekday:
            # 当天首次提示，后续同日不再重复打印
            last_log_date = getattr(context, 'last_non_select_log_date', None)
            if last_log_date != today:
                log.info('非选股日(weekday=%d)，跳过选股与调仓' % weekday)
                try:
                    context.last_non_select_log_date = today
                except Exception:
                    pass
            return
            
        # 检查是否为开盘后5分钟（A股开盘时间为9:30，开盘后5分钟为9:35）
        market_open_time = datetime.time(9, 30)  # 9:30开盘
        buy_time = datetime.time(9, 35)  # 开盘后5分钟
        
        if current_time < buy_time:
            # 当天首次提示，后续同日不再重复打印
            last_log_date = getattr(context, 'last_not_buy_time_log_date', None)
            if last_log_date != today:
                log.info('当前时间%s未到买入时间%s，跳过交易' % (current_time, buy_time))
                try:
                    context.last_not_buy_time_log_date = today
                except Exception:
                    pass
            return
            
        if getattr(context, 'last_buy_date', None) == today:
            # 当天首次提示，后续同日不再重复打印
            last_log_date = getattr(context, 'last_already_selected_log_date', None)
            if last_log_date != today:
                log.info('今日已完成周五选股，跳过重复执行')
                try:
                    context.last_already_selected_log_date = today
                except Exception:
                    pass
            return
    except Exception as e:
        log.warning('选股日判断异常: %s，允许本次继续执行' % str(e))
    
    stock_pool = get_stock_pool(context)

    # 若选股结果为空，直接返回，避免不必要的下单逻辑
    if not stock_pool:
        log.info('选股结果为空，本轮不进行调仓')
        return
    
    # 获取排序需要的数据
    try:
        # 1. 获取收盘价数据
        price_data = get_history(1, '1d', ['close'], security_list=stock_pool)
        # log.info('价格数据类型: %s' % type(price_data))
        # log.info('价格数据形状: %s' % str(price_data.shape if hasattr(price_data, 'shape') else 'N/A'))
        # log.info('价格数据列名: %s' % str(price_data.columns.tolist() if hasattr(price_data, 'columns') else 'N/A'))
        if hasattr(price_data, 'head'):
            log.debug('价格数据前几行:\n%s' % str(price_data))
        
        # 2. 获取股息率数据
        dividend_data = get_fundamentals(stock_pool, 'valuation', fields=['dividend_ratio'])
        # log.info('股息率数据类型: %s' % type(dividend_data))
        if hasattr(dividend_data, 'head'):
            log.debug('股息率数据前几行:\n%s' % str(dividend_data.head()))
        
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
            
            # 获取净利润数据：按年份查询，取最近两年内所有季度以便计算TTM
            financial_data = get_fundamentals(
                stock_pool,
                'income_statement',
                fields=['np_parent_company_owners', 'net_profit', 'end_date', 'publ_date'],
                start_year=str(current_year-2),
                end_year=str(current_year)
            )
            
            # 获取股息率数据 - 估值数据只支持按天查询模式
            # 使用前一交易日的数据，确保数据可用性
            dividend_data = get_fundamentals(
                stock_pool, 
                'valuation', 
                fields=['dividend_ratio', 'total_value'],  # 移除secu_code，因为它通常在索引中
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
            # log.info(f'财务数据结构: 类型={type(financial_data)}, 形状={financial_data.shape if hasattr(financial_data, "shape") else "无形状"}')
            # log.info(f'财务数据列: {list(financial_data.columns) if hasattr(financial_data, "columns") else "无列信息"}')
            # if hasattr(financial_data, 'index'):
            #     log.info(f'财务数据索引: {financial_data.index.names if hasattr(financial_data.index, "names") else "单级索引"}')
            
            # log.info(f'股息数据结构: 类型={type(dividend_data)}, 形状={dividend_data.shape if hasattr(dividend_data, "shape") else "无形状"}')
            # log.info(f'股息数据列: {list(dividend_data.columns) if hasattr(dividend_data, "columns") else "无列信息"}')
            # if hasattr(dividend_data, 'index'):
            #     log.info(f'股息数据索引: {dividend_data.index.names if hasattr(dividend_data.index, "names") else "单级索引"}')
            
        except Exception as e:
            log.error('获取财务和股息数据时出错: %s' % str(e))
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
                                    break
                            except:
                                continue
                    else:
                        # 单级索引，直接查找
                        if stock_code in financial_df.index:
                            stock_financial = financial_df.loc[stock_code]
                            log.info('股票 %s 在财务数据单级索引中找到' % stock_code)
                    
                    if stock_financial is not None and not getattr(stock_financial, 'empty', False):
                        # 优先使用归属于母公司股东的净利润，其次使用净利润
                        if isinstance(stock_financial, pd.Series):
                            if 'np_parent_company_owners' in stock_financial.index and pd.notna(stock_financial['np_parent_company_owners']):
                                net_profit = float(stock_financial['np_parent_company_owners'])
                            elif 'net_profit' in stock_financial.index and pd.notna(stock_financial['net_profit']):
                                net_profit = float(stock_financial['net_profit'])
                            else:
                                net_profit = 0.0
                        else:
                            # DataFrame：按日期排序后取最近四期汇总为TTM净利润
                            try:
                                sf = stock_financial.copy()
                                if 'publ_date' in sf.columns:
                                    sf = sf.sort_values('publ_date')
                                elif 'end_date' in sf.columns:
                                    sf = sf.sort_values('end_date')
                                # 选择利润列
                                profit_col = 'np_parent_company_owners' if ('np_parent_company_owners' in sf.columns and sf['np_parent_company_owners'].notna().any()) else ('net_profit' if ('net_profit' in sf.columns and sf['net_profit'].notna().any()) else None)
                                if profit_col is not None:
                                    profit_series = pd.to_numeric(sf[profit_col], errors='coerce').dropna()
                                    if len(profit_series) > 0:
                                        net_profit = float(profit_series.tail(4).sum())
                                    else:
                                        net_profit = 0.0
                                else:
                                    net_profit = 0.0
                            except Exception as _e:
                                log.warning('计算TTM净利润异常: %s' % str(_e))
                                # 回退到最后一个非空值
                                if 'np_parent_company_owners' in stock_financial.columns and stock_financial['np_parent_company_owners'].notna().any():
                                    net_profit = float(stock_financial['np_parent_company_owners'].dropna().iloc[-1])
                                elif 'net_profit' in stock_financial.columns and stock_financial['net_profit'].notna().any():
                                    net_profit = float(stock_financial['net_profit'].dropna().iloc[-1])
                                else:
                                    net_profit = 0.0
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
                    
                    if stock_dividend is not None and not getattr(stock_dividend, 'empty', False):
                        # 从股息率和市值计算分红金额
                        dividend_ratio = 0
                        market_value = 0
                        
                        if isinstance(stock_dividend, pd.Series):
                            if 'dividend_ratio' in stock_dividend.index:
                                div_ratio_val = stock_dividend['dividend_ratio']
                                # 统一转为标量，避免Series布尔歧义
                                if isinstance(div_ratio_val, pd.Series):
                                    div_ratio_val = div_ratio_val.dropna()
                                    div_ratio_val = div_ratio_val.iloc[-1] if not div_ratio_val.empty else np.nan
                                if isinstance(div_ratio_val, str):
                                    div_ratio_val = div_ratio_val.strip('%')
                                div_ratio_float = pd.to_numeric(div_ratio_val, errors='coerce')
                                dividend_ratio = float(div_ratio_float) if not pd.isna(div_ratio_float) and float(div_ratio_float) != 0 else 0
                            if 'total_value' in stock_dividend.index:
                                total_val = stock_dividend['total_value']
                                if isinstance(total_val, pd.Series):
                                    total_val = total_val.dropna()
                                    total_val = total_val.iloc[-1] if not total_val.empty else np.nan
                                total_val_float = pd.to_numeric(total_val, errors='coerce')
                                market_value = float(total_val_float) if not pd.isna(total_val_float) and float(total_val_float) != 0 else 0
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
                
                # 计算股息支付率（记录原始与截断值以便诊断）
                net_profit_val = float(net_profit) if pd.notna(net_profit) else 0.0
                dividend_amount_val = float(dividend_amount) if pd.notna(dividend_amount) else 0.0
                
                if net_profit_val > 0 and dividend_amount_val > 0:
                    payout_ratio = (dividend_amount_val / net_profit_val) * 100
                    final_ratio = min(payout_ratio, 100)
                    log.info('股票 %s 股息支付率原始: %.2f%%, 截断: %.2f%% (净利润TTM: %.2f, 分红金额TTM: %.2f)' % (stock_code, payout_ratio, final_ratio, net_profit_val, dividend_amount_val))
                    return final_ratio
                else:
                    log.info('股票 %s 股息支付率为0 (净利润TTM: %.2f, 分红金额TTM: %.2f)' % (stock_code, net_profit_val, dividend_amount_val))
                    return 0
            except Exception as e:
                log.error('计算股票%s股息支付率时发生错误: %s' % (stock_code, str(e)))
                return 0
        
        # 处理每个股票的因子数据
        for stock in stock_pool:
            try:
                # log.info('开始处理股票 %s 的因子数据' % stock)
                
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
                    log.info('股票 %s' % (price_data.columns))
                    if 'code' in price_data.columns:
                        stock_price_data = price_data[price_data['code'] == stock]
                        if not stock_price_data.empty:
                            close_price = float(stock_price_data['close'].iloc[0])
                    # 如果是以股票代码为列名的格式
                    elif stock in price_data.columns:
                        close_price = float(price_data[stock].iloc[0])
                
                stock_factors[stock]['close_price'] = close_price
                log.info('股票 %s 收盘价: %.2f' % (stock, close_price))
                
                # 2. 处理股息率数据（从dividend_data中获取）
                # log.info('开始处理股票 %s 的股息率数据' % stock)
                if not dividend_data.empty:
                    stock_dividend = None
                    
                    # 检查索引结构并筛选该股票的数据
                    if hasattr(dividend_data.index, 'levels'):
                        for level in range(len(dividend_data.index.levels)):
                            try:
                                if stock in dividend_data.index.get_level_values(level):
                                    stock_dividend = dividend_data.xs(stock, level=level)
                                    # log.info('股票 %s 在股息数据第%d级索引中找到' % (stock, level))
                                    break
                            except:
                                continue
                    else:
                        # 单级索引，直接查找
                        if stock in dividend_data.index:
                            stock_dividend = dividend_data.loc[stock]
                            log.info('股票 %s 在股息数据单级索引中找到' % stock)
                    
                    if stock_dividend is not None and not stock_dividend.empty:
                        # log.info('股票 %s 股息数据类型: %s' % (stock, type(stock_dividend)))
                        # log.info('股票 %s 股息数据内容: %s' % (stock, str(stock_dividend)))
                        
                        # 检查数据类型并处理股息率
                        if isinstance(stock_dividend, pd.Series):
                            # 如果是Series，直接通过索引访问
                            if 'dividend_ratio' in stock_dividend.index:
                                div_ratio_val = stock_dividend['dividend_ratio']
                                # 统一转为标量，避免Series布尔歧义
                                if isinstance(div_ratio_val, pd.Series):
                                    div_ratio_val = div_ratio_val.dropna()
                                    div_ratio_val = div_ratio_val.iloc[-1] if not div_ratio_val.empty else np.nan
                                if isinstance(div_ratio_val, str):
                                    div_ratio_val = div_ratio_val.strip('%')
                                div_ratio_float = pd.to_numeric(div_ratio_val, errors='coerce')
                                stock_factors[stock]['dividend_ratio'] = float(div_ratio_float) if not pd.isna(div_ratio_float) and float(div_ratio_float) != 0 else 0
                                # log.info('股票 %s 股息率(Series): %.2f%%' % (stock, stock_factors[stock]['dividend_ratio']))
                            
                            if 'total_value' in stock_dividend.index:
                                market_val = stock_dividend['total_value']
                                if isinstance(market_val, pd.Series):
                                    market_val = market_val.dropna()
                                    market_val = market_val.iloc[-1] if not market_val.empty else np.nan
                                market_val_float = pd.to_numeric(market_val, errors='coerce')
                                stock_factors[stock]['market_value'] = float(market_val_float) if not pd.isna(market_val_float) and float(market_val_float) != 0 else float('inf')
                                # log.info('股票 %s 市值(Series): %.2f万元' % (stock, stock_factors[stock]['market_value']/10000))
                        elif isinstance(stock_dividend, pd.DataFrame):
                            # 如果是DataFrame，检查列
                            if 'dividend_ratio' in stock_dividend.columns:
                                div_ratio = stock_dividend['dividend_ratio'].iloc[0]
                                if isinstance(div_ratio, str):
                                    stock_factors[stock]['dividend_ratio'] = float(div_ratio.strip('%'))
                                else:
                                    stock_factors[stock]['dividend_ratio'] = float(div_ratio) if pd.notna(div_ratio) and div_ratio != 0 else 0
                                # log.info('股票 %s 股息率(DataFrame): %.2f%%' % (stock, stock_factors[stock]['dividend_ratio']))
                            
                            if 'total_value' in stock_dividend.columns:
                                market_val = stock_dividend['total_value'].iloc[0]
                                stock_factors[stock]['market_value'] = float(market_val) if pd.notna(market_val) and market_val != 0 else float('inf')
                                # log.info('股票 %s 市值(DataFrame): %.2f万元' % (stock, stock_factors[stock]['market_value']/10000))
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
                # log.info('股票%s因子数据汇总: 收盘价=%.2f, 股息率=%.2f%%, 市值=%.2f亿, 股息支付率=%.2f%%' % 
                #         (stock, stock_factors[stock]["close_price"], 
                #          stock_factors[stock]["dividend_ratio"],
                #          stock_factors[stock]["market_value"]/100000000,
                #          stock_factors[stock]["payout_ratio"]))
                
            except Exception as e:
                log.error(f'处理股票{stock}的因子数据时发生错误: {str(e)}')
                log.error(traceback.format_exc())
                # 保持默认值，继续处理下一个股票
                continue

        # 对每个因子进行排序并分配分数
        # 基于排名的加权总分：每个因子按有利方向排名，
        # 顶部得分为N，次序依次递减到1；总分为五个因子分数之和
        N = len(stock_pool)
        sorted_stocks = []
        if N == 0:
            log.warning('多因子排序阶段输入股票为空')
        else:
            # 为避免缺失值导致异常，使用安全取值函数
            def _close_val(s):
                return stock_factors.get(s, {}).get('close_price', float('inf'))
            def _div_val(s):
                return stock_factors.get(s, {}).get('dividend_ratio', 0)
            def _payout_val(s):
                return stock_factors.get(s, {}).get('payout_ratio', 0)
            def _insider_val(s):
                return stock_factors.get(s, {}).get('insider_holding', 0)
            def _mcap_val(s):
                return stock_factors.get(s, {}).get('market_value', float('inf'))
            
            # 按有利方向进行排序
            close_sorted   = sorted(stock_pool, key=_close_val)                    # 低价优先
            dividend_sorted= sorted(stock_pool, key=_div_val, reverse=True)        # 股息率高优先
            # 使用股息支付率参与计分
            payout_sorted  = sorted(stock_pool, key=_payout_val, reverse=True)     # 支付率高优先（可调整方向）
            insider_sorted = []                                                    # 不使用
            mcap_sorted    = sorted(stock_pool, key=_mcap_val)                     # 市值小优先
            
            # 将排序转换为分数映射：rank 0 -> N, rank 1 -> N-1 ...
            def make_score_map(sorted_list):
                return dict((s, N - idx) for idx, s in enumerate(sorted_list))
            
            score_close   = make_score_map(close_sorted)
            score_div     = make_score_map(dividend_sorted)
            score_payout  = make_score_map(payout_sorted)
            score_insider = dict((s, 0) for s in stock_pool)
            score_mcap    = make_score_map(mcap_sorted)
            
            # 计算总分并记录日志
            for stock in stock_pool:
                total_score = (
                    score_close.get(stock, 0) +
                    score_div.get(stock, 0) +
                    score_payout.get(stock, 0) +
                    score_insider.get(stock, 0) +
                    score_mcap.get(stock, 0)
                )
                log.info('total_score: %s = %d (close=%d, div=%d, payout=%d, insider=%d, mcap=%d)' % (
                    stock,
                    total_score,
                    score_close.get(stock, 0),
                    score_div.get(stock, 0),
                    score_payout.get(stock, 0),
                    score_insider.get(stock, 0),
                    score_mcap.get(stock, 0)
                ))
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
    
    log.debug('选股结果名称2: %s' % get_stock_info(stock_pool, ['stock_name']))
    
    # 选取前5只股票进行交易
    selection_count = getattr(context, 'selection_count', 5)
    top_stocks = stock_pool[:selection_count] if len(stock_pool) >= selection_count else stock_pool
    log.info('选取前%d只股票进行交易: %s' % (len(top_stocks), get_stock_info(top_stocks, ['stock_name'])))
    log.info('前%d只股票详细信息:' % len(top_stocks))
    for i, stock in enumerate(top_stocks, 1):
        if stock in stock_factors:
            stock_info = get_stock_info([stock], ['stock_name'])[stock]
            log.info(f"第{i}名: {stock}({stock_info['stock_name']}): "
                    f"收盘价={stock_factors[stock]['close_price']:.2f}, "
                    f"股息率={stock_factors[stock]['dividend_ratio']:.2f}%, "
                    f"总市值={stock_factors[stock]['market_value']/100000000:.2f}亿")
    
    # 与上周一选股对比：保留重复、卖出不重复、买入新增
    # 获取上周五选股结果，如果为空则尝试从当前持仓回退
    last_list = getattr(context, 'last_friday_selection', [])
    if not last_list:
        # 回退：使用当前持仓作为"上周选择"
        try:
            current_positions = get_positions()
            if current_positions:
                last_list = []
                for pos_key, position in current_positions.items():
                    if hasattr(position, 'total_amount') and position.total_amount > 0:
                        last_list.append(_normalize_local(pos_key))
                    elif hasattr(position, 'amount') and position.amount > 0:
                        last_list.append(_normalize_local(pos_key))
                log.info(f'未找到last_friday_selection，使用当前持仓回退为上周选择: {last_list}')
            else:
                log.info('当前无持仓，首次选股')
        except Exception as e:
            log.warning(f'获取当前持仓失败: {str(e)}，使用空列表作为上周选择')
            last_list = []
    
    # 规范化代码进行比对
    last_selection = set(_normalize_local(s) for s in last_list)
    current_selection = set(_normalize_local(s) for s in top_stocks)
    overlap = sorted(list(last_selection & current_selection))
    to_sell = sorted(list(last_selection - current_selection))
    to_buy = sorted(list(current_selection - last_selection))
    
    if last_selection:
        log.info('与上周五选股对比: 保留(重复)=%s, 卖出(不重复)=%s, 买入(新增)=%s' % (
            get_stock_info(overlap, ['stock_name']) if overlap else {},
            get_stock_info(to_sell, ['stock_name']) if to_sell else {},
            get_stock_info(to_buy, ['stock_name']) if to_buy else {}
        ))
    else:
        log.info('首次周五选股，无上周对比，目标买入: %s' % get_stock_info(top_stocks, ['stock_name']))

    # 告知调仓逻辑保留 overlap，不对其做再平衡；仅卖出 to_sell，买入 to_buy
    try:
        context.rotation_keep_codes = overlap
        log.info(f'本次保留并不再平衡的股票: {overlap}')
    except Exception:
        context.rotation_keep_codes = overlap

    # 仅为新增(to_buy)构建目标权重，避免对重复(overlap)做再平衡
    target_position = {}
    if to_buy:
        # 设置权重为当前选择数量的等权，确保总权重<=100%
        weight = 1.0 / max(len(top_stocks), 1)
        for stock in to_buy:
            target_position[stock] = weight
        log.info(f'为新增{len(to_buy)}只股票设置目标权重，每只权重: {weight:.2%}')
    else:
        log.info('本周选股与上周完全重合，无需新增买入')

    # 调整仓位：将非保留的上周股票卖出，买入新增股票；保留重复股票不动
    adjust_position(context, target_position)
    
    # 记录本次已在今日执行建仓，并更新上周一选股缓存
    try:
        context.last_buy_date = context.current_dt.date()
        context.last_friday_selection = top_stocks
        context.last_selection_date = context.current_dt.date()
    except Exception:
        pass

    context.day_counter += 1
    return

def get_market_open_price(stock, context):
    """
    获取开盘后5分钟（9:35）的价格作为交易价格
    """
    try:
        # 获取当日9:35的分钟级数据
        current_date = context.current_dt.date()
        start_time = datetime.datetime.combine(current_date, datetime.time(9, 35))
        end_time = start_time + datetime.timedelta(minutes=1)
        
        # 使用get_history获取9:35这一分钟的数据
        price_data = get_history(1, '5m', ['close'], security_list=[stock], 
                               include=True)  # include=True包含当前未结束的周期
        
        if not price_data.empty:
            stock_data = price_data[price_data['code'] == stock]
            if not stock_data.empty:
                market_open_price = stock_data['close'].iloc[-1]  # 取最新的价格
                log.debug(f'股票{stock}开盘后5分钟价格: {market_open_price:.2f}元')
                return market_open_price
        
        # 如果无法获取9:35的价格，尝试获取当前价格作为备选
        current_data = get_history(1, '1d', ['close'], security_list=[stock])
        if not current_data.empty:
            stock_data = current_data[current_data['code'] == stock]
            if not stock_data.empty:
                fallback_price = stock_data['close'].iloc[0]
                log.warning(f'无法获取股票{stock}开盘后5分钟价格，使用当日收盘价: {fallback_price:.2f}元')
                return fallback_price
                
    except Exception as e:
        log.error(f'获取股票{stock}开盘后5分钟价格失败: {str(e)}')
    
    return None

def adjust_position(context, target_position):
    """调整持仓到目标仓位
    
    基于API文档优化的版本：
    1. 使用order_target_value()替代order_target()避免持仓同步问题
    2. 改进价格获取和错误处理
    3. 添加订单状态检查
    4. 优化下单逻辑和日志记录
    5. 添加订单执行状态监控
    """
    
    # 检查并取消未完成的订单，避免重复下单
    open_orders = get_open_orders()
    if open_orders:
        log.info(f'发现{len(open_orders)}个未完成订单，先取消以避免冲突')
        for order_id, order_info in open_orders.items():
            try:
                cancel_order(order_id)
                log.debug(f'已取消订单: {order_id} ({order_info.security})')
            except Exception as e:
                log.warning(f'取消订单{order_id}失败: {str(e)}')
    
    # 获取当前持仓和组合信息 - 使用API文档推荐的方法
    try:
        # 使用get_positions()获取所有持仓的Position对象字典
        current_positions = get_positions()
        log.debug(f'通过get_positions()获取到持仓数据: {len(current_positions)}只股票')
        if current_positions:
            log.debug(f'持仓股票列表: {list(current_positions.keys())}')
    except Exception as e:
        log.warning(f'get_positions()获取失败: {str(e)}，尝试使用context.portfolio.positions')
        # 备用方案：使用原来的方法
        current_positions = context.portfolio.positions

    # 初始化或获取延迟卖出集合（用于T+1或当日买入的情况）
    if not hasattr(context, 'deferred_sells'):
        context.deferred_sells = set()

    # 统一卖出前检查函数：可卖数量>0、非停牌、非当日买入
    def can_sell_stock(stock):
        try:
            # 可卖数量检查
            pos = get_position(stock)
            enable_amt = getattr(pos, 'enable_amount', 0) if pos else 0
            total_amt = getattr(pos, 'amount', 0) if pos else 0
            if enable_amt <= 0:
                return False, f'可卖数量为0(总持仓={total_amt})'

            # 停牌检查
            try:
                halt_status = get_stock_status(stock, 'HALT')
                if halt_status and halt_status.get(stock, False):
                    return False, '停牌中'
            except Exception:
                pass

            # 当日买入检查（T+1保护）
            try:
                trades = get_trades()
                if trades:
                    # 兼容多种返回结构
                    for t in trades if isinstance(trades, list) else trades.values():
                        sec = t.get('security') if isinstance(t, dict) else getattr(t, 'security', None)
                        side = t.get('side') if isinstance(t, dict) else getattr(t, 'side', None)
                        if sec == stock and str(side).upper() in ('BUY', 'B', 'BUY_OPEN'):
                            return False, '当日有买入成交(T+1)'
            except Exception:
                pass

            return True, '可卖检查通过'
        except Exception as e:
            return False, f'卖出前检查异常: {str(e)}'

    # 优先处理延迟卖出队列（若条件已满足则尝试清仓）
    if context.deferred_sells:
        processed = []
        for stock in list(context.deferred_sells):
            # 检查是否在保留集合中
            normalized_stock = _normalize_local(stock)
            if normalized_stock in keep_codes:
                log.info(f'延迟卖出队列中的股票{stock}在保留集合中，移出队列')
                processed.append(stock)
                continue
                
            ok, reason = can_sell_stock(stock)
            if ok:
                try:
                    # 获取开盘后5分钟的价格作为限价
                    market_open_price = get_market_open_price(stock, context)
                    if market_open_price:
                        # 使用开盘后5分钟价格作为限价进行卖出
                        order_id = order_target_value(stock, 0, limit_price=market_open_price)
                        log.info(f'延迟卖出使用开盘后5分钟价格{market_open_price:.2f}元作为限价')
                    else:
                        # 如果无法获取开盘后5分钟价格，使用市价单
                        order_id = order_target_value(stock, 0)
                        log.warning(f'延迟卖出无法获取开盘后5分钟价格，使用市价单')
                    
                    if order_id:
                        log.info(f'延迟卖出执行成功: {stock} (订单ID: {order_id})')
                        processed.append(stock)
                    else:
                        log.warning(f'延迟卖出提交失败: {stock}')
                except Exception as e:
                    log.warning(f'延迟卖出执行异常: {stock}, {str(e)}')
            else:
                log.info(f'延迟卖出继续等待: {stock}，原因: {reason}')
        for s in processed:
            context.deferred_sells.discard(s)
        log.debug(f'通过context.portfolio.positions获取到持仓数据: {len(current_positions)}只股票')
    
    portfolio_value = context.portfolio.portfolio_value
    available_cash = context.portfolio.cash
    
    # 打印详细的持仓信息用于调试
    log.info(f'组合总价值: {portfolio_value:.2f}元')
    log.debug(f'可用现金: {available_cash:.2f}元')
    
    if current_positions:
        log.debug('当前持仓详情:')
        for stock, position in current_positions.items():
            if hasattr(position, 'total_amount') and position.total_amount > 0:
                log.debug(f'  {stock}: 数量={position.total_amount}, 价格={getattr(position, "last_sale_price", "N/A")}, 价值={getattr(position, "value", "N/A")}')
            elif hasattr(position, 'amount') and position.amount > 0:
                log.debug(f'  {stock}: 数量={position.amount}, 价格={getattr(position, "last_sale_price", "N/A")}, 价值={getattr(position, "value", "N/A")}')
    else:
        log.info('当前无持仓或持仓数据为空')
    
    # 验证组合状态
    if portfolio_value <= 0:
        log.error('组合总价值为0或负数，无法进行调仓')
        return
    
    if len(target_position) == 0:
        log.warning('目标持仓为空，将清空所有持仓')
    
    # 获取保留股票集合（规范化代码）
    keep_codes = getattr(context, 'rotation_keep_codes', set())
    if keep_codes:
        log.debug(f'本次调仓将保留以下股票不卖出: {keep_codes}')
    
    # 第一步：卖出不在目标池且不在保留集合的股票（基于API的可卖数量）
    stocks_to_sell = []
    if current_positions:
        for stock in current_positions:
            # 规范化股票代码进行比较
            normalized_stock = _normalize_local(stock)
            
            # 使用get_position()获取单个股票的详细持仓信息
            try:
                position = get_position(stock)
                if position:
                    sellable_amount = getattr(position, 'enable_amount', 0)
                    total_amount = getattr(position, 'amount', 0) or getattr(position, 'total_amount', 0)

                    log.debug(f'股票{stock}({normalized_stock}): 总持仓={total_amount}, 可卖数量={sellable_amount}')

                    # 检查是否需要卖出：不在目标池且不在保留集合
                    should_sell = (stock not in target_position and 
                                 normalized_stock not in keep_codes)
                    
                    if sellable_amount > 0 and should_sell:
                        stocks_to_sell.append(stock)
                        log.debug(f'股票{stock}加入卖出列表: 可卖数量={sellable_amount}')
                    elif sellable_amount > 0 and normalized_stock in keep_codes:
                        log.debug(f'股票{stock}在保留集合中，跳过卖出')
                    elif total_amount > 0 and sellable_amount == 0 and should_sell:
                        log.warning(f'股票{stock}有持仓({total_amount})但可卖数量为0，可能为T+1或冻结')
            except Exception as e:
                log.warning(f'获取股票{stock}持仓信息失败: {str(e)}')
                # 备用方案：使用当前字典中的持仓信息
                position = current_positions.get(stock)
                if position:
                    sellable_amount = getattr(position, 'enable_amount', 0)
                    total_amount = getattr(position, 'total_amount', 0) or getattr(position, 'amount', 0)

                    log.debug(f'股票{stock}(备用): 总持仓={total_amount}, 可卖数量={sellable_amount}')
                    
                    # 规范化股票代码进行比较
                    normalized_stock = _normalize_local(stock)
                    should_sell = (stock not in target_position and 
                                 normalized_stock not in keep_codes)
                    
                    if sellable_amount > 0 and should_sell:
                        stocks_to_sell.append(stock)

    log.info(f'当前持仓股票数量: {len(current_positions)}')
    log.info(f'目标持仓股票数量: {len(target_position)}')
    log.info(f'实际可卖出的股票数量: {len(stocks_to_sell)}')

    if len(current_positions) > 0:
        log.debug(f'当前持仓股票: {list(current_positions.keys())}')
    if len(target_position) > 0:
        log.debug(f'目标持仓股票: {list(target_position.keys())}')

    sell_orders = []  # 记录卖出订单
    for stock in stocks_to_sell:
        try:
            # 检查股票是否停牌
            try:
                halt_status = get_stock_status(stock, 'HALT')
                if halt_status and halt_status.get(stock, False):
                    log.warning(f'股票{stock}已停牌，无法卖出')
                    continue
            except Exception as e:
                log.warning(f'检查股票{stock}停牌状态失败: {str(e)}，继续执行')
            
            # 卖出前统一检查
            ok, reason = can_sell_stock(stock)
            if not ok:
                log.warning(f'股票{stock}卖出前检查未通过: {reason}，加入延迟卖出队列')
                context.deferred_sells.add(stock)
                continue

            # 获取开盘后5分钟的价格作为限价
            market_open_price = get_market_open_price(stock, context)
            if market_open_price:
                # 使用开盘后5分钟价格作为限价进行卖出
                order_id = order_target_value(stock, 0, limit_price=market_open_price)
                log.info(f'股票{stock}卖出使用开盘后5分钟价格{market_open_price:.2f}元作为限价')
            else:
                # 如果无法获取开盘后5分钟价格，使用市价单
                order_id = order_target_value(stock, 0)
                log.warning(f'股票{stock}卖出无法获取开盘后5分钟价格，使用市价单')
            
            if order_id:
                sell_orders.append(order_id)
                log.info(f'已提交卖出订单: {stock} (订单ID: {order_id})')
            else:
                log.warning(f'卖出股票{stock}的订单提交失败')
        except Exception as e:
            log.error(f'卖出股票{stock}时发生错误: {str(e)}')
    
    # 第二步：计算全局资金需求和动态调整目标仓位
    target_stocks = list(target_position.keys())
    log.info(f'开始分析{len(target_stocks)}只目标股票的资金需求')
    
    # 计算所有目标股票的资金需求
    stock_analysis = {}
    total_required_cash = 0
    total_released_cash = 0
    
    for stock in target_stocks:
        try:
            target_weight = target_position[stock]
            target_value = portfolio_value * target_weight
            
            # 验证目标权重合理性
            if target_weight <= 0 or target_weight > 1:
                log.warning(f'股票{stock}的目标权重{target_weight:.2%}不合理，跳过')
                continue
            
            # 检查股票是否停牌
            try:
                halt_status = get_stock_status(stock, 'HALT')
                if halt_status and halt_status.get(stock, False):
                    log.warning(f'股票{stock}已停牌，无法交易')
                    continue
            except Exception as e:
                log.warning(f'检查股票{stock}停牌状态失败: {str(e)}，继续执行')
            
            # 获取当前持仓信息
            current_position = current_positions.get(stock)
            current_value = 0
            current_weight = 0
            
            if current_position:
                current_value = current_position.amount * current_position.last_sale_price
                current_weight = current_value / portfolio_value
            
            # 计算权重差异和资金需求
            weight_diff = abs(target_weight - current_weight)
            value_diff = target_value - current_value
            
            # 记录股票分析信息
            stock_analysis[stock] = {
                'target_weight': target_weight,
                'target_value': target_value,
                'current_weight': current_weight,
                'current_value': current_value,
                'weight_diff': weight_diff,
                'value_diff': value_diff,
                'action': 'hold'  # 默认持有
            }
            
            # 设置调仓阈值：权重差异>1%或价值差异绝对值>1000元
            if weight_diff > 0.01 or abs(value_diff) > 1000:
                if value_diff > 0:  # 需要买入
                    stock_analysis[stock]['action'] = 'buy'
                    total_required_cash += value_diff
                elif value_diff < 0:  # 需要卖出
                    stock_analysis[stock]['action'] = 'sell'
                    total_released_cash += abs(value_diff)
                    
        except Exception as e:
            log.error(f'分析股票{stock}时发生错误: {str(e)}')
            continue
    
    # 计算实际可用资金（包括卖出释放的资金）
    total_available_cash = available_cash + total_released_cash
    cash_buffer = total_available_cash * 0.05  # 保留5%缓冲
    usable_cash = total_available_cash - cash_buffer
    
    log.info(f'资金分析: 当前可用{available_cash:.0f}元, 卖出释放{total_released_cash:.0f}元, '
             f'总可用{total_available_cash:.0f}元, 需要{total_required_cash:.0f}元')
    
    # 如果资金不足，按比例缩减买入目标
    scaling_factor = 1.0
    if total_required_cash > usable_cash:
        scaling_factor = usable_cash / total_required_cash
        log.warning(f'资金不足，将按{scaling_factor:.2%}比例缩减买入目标')
        
        # 重新计算缩减后的目标价值
        for stock in stock_analysis:
            if stock_analysis[stock]['action'] == 'buy':
                original_diff = stock_analysis[stock]['value_diff']
                scaled_diff = original_diff * scaling_factor
                stock_analysis[stock]['target_value'] = stock_analysis[stock]['current_value'] + scaled_diff
                stock_analysis[stock]['value_diff'] = scaled_diff
    
    # 第三步：执行调仓操作
    buy_orders = []
    sell_orders_adjust = []  # 调整阶段的卖出订单
    successful_adjustments = 0
    failed_adjustments = 0
    
    # 按顺序执行：先卖出，再买入
    for action_type in ['sell', 'buy']:
        for stock, analysis in stock_analysis.items():
            if analysis['action'] != action_type:
                continue
                
            try:
                target_value = analysis['target_value']
                current_value = analysis['current_value']
                value_diff = analysis['value_diff']
                
                log.debug(f'{"卖出" if action_type == "sell" else "买入"}股票{stock}: '
                        f'当前权重{analysis["current_weight"]:.2%}({current_value:.0f}元) -> '
                        f'目标权重{analysis["target_weight"]:.2%}({target_value:.0f}元)')
                
                # 卖出前检查可卖数量，避免无效委托
                if action_type == 'sell':
                    try:
                        pos = get_position(stock)
                        if pos and getattr(pos, 'enable_amount', 0) == 0:
                            log.warning(f'股票{stock}可卖数量为0，跳过卖出调仓')
                            failed_adjustments += 1
                            continue
                    except Exception as _:
                        pass

                # 使用order_target_value进行调仓
                if action_type == 'sell':
                    ok, reason = can_sell_stock(stock)
                    if not ok:
                        log.warning(f'股票{stock}卖出调仓前检查未通过: {reason}，加入延迟卖出队列')
                        context.deferred_sells.add(stock)
                        failed_adjustments += 1
                        continue
                
                # 获取开盘后5分钟的价格作为限价
                market_open_price = get_market_open_price(stock, context)
                if market_open_price:
                    # 使用开盘后5分钟价格作为限价进行交易
                    order_id = order_target_value(stock, target_value, limit_price=market_open_price)
                    log.debug(f'股票{stock}使用开盘后5分钟价格{market_open_price:.2f}元作为限价')
                else:
                    # 如果无法获取开盘后5分钟价格，使用市价单
                    order_id = order_target_value(stock, target_value)
                    log.warning(f'股票{stock}无法获取开盘后5分钟价格，使用市价单')
                
                log.debug(f'股票{stock}当前价值: {current_value:.2f}元')
                if order_id:
                    if action_type == 'sell':
                        sell_orders_adjust.append(order_id)
                    else:
                        buy_orders.append(order_id)
                    successful_adjustments += 1
                    log.info(f'已提交{"卖出" if action_type == "sell" else "买入"}订单: {stock} '
                            f'目标价值{target_value:.0f}元 (订单ID: {order_id})')
                else:
                    failed_adjustments += 1
                    log.warning(f'股票{stock}的{"卖出" if action_type == "sell" else "买入"}订单提交失败')
                    
            except Exception as e:
                failed_adjustments += 1
                log.error(f'{"卖出" if action_type == "sell" else "买入"}股票{stock}时发生错误: {str(e)}')
                continue
    
    # 记录调仓完成信息
    all_orders = sell_orders + sell_orders_adjust + buy_orders
    log.info(f'调仓完成: 成功{successful_adjustments}笔, 失败{failed_adjustments}笔, '
             f'总订单数{len(all_orders)}')
    
    # 记录订单ID用于后续状态检查
    if all_orders:
        g.recent_orders.extend(all_orders)
        log.debug(f'已记录{len(all_orders)}个订单ID用于状态跟踪')

    # 输出延迟卖出队列信息，提示原因
    if hasattr(context, 'deferred_sells') and context.deferred_sells:
        log.warning(f'延迟卖出队列({len(context.deferred_sells)}): {list(context.deferred_sells)}')
        log.debug('说明：这些股票因可卖数量为0、停牌或当日买入(T+1)暂不清仓，将在条件满足后再卖出')
    
    # 检查目标权重总和和仓位控制
    total_target_weight = sum(target_position.values())
    if abs(total_target_weight - 1.0) > 0.01:
        log.warning(f'目标权重总和为{total_target_weight:.2%}，不等于100%，请检查策略逻辑')
    
    # 动态仓位控制和风险管理
    if scaling_factor < 1.0:
        log.warning(f'由于资金限制，实际仓位已按{scaling_factor:.2%}比例缩减')
        log.debug(f'建议考虑: 1)增加资金投入 2)减少目标股票数量 3)调整权重分配')
    
    # 计算预期资金利用率
    expected_cash_usage = total_required_cash * scaling_factor
    cash_utilization = expected_cash_usage / total_available_cash if total_available_cash > 0 else 0
    log.info(f'资金利用率: {cash_utilization:.1%} (预期使用{expected_cash_usage:.0f}元/'
             f'总可用{total_available_cash:.0f}元)')
    
    # 风险提示
    if cash_utilization > 0.95:
        log.warning('资金利用率过高(>95%)，建议保留更多现金缓冲')
    elif cash_utilization < 0.8:
        log.info(f'资金利用率较低({cash_utilization:.1%})，可考虑增加投资比例')
    
    # 存储订单信息到context中，供后续监控使用
    if not hasattr(context, 'recent_orders'):
        context.recent_orders = {}
    
    context.recent_orders['last_adjustment'] = {
        'timestamp': context.current_dt,
        'sell_orders': sell_orders,
        'sell_orders_adjust': sell_orders_adjust,
        'buy_orders': buy_orders,
        'target_stocks': len(target_position),
        'successful': successful_adjustments,
        'failed': failed_adjustments,
        'scaling_factor': scaling_factor,
        'cash_utilization': cash_utilization
    }
    
    log.info('adjust_position函数执行完成')
    
    # 调用订单状态检查
    check_order_status(context)


def check_order_status(context):
    """检查最近订单的执行状态"""
    if not hasattr(g, 'recent_orders') or not g.recent_orders:
        return
    
    try:
        # 获取所有订单状态
        completed_orders = 0
        failed_orders = 0
        pending_orders = 0
        
        # 创建一个新的列表来存储仍在处理中的订单
        remaining_orders = []
        
        for order_id in g.recent_orders:
            try:
                order_info = get_order(order_id)
                
                # 处理不同的返回格式
                if order_info is None:
                    # 订单不存在或已过期，视为已完成
                    completed_orders += 1
                    continue
                
                # 如果返回的是列表，取第一个元素
                if isinstance(order_info, list):
                    if len(order_info) > 0:
                        order_info = order_info[0]
                    else:
                        completed_orders += 1
                        continue
                
                # 获取订单状态
                if hasattr(order_info, 'status'):
                    status = order_info.status
                elif isinstance(order_info, dict):
                    status = order_info.get('status', '8')  # 默认为已成交
                else:
                    # 无法确定状态，假设已完成
                    completed_orders += 1
                    continue
                
                # 根据API文档中的状态码判断订单状态
                if status in ['8']:  # 已成交
                    completed_orders += 1
                elif status in ['6', '9', '5']:  # 已撤、废单、部撤
                    failed_orders += 1
                else:  # 其他状态视为待处理
                    pending_orders += 1
                    remaining_orders.append(order_id)
                    
            except Exception as e:
                log.warning(f'检查订单 {order_id} 状态时出错: {str(e)}')
                # 出错的订单保留在列表中，下次再检查
                remaining_orders.append(order_id)
                continue
        
        # 更新订单列表，只保留未完成的订单
        g.recent_orders = remaining_orders
        
        # 记录状态信息
        total_orders = completed_orders + failed_orders + pending_orders
        if total_orders > 0:
            if pending_orders == 0:
                log.info(f'所有订单已处理完成: 成功{completed_orders}个，失败{failed_orders}个')
            else:
                log.info(f'订单状态: 已完成{completed_orders}个，失败{failed_orders}个，待处理{pending_orders}个')
            
    except Exception as e:
        log.warning(f'检查订单状态时发生错误: {str(e)}')

    return