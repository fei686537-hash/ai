# PTrade金融数据API完整文档

## 目录
1. [通用说明](#通用说明)
2. [估值数据(valuation)](#估值数据valuation)
3. [资产负债表(balance_statement)](#资产负债表balance_statement)
4. [利润表(income_statement)](#利润表income_statement)
5. [现金流量表(cashflow_statement)](#现金流量表cashflow_statement)
6. [成长能力(growth_ability)](#成长能力growth_ability)
7. [盈利能力(profit_ability)](#盈利能力profit_ability)
8. [每股指标(eps)](#每股指标eps)
9. [营运能力(operating_ability)](#营运能力operating_ability)
10. [偿债能力(debt_paying_ability)](#偿债能力debt_paying_ability)

## 通用说明

### 函数签名
```python
get_fundamentals(security, table_name, fields=None, date=None, start_year=None, end_year=None, report_types=None, date_type=None, merge_type=None)
```

### 查询模式
1. **按日期查询模式**：返回输入日期之前对应的财务数据
2. **按年份查询模式**：返回输入年份范围内对应季度的财务数据

### date字段说明
1. **场景一**：date字段不入参
   - 回测中默认获取context.blotter.current_dt交易日收盘后更新的数据
   - 可能产生未来函数
   - 交易和研究会返回当日数据
   - 建议使用date参数入参上一个交易日日期

2. **场景二**：date字段入参日期
   - 回测和交易中若date为非交易日，将返回NAN数据
   - 研究中若date为非交易日，将返回往前最近一个交易日的数据

## 估值数据(valuation)

### 特别说明
- 只支持按天查询模式
- 不支持参数：start_year, end_year, report_types, date_type, merge_type
- 换手率（turnover_rate）和滚动股息率（dividend_ratio）返回带%的字符串

### 字段列表

| 字段名 | 类型 | 说明 | 返回类型 |
|--------|------|------|----------|
| trading_day | str | 交易日期 | 固定返回 |
| total_value | str | A股总市值(元) | 固定返回 |
| float_value | str | A股流通市值(元) | 自选返回 |
| secu_code | str | 证券代码 | 固定返回 |
| secu_abbr | str | 证券简称 | 自选返回 |
| pe_dynamic | str | 动态市盈率 | 自选返回 |
| pe_static | str | 静态市盈率 | 自选返回 |
| pe_ttm | float | 市盈率PE(TTM) | 自选返回 |
| pb | float | 市净率 | 自选返回 |
| ps | float | 市销率PS | 自选返回 |
| ps_ttm | float | 市销率PS(TTM) | 自选返回 |
| pcf | str | 市现率 | 自选返回 |
| turnover_rate | str | 换手率 | 自选返回 |
| dividend_ratio | str | 滚动股息率 | 自选返回 |
| total_shares | int | 总股本 | 自选返回 |
| a_shares | str | A股股本 | 自选返回 |
| b_shares | float | B股股本 | 自选返回 |
| h_shares | float | H股股本 | 自选返回 |
| a_floats | float | 可流通A股 | 自选返回 |
| b_floats | str | 可流通B股 | 自选返回 |

### 示例
```python
stocks = ['600570.SS','000001.SZ']
# 获取估值数据
get_fundamentals(stocks, 'valuation', fields=['total_value', 'pe_dynamic', 'turnover_rate', 'pb'])
```

## 资产负债表(balance_statement)

### 字段列表

| 字段名 | 类型 | 说明 |
|--------|------|------|
| secu_code | str | 股票代码 |
| secu_abbr | str | 股票简称 |
| company_type | str | 公司类型 |
| end_date | str | 截止日期 |
| publ_date | str | 公告日期 |
| total_current_assets | float | 流动资产合计 |
| total_non_current_assets | float | 非流动资产合计 |
| total_assets | float | 资产总计 |
| total_current_liability | float | 流动负债合计 |
| total_non_current_liability | float | 非流动负债合计 |
| total_liability | float | 负债合计 |
| total_shareholder_equity | float | 所有者权益合计 |

#### 流动资产明细
| 字段名 | 类型 | 说明 |
|--------|------|------|
| cash_equivalents | float | 货币资金 |
| trading_assets | float | 交易性金融资产 |
| bill_receivable | float | 应收票据 |
| account_receivable | float | 应收账款 |
| advance_payment | float | 预付款项 |
| other_receivable | float | 其他应收款 |
| inventories | float | 存货 |
| other_current_assets | float | 其他流动资产 |

#### 非流动资产明细
| 字段名 | 类型 | 说明 |
|--------|------|------|
| fixed_assets | float | 固定资产 |
| construction_materials | float | 工程物资 |
| intangible_assets | float | 无形资产 |
| good_will | float | 商誉 |
| long_deferred_expense | float | 长期待摊费用 |
| deferred_tax_assets | float | 递延所得税资产 |

#### 负债明细
| 字段名 | 类型 | 说明 |
|--------|------|------|
| shortterm_loan | float | 短期借款 |
| trading_liability | float | 交易性金融负债 |
| notes_payable | float | 应付票据 |
| accounts_payable | float | 应付账款 |
| advance_receipts | float | 预收款项 |
| salaries_payable | float | 应付职工薪酬 |
| taxs_payable | float | 应交税费 |
| interest_payable | float | 应付利息 |
| longterm_loan | float | 长期借款 |
| bonds_payable | float | 应付债券 |
| deferred_tax_liability | float | 递延所得税负债 |

#### 所有者权益明细
| 字段名 | 类型 | 说明 |
|--------|------|------|
| paidin_capital | float | 实收资本(股本) |
| capital_reserve_fund | float | 资本公积 |
| surplus_reserve_fund | float | 盈余公积 |
| retained_profit | float | 未分配利润 |

### 示例
```python
# 获取资产负债表数据
get_fundamentals('600570.SS', 'balance_statement', 'total_assets', start_year='2023', end_year='2024', report_types='1')
```

## 利润表(income_statement)

### 字段列表

#### 基本信息
| 字段名 | 类型 | 说明 |
|--------|------|------|
| secu_code | str | 股票代码 |
| secu_abbr | str | 股票简称 |
| company_type | str | 公司类型 |
| end_date | str | 截止日期 |
| publ_date | str | 公告日期 |

#### 利润指标
| 字段名 | 类型 | 说明 |
|--------|------|------|
| total_operating_revenue | float | 营业总收入 |
| operating_revenue | float | 营业收入 |
| total_operating_cost | float | 营业总成本 |
| operating_cost | float | 营业成本 |
| operating_tax_surcharges | float | 营业税金及附加 |
| operating_expense | float | 销售费用 |
| administration_expense | float | 管理费用 |
| financial_expense | float | 财务费用 |
| asset_impairment_loss | float | 资产减值损失 |
| operating_profit | float | 营业利润 |
| total_profit | float | 利润总额 |
| net_profit | float | 净利润 |
| basic_eps | float | 基本每股收益 |
| diluted_eps | float | 稀释每股收益 |

#### 其他收益指标
| 字段名 | 类型 | 说明 |
|--------|------|------|
| invest_income | float | 投资收益 |
| non_operating_income | float | 营业外收入 |
| non_operating_expense | float | 营业外支出 |
| income_tax_cost | float | 所得税费用 |
| minority_profit | float | 少数股东损益 |
| np_parent_company_owners | float | 归属母公司净利润 |

### 示例
```python
# 获取净利润数据
get_fundamentals('600570.SS', 'income_statement', 'net_profit', start_year='2023', end_year='2024', report_types='1')
```

## 现金流量表(cashflow_statement)

### 字段列表

#### 经营活动现金流量
| 字段名 | 类型 | 说明 |
|--------|------|------|
| goods_sale_service_render_cash | float | 销售商品、提供劳务收到的现金 |
| net_operate_cash_flow | float | 经营活动产生的现金流量净额 |
| subtotal_operate_cash_inflow | float | 经营活动现金流入小计 |
| subtotal_operate_cash_outflow | float | 经营活动现金流出小计 |

#### 投资活动现金流量
| 字段名 | 类型 | 说明 |
|--------|------|------|
| invest_withdrawal_cash | float | 收回投资收到的现金 |
| invest_proceeds | float | 取得投资收益收到的现金 |
| invest_cash_paid | float | 投资支付的现金 |
| subtotal_invest_cash_inflow | float | 投资活动现金流入小计 |
| subtotal_invest_cash_outflow | float | 投资活动现金流出小计 |
| net_invest_cash_flow | float | 投资活动产生的现金流量净额 |

#### 筹资活动现金流量
| 字段名 | 类型 | 说明 |
|--------|------|------|
| cash_from_invest | float | 吸收投资收到的现金 |
| cash_from_borrowing | float | 取得借款收到的现金 |
| subtotal_finance_cash_inflow | float | 筹资活动现金流入小计 |
| subtotal_finance_cash_outflow | float | 筹资活动现金流出小计 |
| net_finance_cash_flow | float | 筹资活动产生的现金流量净额 |

#### 现金及等价物
| 字段名 | 类型 | 说明 |
|--------|------|------|
| cash_equivalent_increase | float | 现金及现金等价物净增加额 |
| begin_period_cash | float | 期初现金及现金等价物余额 |
| end_period_cash_equivalent | float | 期末现金及现金等价物余额 |

### 示例
```python
get_fundamentals('600570.SS', 'cashflow_statement', 'net_operate_cash_flow', start_year='2023', end_year='2024', report_types='1')
```

## 成长能力(growth_ability)

### 字段列表

#### 收益增长
| 字段名 | 类型 | 说明 |
|--------|------|------|
| basic_eps_yoy | float | 基本每股收益同比增长（%） |
| operating_revenue_grow_rate | float | 营业收入同比增长（%） |
| net_profit_grow_rate | float | 净利润同比增长（%） |
| np_parent_company_yoy | float | 归属母公司股东的净利润同比增长（%） |
| oper_profit_grow_rate | float | 营业利润同比增长（%） |
| total_profit_grow_rate | float | 利润总额同比增长（%） |

#### 资产增长
| 字段名 | 类型 | 说明 |
|--------|------|------|
| total_asset_grow_rate | float | 总资产同比增长（%） |
| net_asset_grow_rate | float | 净资产同比增长（%） |
| se_without_mi_grow_rate_ytd | float | 归属母公司股东的权益相对年初增长率（%） |

#### 其他指标
| 字段名 | 类型 | 说明 |
|--------|------|------|
| sustainable_grow_rate | float | 可持续增长率（%） |
| avg_np_yoy_past_five_year | float | 过去五年同期归属母公司净利润平均增幅（%） |

### 示例
```python
get_fundamentals('600570.SS', 'growth_ability', 'operating_revenue_grow_rate', start_year='2023', end_year='2024', report_types='1')
```

## 盈利能力(profit_ability)

### 字段列表

#### 收益率指标
| 字段名 | 类型 | 说明 |
|--------|------|------|
| roe | float | 净资产收益率%摊薄公布值（%） |
| roe_weighted | float | 净资产收益率%加权公布值（%） |
| roa | float | 总资产净利率（%） |
| gross_income_ratio | float | 销售毛利率（%） |
| net_profit_ratio | float | 销售净利率（%） |
| operating_profit_ratio | float | 营业利润率（%） |

#### 成本费用
| 字段名 | 类型 | 说明 |
|--------|------|------|
| operating_expense_rate | float | 销售费用/营业总收入（%） |
| admini_expense_rate | float | 管理费用/营业总收入（%） |
| financial_expense_rate | float | 财务费用/营业总收入（%） |
| sales_cost_ratio | float | 销售成本率（%） |

### 示例
```python
get_fundamentals('600570.SS', 'profit_ability', 'roe', start_year='2023', end_year='2024', report_types='1')
```

## 每股指标(eps)

### 字段列表

#### 每股收益
| 字段名 | 类型 | 说明 |
|--------|------|------|
| basic_eps | float | 基本每股收益（元/股） |
| diluted_eps | float | 稀释每股收益（元/股） |
| eps | float | 每股收益_期末股本摊薄（元/股） |
| eps_ttm | float | 每股收益_TTM（元/股） |

#### 每股其他指标
| 字段名 | 类型 | 说明 |
|--------|------|------|
| naps | float | 每股净资产（元/股） |
| operating_revenue_ps | float | 每股营业收入（元/股） |
| capital_surplus_fund_ps | float | 每股资本公积金（元/股） |
| surplus_reserve_fund_ps | float | 每股盈余公积（元/股） |
| undivided_profit | float | 每股未分配利润（元/股） |
| net_operate_cash_flow_ps | float | 每股经营活动产生的现金流量净额（元/股） |
| enterprise_fcf_ps | float | 每股企业自由现金流量（元/股） |
| shareholder_fcf_ps | float | 每股股东自由现金流量（元/股） |

### 示例
```python
get_fundamentals('600570.SS', 'eps', 'basic_eps', start_year='2023', end_year='2024', report_types='1')
```

## 营运能力(operating_ability)

### 字段列表

#### 周转率指标
| 字段名 | 类型 | 说明 |
|--------|------|------|
| inventory_turnover_rate | float | 存货周转率（次） |
| accounts_receivables_turnover_rate | float | 应收帐款周转率（次） |
| accounts_payables_turnover_rate | float | 应付帐款周转率（次） |
| current_assets_turnover_rate | float | 流动资产周转率（次） |
| fixed_asset_turnover_rate | float | 固定资产周转率（次） |
| total_asset_turnover_rate | float | 总资产周转率（次） |

#### 周转天数
| 字段名 | 类型 | 说明 |
|--------|------|------|
| inventory_turnover_days | float | 存货周转天数（天/次） |
| accounts_receivables_turnover_days | float | 应收帐款周转天数（天/次） |
| accounts_payables_turnover_days | float | 应付帐款周转天数（天/次） |
| oper_cycle | float | 营业周期（天/次） |

### 示例
```python
get_fundamentals('600570.SS', 'operating_ability', 'inventory_turnover_rate', start_year='2023', end_year='2024', report_types='1')
```

## 偿债能力(debt_paying_ability)

### 字段列表

#### 偿债能力比率
| 字段名 | 类型 | 说明 |
|--------|------|------|
| current_ratio | float | 流动比率 |
| quick_ratio | float | 速动比率 |
| super_quick_ratio | float | 超速动比率 |
| debt_equity_ratio | float | 产权比率（%） |
| interest_cover | float | 利息保障倍数（倍） |

#### 现金流相关指标
| 字段名 | 类型 | 说明 |
|--------|------|------|
| nocf_to_t_liability | float | 经营活动产生现金流量净额/负债合计 |
| nocf_to_interest_bear_debt | float | 经营活动产生现金流量净额/带息债务 |
| nocf_to_current_liability | float | 经营活动产生现金流量净额/流动负债 |
| opercashinto_current_debt | float | 现金流动负债比 |

#### 资产负债结构
| 字段名 | 类型 | 说明 |
|--------|------|------|
| sewmi_to_total_liability | float | 归属母公司股东的权益/负债合计（%） |
| debt_tangible_equity_ratio | float | 有形净值债务率（%） |
| long_debt_to_working_capital | float | 长期负债与营运资金比率 |

### 示例
```python
get_fundamentals('600570.SS', 'debt_paying_ability', 'current_ratio', start_year='2023', end_year='2024', report_types='1')
```
