import streamlit as st
import akshare as ak
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta

# ========== 策略固定参数 ==========
GRID_STEP = 0.03       # 网格涨跌3%
SIDE_FEE = 0.0025      # 单边手续费 千分之2.5
GRID_LEVEL = 5         # 5档分级仓位
# =================================

# 手机页面初始化
st.set_page_config(page_title="ETF网格智能调仓工具", layout="wide", initial_sidebar_state="collapsed")
plt.rcParams["font.sans-serif"] = ["Arial Unicode MS"]
plt.rcParams["axes.unicode_minus"] = False

# 缓存运行数据
if "base_center_price" not in st.session_state:
    st.session_state.base_center_price = 0.0
if "current_grid_level" not in st.session_state:
    st.session_state.current_grid_level = 0
if "etf_history_data" not in st.session_state:
    st.session_state.etf_history_data = pd.DataFrame()

# 标题说明
st.title("📱 ETF网格交易调仓系统")
st.info(f"策略规则：±{GRID_STEP*100:.0f}%网格档位 | 单边手续费 0.25% | 5档分级分批买卖")

# 模块1：实时行情获取（修复字段报错）
st.subheader("1. 一键获取ETF实时行情")
etf_code = st.text_input("输入场内ETF代码（例：510300 / 159915）", value="510300")
col1, col2 = st.columns(2)
with col1:
    day_count = st.number_input("调取历史天数", min_value=30, max_value=365, value=120)
with col2:
    refresh_btn = st.button("🔄 刷新行情", type="primary")

if refresh_btn:
    try:
        end_day = datetime.now().strftime("%Y%m%d")
        start_day = (datetime.now() - timedelta(days=day_count)).strftime("%Y%m%d")
        # 改用稳定接口获取行情
        df = ak.fund_etf_hist_em(
            symbol=etf_code,
            period="daily",
            start_date=start_day,
            end_date=end_day
        )
        # 修复字段格式问题，重命名并筛选列
        df = df.rename(columns={
            "日期": "date",
            "开盘": "open",
            "最高": "high",
            "最低": "low",
            "收盘": "close"
        })
        df = df[["date", "open", "high", "low", "close"]].copy()
        df["date"] = pd.to_datetime(df["date"])
        st.session_state.etf_history_data = df

        now_price = df["close"].iloc[-1]
        # 动态中枢基准价：近60日收盘价均值
        center_price = round(df["close"].tail(60).mean(), 3)
        st.session_state.base_center_price = center_price

        st.success(f"✅ 行情加载成功！最新现价：{now_price:.3f}元  动态中枢价：{center_price:.3f}元")
        st.dataframe(df.tail(10), use_container_width=True)
    except Exception as err:
        st.error(f"行情读取失败：{err}")

# 模块2：录入客户持仓本金
st.divider()
st.subheader("2. 客户账户持仓信息")
c1, c2 = st.columns(2)
with c1:
    total_money = st.number_input("账户总本金(元)", min_value=1000, value=100000, step=1000)
    hold_shares = st.number_input("当前持仓股数", min_value=0, value=0, step=100)
with c2:
    single_grid_cap = total_money / GRID_LEVEL
    st.metric("单网格档位资金", f"{single_grid_cap:.2f}元")
    st.metric("当前持仓档位", f"{st.session_state.current_grid_level}/{GRID_LEVEL}档")

# 模块3：智能调仓建议（核心计算）
st.divider()
st.subheader("3. 实时调仓操作建议")
if len(st.session_state.etf_history_data) > 0:
    price_now = st.session_state.etf_history_data["close"].iloc[-1]
    base_p = st.session_state.base_center_price
    now_level = st.session_state.current_grid_level
    single_fund = total_money / GRID_LEVEL

    # 生成上下5档网格价格线
    down_price_list = [round(base_p * (1 - GRID_STEP * i), 3) for i in range(1, GRID_LEVEL+1)]
    up_price_list = [round(base_p * (1 + GRID_STEP * i), 3) for i in range(1, GRID_LEVEL+1)]
    result_text = ""
    trade_num = 0

    # 下跌加仓判断
    for index, price_line in enumerate(down_price_list):
        if price_now <= price_line and now_level <= index:
            trade_num = single_fund / (price_now * (1 + SIDE_FEE))
            st.session_state.current_grid_level = index + 1
            result_text = f"🔴 【第{index+1}档加仓】\n参考买入股数：{trade_num:.0f}股\n触发价位：{price_line:.3f}元\n已扣除单边0.25%买入手续费"
            break
    # 上涨减仓判断
    for index, price_line in enumerate(up_price_list):
        if price_now >= price_line and now_level > index:
            trade_num = hold_shares / (now_level - index)
            receive_money = trade_num * price_now * (1 - SIDE_FEE)
            st.session_state.current_grid_level = index
            result_text = f"🟢 【第{index+1}档减仓】\n参考卖出股数：{trade_num:.0f}股\n触发价位：{price_line:.3f}元\n卖出实际到手资金：{receive_money:.2f}元（扣手续费后）"
            break
    # 区间持有
    if result_text == "":
        result_text = f"🟡 当前处于网格中枢区间，建议持有观望\n现价：{price_now:.3f}  中枢基准：{base_p:.3f}"

    st.markdown(f"### {result_text}")

    # 辅助行情研判
    data_df = st.session_state.etf_history_data
    high_max = data_df["high"].max()
    low_min = data_df["low"].min()
    pos_rate = (price_now - low_min) / (high_max - low_min)
    st.info(f"行情参考：近期价格位置分位 {pos_rate:.1%}（0%低位 / 100%高位）\n阶段区间上限：{high_max:.3f}  区间下限：{low_min:.3f}")

# 模块4：价格走势图+网格线可视化
st.divider()
st.subheader("4. 价格走势与网格档位图")
if len(st.session_state.etf_history_data) > 0:
    fig, ax = plt.subplots(figsize=(12, 5))
    data_df = st.session_state.etf_history_data
    ax.plot(data_df["date"], data_df["close"], color="#1f77b4", linewidth=2, label="ETF实时价格")
    ax.axhline(y=base_p, color="orange", lw=2, label="动态中枢基准线")
    # 绘制上下网格虚线
    for p in up_price_list:
        ax.axhline(y=p, color="red", linestyle="--", alpha=0.5)
    for p in down_price_list:
        ax.axhline(y=p, color="green", linestyle="--", alpha=0.5)
    ax.legend()
    ax.grid(alpha=0.3)
    st.pyplot(fig)

# 重置按钮
if st.button("🔄 重置全部参数"):
    st.session_state.base_center_price = 0.0
    st.session_state.current_grid_level = 0
    st.session_state.etf_history_data = pd.DataFrame()
    st.success("数据已清空，可重新测算")