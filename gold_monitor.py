#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
黄金价格监控系统
功能：
1. 定期获取工商银行黄金价格数据
2. 生成可视化图表分析
3. 检测价格暴跌并发送邮件警告
4. 每天定时发送分析报告（3点和12点）
5. AI智能分析投资建议
"""

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context
import json
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from datetime import datetime, timedelta
import matplotlib
matplotlib.use('Agg')  # 使用非交互式后端
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib import rcParams
import os
import sys
import ssl
import warnings
import configparser
from pathlib import Path

try:
    import numpy as np
except ImportError:
    np = None

# 忽略SSL警告
warnings.filterwarnings('ignore', message='Unverified HTTPS request')

# 设置中文字体 - 使用系统已有的Noto Sans CJK
# 必须使用matplotlib识别的字体名称
plt.rcParams['font.sans-serif'] = ['Noto Sans CJK JP', 'Noto Sans CJK KR', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

# 清除matplotlib字体缓存以确保新字体生效
import matplotlib.font_manager as fm
fm._load_fontmanager(try_read_cache=False)

# 全局配置
CONFIG = {}
LAST_DAILY_REPORT = None
LAST_ERROR_EMAIL = {}  # 记录最近发送的错误邮件，防止重复发送
LAST_CRASH_EMAIL = {}  # 记录最近发送的暴跌邮件，防止重复发送
LAST_PRICE_ALERT = {}  # 记录价格阈值提醒的发送时间，结构: {metal_type: {threshold: datetime}}
LAST_PRICES = {}  # 记录上次检查时的价格，用于检测阈值穿越，结构: {metal_type: price}
IS_FIRST_RUN = True  # 标记是否是首次运行

# 金属类型配置
METAL_TYPES = {
    'gold': {'name': '黄金', 'color': '#FFD700'},
    'silver': {'name': '白银', 'color': '#C0C0C0'},
    'platinum': {'name': '铂金', 'color': '#E5E4E2'},
    'palladium': {'name': '钯金', 'color': '#CED0DD'}
}


class SSLAdapter(HTTPAdapter):
    """自定义SSL适配器，用于处理旧版SSL协议"""
    def init_poolmanager(self, *args, **kwargs):
        ctx = create_urllib3_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ctx.options |= 0x4  # OP_LEGACY_SERVER_CONNECT
        kwargs['ssl_context'] = ctx
        return super().init_poolmanager(*args, **kwargs)


def load_config():
    """加载配置文件"""
    config_file = Path(__file__).parent / 'config.ini'
    if not config_file.exists():
        print("错误: 配置文件不存在")
        print("请复制 config.example.ini 为 config.ini 并填写配置信息")
        print("  cp config.example.ini config.ini")
        sys.exit(1)

    config = configparser.ConfigParser()
    config.read(config_file, encoding='utf-8')

    global CONFIG
    CONFIG = {
        'email': {
            'sender_email': config.get('Email', 'sender_email'),
            'sender_password': config.get('Email', 'sender_password'),
            'receiver_email': config.get('Email', 'receiver_email'),
            'smtp_server': config.get('Email', 'smtp_server'),
            'smtp_port': config.getint('Email', 'smtp_port'),
        },
        'monitor': {
            'check_interval': config.getint('Monitor', 'check_interval'),
            'gold_crash_threshold': config.getfloat('Monitor', 'gold_crash_threshold', fallback=-2.0),
            'silver_crash_threshold': config.getfloat('Monitor', 'silver_crash_threshold', fallback=-3.0),
            'platinum_crash_threshold': config.getfloat('Monitor', 'platinum_crash_threshold', fallback=-2.5),
            'palladium_crash_threshold': config.getfloat('Monitor', 'palladium_crash_threshold', fallback=-3.5),
            'price_alert_interval': config.getint('Monitor', 'price_alert_interval', fallback=3600),
            'daily_report_times': [t.strip() for t in config.get('Monitor', 'daily_report_times').split(',')],
            'max_retries': config.getint('Monitor', 'max_retries', fallback=3),
            'retry_delay': config.getint('Monitor', 'retry_delay', fallback=5),
        },
        'price_thresholds': {}
    }

    # 加载价格阈值配置
    for metal_type in METAL_TYPES.keys():
        threshold_key = f'{metal_type}_price_thresholds'
        threshold_str = config.get('Monitor', threshold_key, fallback='').strip()
        if threshold_str:
            try:
                thresholds = [float(t.strip()) for t in threshold_str.split(',') if t.strip()]
                CONFIG['price_thresholds'][metal_type] = sorted(thresholds)  # 排序便于处理
            except ValueError as e:
                print(f"警告: {threshold_key} 配置格式错误: {e}")
                CONFIG['price_thresholds'][metal_type] = []
        else:
            CONFIG['price_thresholds'][metal_type] = []

    # 配置结构继续
    CONFIG.update({
        'api': {
            'gold_api_url': config.get('API', 'gold_api_url'),
            'silver_api_url': config.get('API', 'silver_api_url'),
            'platinum_api_url': config.get('API', 'platinum_api_url'),
            'palladium_api_url': config.get('API', 'palladium_api_url'),
        },
        'ai': {
            'enable': config.getboolean('AI', 'enable', fallback=False),
            'api_base_url': config.get('AI', 'api_base_url', fallback=''),
            'api_key': config.get('AI', 'api_key', fallback=''),
            'model': config.get('AI', 'model', fallback='gpt-4'),
        },
        'storage': {
            'charts_dir': config.get('Storage', 'charts_dir'),
            'keep_history': config.getboolean('Storage', 'keep_history'),
            'history_days': config.getint('Storage', 'history_days'),
            'save_ai_analysis': config.getboolean('Storage', 'save_ai_analysis', fallback=True),
        }
    })

    # 创建图表目录
    charts_dir = Path(__file__).parent / CONFIG['storage']['charts_dir']
    charts_dir.mkdir(exist_ok=True)

    return CONFIG


def get_metal_price_with_retry(metal_type):
    """获取金属价格数据（带重试机制）"""
    max_retries = CONFIG['monitor']['max_retries']
    retry_delay = CONFIG['monitor']['retry_delay']

    for attempt in range(max_retries):
        try:
            return get_metal_price(metal_type)
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"  ✗ 第{attempt + 1}次尝试失败: {str(e)}")
                print(f"  ⟳ {retry_delay}秒后重试...")
                time.sleep(retry_delay)
            else:
                raise Exception(f"获取{METAL_TYPES[metal_type]['name']}价格失败（重试{max_retries}次后）: {str(e)}")


def get_metal_price(metal_type):
    """获取指定金属的价格数据"""
    try:
        api_url_key = f'{metal_type}_api_url'
        if api_url_key not in CONFIG['api']:
            raise Exception(f"配置文件中未找到{metal_type}的API地址")

        api_url = CONFIG['api'][api_url_key]
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        # 创建会话并使用自定义SSL适配器
        session = requests.Session()
        session.mount('https://', SSLAdapter())
        response = session.get(api_url, headers=headers, timeout=30, verify=False)
        response.raise_for_status()
        data = response.json()

        if data.get('code') == 0:
            return data.get('data')
        else:
            raise Exception(f"API返回错误: {data.get('message')}")
    except Exception as e:
        raise Exception(f"获取{METAL_TYPES[metal_type]['name']}价格失败: {str(e)}")


def parse_price_data(data):
    """解析价格数据"""
    result = {
        'realtime': [],
        'day': [],
        'week': [],
        'month': []
    }

    # 解析实时数据
    if 'realtimeData' in data and data['realtimeData']:
        for item in data['realtimeData'][-100:]:  # 只取最近100条
            result['realtime'].append({
                'time': item.get('quoteDate'),
                'price': float(item.get('price', 0)),
                'rate': float(item.get('upDownRate', 0))
            })

    # 解析日数据
    if 'dayData' in data and data['dayData']:
        for item in data['dayData']:
            result['day'].append({
                'time': item.get('quoteDate'),
                'open': float(item.get('openPrice', 0)),
                'close': float(item.get('closePrice', 0)),
                'high': float(item.get('highPrice', 0)),
                'low': float(item.get('lowPrice', 0))
            })

    # 解析周数据
    if 'weekData' in data and data['weekData']:
        for item in data['weekData']:
            result['week'].append({
                'time': item.get('quoteDate'),
                'open': float(item.get('openPrice', 0)),
                'close': float(item.get('closePrice', 0)),
                'high': float(item.get('highPrice', 0)),
                'low': float(item.get('lowPrice', 0))
            })

    # 解析月数据
    if 'monthData' in data and data['monthData']:
        for item in data['monthData'][-12:]:  # 只取最近12个月
            result['month'].append({
                'time': item.get('quoteDate'),
                'open': float(item.get('openPrice', 0)),
                'close': float(item.get('closePrice', 0)),
                'high': float(item.get('highPrice', 0)),
                'low': float(item.get('lowPrice', 0))
            })

    return result


def create_single_metal_chart(metal_type, metal_data, timestamp, charts_dir):
    """为单个金属生成独立的4面板图表"""
    if not metal_data or not metal_data.get('parsed_data'):
        return None

    parsed_data = metal_data['parsed_data']
    metal_name = METAL_TYPES[metal_type]['name']
    color = METAL_TYPES[metal_type]['color']

    output_file = charts_dir / f'{metal_type}_chart_{timestamp}.png'

    fig, axes = plt.subplots(2, 2, figsize=(16, 12))
    fig.suptitle(f'工商银行{metal_name}价格分析', fontsize=16, fontweight='bold')

    # 1. 实时价格走势
    if parsed_data['realtime']:
        ax = axes[0, 0]
        times = [datetime.fromisoformat(item['time'].replace('Z', '+00:00')) for item in parsed_data['realtime']]
        prices = [item['price'] for item in parsed_data['realtime']]

        ax.plot(times, prices, color=color, linewidth=2)
        ax.set_title('实时价格走势', fontsize=12, fontweight='bold')
        ax.set_xlabel('时间')
        ax.set_ylabel('价格 (元/克)')
        ax.grid(True, alpha=0.3)
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)

        # 添加当前价格标注
        if prices:
            current_price = prices[-1]
            ax.axhline(y=current_price, color='red', linestyle='--', alpha=0.5)
            ax.text(0.02, 0.98, f'当前价: ¥{current_price:.2f}',
                   transform=ax.transAxes, fontsize=10, verticalalignment='top',
                   bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

    # 2. 日K线图
    if parsed_data['day']:
        ax = axes[0, 1]
        times = [datetime.fromisoformat(item['time'].replace('Z', '+00:00')) for item in parsed_data['day']]
        closes = [item['close'] for item in parsed_data['day']]
        highs = [item['high'] for item in parsed_data['day']]
        lows = [item['low'] for item in parsed_data['day']]

        ax.plot(times, closes, color=color, linewidth=2, label='收盘价')
        ax.fill_between(times, lows, highs, alpha=0.3, color=color, label='价格区间')
        ax.set_title('日K线图 (最近30天)', fontsize=12, fontweight='bold')
        ax.set_xlabel('日期')
        ax.set_ylabel('价格 (元/克)')
        ax.legend()
        ax.grid(True, alpha=0.3)
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)

    # 3. 周度价格趋势
    if parsed_data['week']:
        ax = axes[1, 0]
        times = [datetime.fromisoformat(item['time'].replace('Z', '+00:00')) for item in parsed_data['week']]
        closes = [item['close'] for item in parsed_data['week']]

        ax.plot(times, closes, color=color, linewidth=2, marker='o', markersize=4)
        ax.set_title('周度价格趋势', fontsize=12, fontweight='bold')
        ax.set_xlabel('日期')
        ax.set_ylabel('价格 (元/克)')
        ax.grid(True, alpha=0.3)
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)

    # 4. 月度价格趋势（带趋势线）
    if parsed_data['month']:
        ax = axes[1, 1]
        times = [datetime.fromisoformat(item['time'].replace('Z', '+00:00')) for item in parsed_data['month']]
        closes = [item['close'] for item in parsed_data['month']]

        ax.plot(times, closes, color=color, linewidth=2, marker='s', markersize=5, label='收盘价')
        ax.set_title('月度价格趋势 (最近12个月)', fontsize=12, fontweight='bold')
        ax.set_xlabel('日期')
        ax.set_ylabel('价格 (元/克)')
        ax.grid(True, alpha=0.3)
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)

        # 添加趋势线
        if np and len(closes) > 1:
            z = np.polyfit(range(len(closes)), closes, 1)
            p = np.poly1d(z)
            ax.plot(times, p(range(len(closes))), "r--", alpha=0.5, linewidth=1, label='趋势线')
            ax.legend()

    plt.tight_layout()
    plt.savefig(output_file, dpi=100, bbox_inches='tight')
    plt.close()

    return str(output_file)


def create_visualization(all_metals_data):
    """为每种金属生成独立的可视化图表"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    charts_dir = Path(__file__).parent / CONFIG['storage']['charts_dir']

    chart_files = []
    for metal_type in METAL_TYPES.keys():
        if metal_type in all_metals_data:
            chart_file = create_single_metal_chart(
                metal_type,
                all_metals_data[metal_type],
                timestamp,
                charts_dir
            )
            if chart_file:
                chart_files.append(chart_file)

    return chart_files


def get_ai_analysis(all_metals_data, chart_files):
    """使用AI分析贵金属走势并给出投资建议（支持OpenAI标准格式，结合最近新闻）"""
    if not CONFIG['ai']['enable'] or not CONFIG['ai']['api_key']:
        return None

    try:
        from openai import OpenAI
        import base64

        # 准备所有金属的数据摘要
        metals_summary = {}
        for metal_type, metal_data in all_metals_data.items():
            if not metal_data or not metal_data.get('parsed_data'):
                continue

            parsed_data = metal_data['parsed_data']
            summary = {
                'name': METAL_TYPES[metal_type]['name'],
                'current_price': 0,
                'current_rate': 0,
                'day_high': 0,
                'day_low': 0,
                'week_trend': [],
                'month_trend': []
            }

            if parsed_data['realtime']:
                latest = parsed_data['realtime'][-1]
                summary['current_price'] = latest['price']
                summary['current_rate'] = latest['rate']

            if parsed_data['day'] and len(parsed_data['day']) > 0:
                # 取最后一条数据（今天）的最高和最低价格
                today = parsed_data['day'][-1]
                summary['day_high'] = today['high']
                summary['day_low'] = today['low']

            if parsed_data['week']:
                summary['week_trend'] = [{'date': w['time'][:10], 'close': w['close']} for w in parsed_data['week'][-4:]]

            if parsed_data['month']:
                summary['month_trend'] = [{'date': m['time'][:10], 'close': m['close']} for m in parsed_data['month'][-6:]]

            metals_summary[metal_type] = summary

        # 读取所有图表并编码为base64
        chart_images = []
        for chart_path in chart_files:
            if os.path.exists(chart_path):
                with open(chart_path, 'rb') as f:
                    image_data = f.read()
                image_base64 = base64.b64encode(image_data).decode('utf-8')
                # 从文件名提取金属类型
                filename = Path(chart_path).stem
                metal_type = filename.split('_')[0]
                metal_name = METAL_TYPES.get(metal_type, {}).get('name', metal_type)
                chart_images.append({
                    'metal_name': metal_name,
                    'base64': image_base64
                })

        # 构建提示词（包含所有金属和新闻分析要求）
        metals_data_str = ""
        for metal_type, summary in metals_summary.items():
            metals_data_str += f"""
{summary['name']}:
  - 当前价格: ¥{summary['current_price']:.2f} 元/克
  - 当日涨跌: {summary['current_rate']:+.2f}%
  - 日内最高: ¥{summary['day_high']:.2f}
  - 日内最低: ¥{summary['day_low']:.2f}
"""

        prompt = f"""请分析以下贵金属价格数据并给出投资建议。

**重要：请结合2026年1月最近的财经新闻、国际局势、美联储政策、地缘政治等因素进行综合分析。**

当前各金属数据：
{metals_data_str}

分析要求：
1. **市场趋势分析**：结合最近的新闻热点（如美联储利率决议、国际冲突、经济数据等），分析各金属的短期、中期、长期趋势
2. **关键价格位**：标注重要的支撑位和压力位
3. **投资建议**：针对每种金属给出明确的投资建议（买入/持有/观望/卖出）
4. **风险提示**：基于当前国际形势的风险警示

请用专业但易懂的中文回答，字数控制在500字以内，包含对各金属的具体建议。"""

        # 创建OpenAI客户端
        client = OpenAI(
            api_key=CONFIG['ai']['api_key'],
            base_url=CONFIG['ai']['api_base_url']
        )

        # 构建消息内容（包含文本和所有图表）
        message_content = [{"type": "text", "text": prompt}]

        # 添加所有图表图像
        for chart_image in chart_images:
            message_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{chart_image['base64']}"
                }
            })

        # 调用API（使用OpenAI标准格式）
        response = client.chat.completions.create(
            model=CONFIG['ai']['model'],
            messages=[
                {
                    "role": "user",
                    "content": message_content
                }
            ],
            max_tokens=2048,
            temperature=0.7
        )

        return response.choices[0].message.content

    except Exception as e:
        print(f"AI分析失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return None


def save_ai_analysis(analysis_text, chart_files, all_metals_data):
    """保存AI分析结果到文件（支持多种金属）"""
    if not CONFIG['storage']['save_ai_analysis'] or not analysis_text:
        return

    try:
        # 使用时间戳作为文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        charts_dir = Path(chart_files[0]).parent if chart_files else Path(__file__).parent / CONFIG['storage']['charts_dir']

        # 保存为文本文件
        txt_path = charts_dir / f'analysis_{timestamp}.txt'
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(f"贵金属价格AI分析报告\n")
            f.write(f"=" * 60 + "\n")
            f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"图表文件数: {len(chart_files)}\n")
            for chart_file in chart_files:
                f.write(f"  - {Path(chart_file).name}\n")
            f.write(f"=" * 60 + "\n\n")

            # 添加所有金属的市场概况
            f.write(f"市场概况:\n")
            for metal_type, metal_data in all_metals_data.items():
                if metal_data and metal_data.get('parsed_data') and metal_data['parsed_data'].get('realtime'):
                    latest = metal_data['parsed_data']['realtime'][-1]
                    metal_name = METAL_TYPES[metal_type]['name']
                    f.write(f"  {metal_name}: ¥{latest['price']:.2f} 元/克 ({latest['rate']:+.2f}%)\n")
            f.write(f"\n")

            f.write(f"AI分析（结合最近新闻）:\n")
            f.write(f"-" * 60 + "\n")
            f.write(analysis_text)
            f.write(f"\n\n" + "-" * 60 + "\n")
            f.write(f"数据来源: 工商银行贵金属价格API\n")
            f.write(f"分析模型: {CONFIG['ai']['model']}\n")

        # 保存为JSON文件（结构化数据）
        json_path = charts_dir / f'analysis_{timestamp}.json'
        analysis_data = {
            'timestamp': datetime.now().isoformat(),
            'chart_files': [Path(f).name for f in chart_files],
            'model': CONFIG['ai']['model'],
            'analysis_text': analysis_text,
            'market_data': {}
        }

        # 添加所有金属的市场数据
        for metal_type, metal_data in all_metals_data.items():
            if metal_data and metal_data.get('parsed_data') and metal_data['parsed_data'].get('realtime'):
                latest = metal_data['parsed_data']['realtime'][-1]
                analysis_data['market_data'][metal_type] = {
                    'name': METAL_TYPES[metal_type]['name'],
                    'current_price': latest['price'],
                    'rate': latest['rate'],
                    'time': latest['time']
                }

        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(analysis_data, f, ensure_ascii=False, indent=2)

        print(f"✓ AI分析已保存: {txt_path.name}, {json_path.name}")

    except Exception as e:
        print(f"✗ 保存AI分析失败: {str(e)}")


def detect_crash(all_metals_data):
    """检测任意金属价格暴跌"""
    crash_list = []

    for metal_type, metal_data in all_metals_data.items():
        if not metal_data or not metal_data.get('parsed_data'):
            continue

        parsed_data = metal_data['parsed_data']
        # 获取该金属特定的暴跌阈值
        threshold_key = f'{metal_type}_crash_threshold'
        crash_threshold = CONFIG['monitor'].get(threshold_key, -2.0)

        crash_info = {
            'metal_type': metal_type,
            'metal_name': METAL_TYPES[metal_type]['name'],
            'threshold': crash_threshold,
            'is_crash': False,
            'rate': 0,
            'current_price': 0,
            'previous_price': 0
        }

        # 从实时数据检测
        if parsed_data['realtime'] and len(parsed_data['realtime']) > 0:
            latest = parsed_data['realtime'][-1]
            crash_info['rate'] = latest['rate']
            crash_info['current_price'] = latest['price']

            if latest['rate'] <= crash_threshold:
                crash_info['is_crash'] = True

        # 从日数据检测（作为补充）
        if not crash_info['is_crash'] and parsed_data['day'] and len(parsed_data['day']) >= 2:
            today = parsed_data['day'][-1]
            yesterday = parsed_data['day'][-2]

            if yesterday['close'] > 0:
                rate = ((today['close'] - yesterday['close']) / yesterday['close']) * 100
                if rate <= crash_threshold:
                    crash_info['is_crash'] = True
                    crash_info['rate'] = rate
                    crash_info['current_price'] = today['close']
                    crash_info['previous_price'] = yesterday['close']

        if crash_info['is_crash']:
            crash_list.append(crash_info)

    return crash_list


def check_price_thresholds(all_metals_data):
    """检测价格阈值触发（只在价格穿越阈值时触发）"""
    global LAST_PRICES
    alert_list = []

    for metal_type, metal_data in all_metals_data.items():
        if not metal_data or not metal_data.get('parsed_data'):
            continue

        # 获取该金属的价格阈值列表
        thresholds = CONFIG['price_thresholds'].get(metal_type, [])
        if not thresholds:
            continue

        parsed_data = metal_data['parsed_data']
        if not parsed_data['realtime'] or len(parsed_data['realtime']) == 0:
            continue

        latest = parsed_data['realtime'][-1]
        current_price = latest['price']

        # 获取上次价格
        last_price = LAST_PRICES.get(metal_type)

        # 如果没有上次价格（首次运行），保存当前价格并跳过检测
        if last_price is None:
            LAST_PRICES[metal_type] = current_price
            continue

        # 检查每个阈值是否被穿越
        for threshold in thresholds:
            crossed = False
            direction = None

            # 向上穿越：上次价格 < 阈值，当前价格 >= 阈值
            if last_price < threshold <= current_price:
                crossed = True
                direction = '向上突破'

            # 向下穿越：上次价格 > 阈值，当前价格 <= 阈值
            elif last_price > threshold >= current_price:
                crossed = True
                direction = '向下突破'

            if crossed:
                alert_info = {
                    'metal_type': metal_type,
                    'metal_name': METAL_TYPES[metal_type]['name'],
                    'threshold': threshold,
                    'current_price': current_price,
                    'last_price': last_price,
                    'direction': direction
                }
                alert_list.append(alert_info)

        # 更新当前价格为下次检查的上次价格
        LAST_PRICES[metal_type] = current_price

    return alert_list


def should_send_price_alert(alert_list):
    """检查是否应该发送价格阈值提醒（每个阈值在配置的时间间隔内只发送一次）"""
    global LAST_PRICE_ALERT

    if not alert_list:
        return []

    current_time = datetime.now()
    alert_interval = CONFIG['monitor']['price_alert_interval']
    alerts_to_send = []

    for alert in alert_list:
        metal_type = alert['metal_type']
        threshold = str(alert['threshold'])  # 转换为字符串作为key

        # 初始化该金属的记录字典
        if metal_type not in LAST_PRICE_ALERT:
            LAST_PRICE_ALERT[metal_type] = {}

        # 检查该阈值是否在配置的时间间隔内已发送
        if threshold in LAST_PRICE_ALERT[metal_type]:
            last_time = LAST_PRICE_ALERT[metal_type][threshold]
            time_diff = (current_time - last_time).total_seconds()
            if time_diff < alert_interval:
                time_diff_minutes = time_diff / 60
                interval_minutes = alert_interval / 60
                print(f"  ℹ️  {alert['metal_name']}价格阈值¥{threshold}/克在{time_diff_minutes:.1f}分钟前已发送提醒（间隔{interval_minutes:.0f}分钟），跳过本次发送")
                continue

        # 可以发送，记录时间
        LAST_PRICE_ALERT[metal_type][threshold] = current_time
        alerts_to_send.append(alert)

    return alerts_to_send


def format_price_alert_email(alert_list, all_metals_data, chart_files, ai_analysis):
    """格式化价格阈值提醒邮件"""
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 标题包含所有触发的阈值
    alert_names = [f"{alert['metal_name']}¥{alert['threshold']}" for alert in alert_list]
    subject = f"💰 贵金属价格阈值提醒 - {'/'.join(alert_names)} - {current_time}"

    body = f"""贵金属价格阈值提醒！

检测时间: {current_time}
提醒原因: 以下金属价格突破设定的阈值

"""

    # 列出所有触发的阈值详情
    body += "=== 阈值突破详情 ===\n\n"
    for alert in alert_list:
        body += f"""【{alert['metal_name']}】
  阈值价格: ¥{alert['threshold']:.2f} 元/克
  上次价格: ¥{alert['last_price']:.2f} 元/克
  当前价格: ¥{alert['current_price']:.2f} 元/克
  突破方向: {alert['direction']}

"""

    # 添加所有金属的当前状态
    body += "=== 所有金属当前状态 ===\n\n"
    for metal_type, metal_data in all_metals_data.items():
        if metal_data and metal_data.get('parsed_data') and metal_data['parsed_data']['realtime']:
            latest = metal_data['parsed_data']['realtime'][-1]
            metal_name = METAL_TYPES[metal_type]['name']
            body += f"【{metal_name}】¥{latest['price']:.2f} 元/克 ({latest['rate']:+.2f}%)\n"

    if ai_analysis:
        body += f"""

=== AI 智能分析 ===

{ai_analysis}
"""

    body += f"""

---
贵金属价格监控系统
{current_time}
"""

    return subject, body


def send_email(subject, body, image_paths=None, is_html=False):
    """发送邮件通知（支持多个附件）"""
    try:
        email_config = CONFIG['email']

        # 创建邮件
        msg = MIMEMultipart()
        msg['From'] = email_config['sender_email']
        msg['To'] = email_config['receiver_email']
        msg['Subject'] = subject

        # 添加正文
        if is_html:
            msg.attach(MIMEText(body, 'html', 'utf-8'))
        else:
            msg.attach(MIMEText(body, 'plain', 'utf-8'))

        # 添加图片附件（支持单个或多个）
        if image_paths:
            # 如果是单个文件路径（字符串），转换为列表
            if isinstance(image_paths, str):
                image_paths = [image_paths]

            # 添加所有图片附件
            for image_path in image_paths:
                if os.path.exists(image_path):
                    with open(image_path, 'rb') as f:
                        img = MIMEImage(f.read())
                        # 使用文件名作为附件名
                        filename = Path(image_path).name
                        img.add_header('Content-Disposition', 'attachment', filename=filename)
                        msg.attach(img)

        # 发送邮件
        with smtplib.SMTP_SSL(email_config['smtp_server'], email_config['smtp_port']) as server:
            server.login(email_config['sender_email'], email_config['sender_password'])
            server.send_message(msg)

        print(f"✓ 邮件发送成功: {subject}")
        return True
    except Exception as e:
        print(f"✗ 邮件发送失败: {str(e)}")
        return False


def format_crash_email(crash_list, all_metals_data, chart_files, ai_analysis):
    """格式化暴跌警告邮件（支持多种金属）"""
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # 标题包含所有暴跌的金属
    crash_names = [crash['metal_name'] for crash in crash_list]
    subject = f"⚠️ 贵金属价格暴跌警告 - {'/'.join(crash_names)} - {current_time}"

    body = f"""贵金属价格暴跌警告！

检测时间: {current_time}
警告原因: 以下金属价格跌幅超过各自设定的阈值

"""

    # 列出所有暴跌的金属详情
    body += "=== 暴跌详情 ===\n\n"
    for crash in crash_list:
        body += f"""【{crash['metal_name']}】
  当前价格: ¥{crash['current_price']:.2f} 元/克
  跌幅: {crash['rate']:.2f}%
  触发阈值: {crash['threshold']:.1f}%

"""

    # 添加所有金属的当前状态
    body += "=== 其他金属当前状态 ===\n\n"
    for metal_type, metal_data in all_metals_data.items():
        if metal_data and metal_data.get('parsed_data') and metal_data['parsed_data']['realtime']:
            latest = metal_data['parsed_data']['realtime'][-1]
            metal_name = METAL_TYPES[metal_type]['name']
            # 跳过已经在暴跌列表中的
            if not any(crash['metal_type'] == metal_type for crash in crash_list):
                body += f"【{metal_name}】¥{latest['price']:.2f} 元/克 ({latest['rate']:+.2f}%)\n"

    if ai_analysis:
        body += f"""

=== AI投资建议（结合最近新闻） ===

{ai_analysis}

"""

    body += """

⚠️ 请及时关注市场动态！

详细走势图请查看附件。

---
此邮件由贵金属价格监控系统自动发送
"""

    return subject, body


def format_startup_email(all_metals_data, chart_files, ai_analysis):
    """格式化系统启动邮件"""
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    subject = f"🚀 贵金属价格监控系统已启动 - {datetime.now().strftime('%Y年%m月%d日 %H:%M')}"

    body = f"""贵金属价格监控系统启动成功！

启动时间: {current_time}

=== 系统配置 ===

监控金属: {', '.join([METAL_TYPES[t]['name'] for t in METAL_TYPES.keys()])}
监控间隔: {CONFIG['monitor']['check_interval']}秒 ({CONFIG['monitor']['check_interval']//60}分钟)
暴跌阈值:
  · 黄金: {CONFIG['monitor']['gold_crash_threshold']:.1f}%
  · 白银: {CONFIG['monitor']['silver_crash_threshold']:.1f}%
  · 铂金: {CONFIG['monitor']['platinum_crash_threshold']:.1f}%
  · 钯金: {CONFIG['monitor']['palladium_crash_threshold']:.1f}%
定时报告: {', '.join(CONFIG['monitor']['daily_report_times'])}
AI分析: {'已启用（结合最近新闻）' if CONFIG['ai']['enable'] else '未启用'}

=== 当前市场概况 ===

"""

    # 列出所有金属的详细信息
    for metal_type, metal_data in all_metals_data.items():
        if not metal_data or not metal_data.get('parsed_data'):
            continue

        parsed_data = metal_data['parsed_data']
        metal_name = METAL_TYPES[metal_type]['name']

        current_price = 0
        current_rate = 0
        day_high = 0
        day_low = 0

        if parsed_data['realtime']:
            latest = parsed_data['realtime'][-1]
            current_price = latest['price']
            current_rate = latest['rate']

        if parsed_data['day'] and len(parsed_data['day']) > 0:
            # 取最后一条数据（今天）的最高和最低价格
            today = parsed_data['day'][-1]
            day_high = today['high']
            day_low = today['low']

        body += f"""【{metal_name}】
  当前价格: ¥{current_price:.2f} 元/克
  当日涨跌: {current_rate:+.2f}%
  日内最高: ¥{day_high:.2f} 元/克
  日内最低: ¥{day_low:.2f} 元/克
  波动幅度: ¥{day_high - day_low:.2f} 元/克

"""

    if ai_analysis:
        body += f"""
=== AI智能分析（结合最近新闻） ===

{ai_analysis}

"""

    body += """
=== 价格走势图 ===

详细的多维度价格走势对比图请查看附件。

系统将按照配置的间隔持续监控，并在以下情况发送邮件：
✓ 任意金属价格暴跌（超过阈值）
✓ 每日定时报告（配置的时间点）
✓ 系统发生错误

---
此邮件由贵金属价格监控系统自动发送
监控邮箱: """ + CONFIG['email']['receiver_email'] + """
"""

    return subject, body


def format_daily_email(all_metals_data, chart_files, ai_analysis):
    """格式化每日报告邮件（支持多种金属）"""
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    subject = f"📊 贵金属价格每日报告 - {datetime.now().strftime('%Y年%m月%d日')}"

    body = f"""贵金属价格每日分析报告

报告时间: {current_time}

=== 各金属当前市场概况 ===

"""

    # 列出所有金属的详细信息
    for metal_type, metal_data in all_metals_data.items():
        if not metal_data or not metal_data.get('parsed_data'):
            continue

        parsed_data = metal_data['parsed_data']
        metal_name = METAL_TYPES[metal_type]['name']

        current_price = 0
        current_rate = 0
        day_high = 0
        day_low = 0

        if parsed_data['realtime']:
            latest = parsed_data['realtime'][-1]
            current_price = latest['price']
            current_rate = latest['rate']

        if parsed_data['day'] and len(parsed_data['day']) > 0:
            # 取最后一条数据（今天）的最高和最低价格
            today = parsed_data['day'][-1]
            day_high = today['high']
            day_low = today['low']

        body += f"""【{metal_name}】
  当前价格: ¥{current_price:.2f} 元/克
  当日涨跌: {current_rate:+.2f}%
  日内最高: ¥{day_high:.2f} 元/克
  日内最低: ¥{day_low:.2f} 元/克
  波动幅度: ¥{day_high - day_low:.2f} 元/克

"""

    if ai_analysis:
        body += f"""
=== AI智能分析（结合最近新闻） ===

{ai_analysis}

"""

    body += """
=== 价格走势图 ===

详细的多维度价格走势对比图请查看附件，包括：
- 实时价格走势对比
- 日收盘价对比（最近30天）
- 周度价格趋势对比
- 月度价格趋势对比（最近12个月，含趋势线）

---
此邮件由贵金属价格监控系统自动发送
每日发送时间: """ + ', '.join(CONFIG['monitor']['daily_report_times']) + """
"""

    return subject, body


def format_error_email(error_msg):
    """格式化错误警告邮件"""
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    subject = f"⚠️ 贵金属价格监控系统错误 - {current_time}"

    body = f"""贵金属价格监控系统遇到错误！

错误时间: {current_time}
错误信息: {error_msg}

系统已自动重试{CONFIG['monitor']['max_retries']}次，但仍然失败。
请检查系统状态和网络连接。

---
此邮件由贵金属价格监控系统自动发送
"""

    return subject, body


def should_send_error_email(error_msg):
    """检查是否应该发送错误邮件（避免重复发送）"""
    global LAST_ERROR_EMAIL

    current_time = datetime.now()
    error_key = str(error_msg)[:100]  # 使用错误消息的前100个字符作为键

    # 如果这个错误在最近30分钟内已经发送过，就不再发送
    if error_key in LAST_ERROR_EMAIL:
        last_time = LAST_ERROR_EMAIL[error_key]
        time_diff = (current_time - last_time).total_seconds()
        if time_diff < 1800:  # 30分钟 = 1800秒
            print(f"  ℹ️ 相同错误在{time_diff/60:.1f}分钟前已发送邮件，跳过本次发送")
            return False

    # 记录本次发送
    LAST_ERROR_EMAIL[error_key] = current_time

    # 清理超过1小时的旧记录
    keys_to_remove = []
    for key, time_val in LAST_ERROR_EMAIL.items():
        if (current_time - time_val).total_seconds() > 3600:
            keys_to_remove.append(key)
    for key in keys_to_remove:
        del LAST_ERROR_EMAIL[key]

    return True


def should_send_crash_email(crash_list):
    """检查是否应该发送暴跌邮件（1小时内不重复发送）"""
    global LAST_CRASH_EMAIL

    if not crash_list:
        return False

    current_time = datetime.now()
    # 使用暴跌金属的名称列表作为键
    crash_metals = sorted([crash['metal_type'] for crash in crash_list])
    crash_key = ','.join(crash_metals)

    # 如果这些金属的暴跌在最近1小时内已经发送过，就不再发送
    if crash_key in LAST_CRASH_EMAIL:
        last_time = LAST_CRASH_EMAIL[crash_key]
        time_diff = (current_time - last_time).total_seconds()
        if time_diff < 3600:  # 1小时 = 3600秒
            print(f"  ℹ️  相同金属暴跌在{time_diff/60:.1f}分钟前已发送邮件，跳过本次发送")
            return False

    # 记录本次发送
    LAST_CRASH_EMAIL[crash_key] = current_time

    # 清理超过2小时的旧记录
    keys_to_remove = []
    for key, time_val in LAST_CRASH_EMAIL.items():
        if (current_time - time_val).total_seconds() > 7200:
            keys_to_remove.append(key)
    for key in keys_to_remove:
        del LAST_CRASH_EMAIL[key]

    return True


def should_send_daily_report():
    """检查是否应该发送每日报告"""
    global LAST_DAILY_REPORT

    now = datetime.now()
    current_time = now.strftime('%H:%M')

    # 检查是否在配置的发送时间点附近（±5分钟）
    for report_time in CONFIG['monitor']['daily_report_times']:
        target_hour, target_minute = map(int, report_time.split(':'))
        target = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)

        time_diff = abs((now - target).total_seconds())

        # 如果在目标时间的±5分钟内，且今天还没发送过这个时间点的报告
        if time_diff <= 300:  # 5分钟 = 300秒
            report_key = now.strftime('%Y-%m-%d') + '_' + report_time
            if LAST_DAILY_REPORT != report_key:
                LAST_DAILY_REPORT = report_key
                return True

    return False


def clean_old_charts():
    """清理过期的历史图表和AI分析文件"""
    if not CONFIG['storage']['keep_history'] or CONFIG['storage']['history_days'] == 0:
        return

    try:
        charts_dir = Path(__file__).parent / CONFIG['storage']['charts_dir']
        cutoff_date = datetime.now() - timedelta(days=CONFIG['storage']['history_days'])

        deleted_count = 0
        # 支持新旧两种文件名格式
        for pattern in ['gold_chart_*.png', 'metals_chart_*.png']:
            for chart_file in charts_dir.glob(pattern):
                # 从文件名提取时间戳
                try:
                    timestamp_str = chart_file.stem.replace('gold_chart_', '').replace('metals_chart_', '')
                    file_date = datetime.strptime(timestamp_str, '%Y%m%d_%H%M%S')

                    if file_date < cutoff_date:
                        # 删除图表文件
                        chart_file.unlink()
                        deleted_count += 1
                        print(f"删除过期图表: {chart_file.name}")

                        # 删除对应的AI分析文件
                        base_name = chart_file.stem
                        txt_file = charts_dir / f'{base_name}_analysis.txt'
                        json_file = charts_dir / f'{base_name}_analysis.json'

                        if txt_file.exists():
                            txt_file.unlink()
                            print(f"删除分析文件: {txt_file.name}")

                        if json_file.exists():
                            json_file.unlink()
                            print(f"删除分析文件: {json_file.name}")
                except:
                    pass

        if deleted_count > 0:
            print(f"✓ 共清理 {deleted_count} 组过期文件")

    except Exception as e:
        print(f"✗ 清理文件失败: {str(e)}")


def monitor_once():
    """执行一次监控（支持多种贵金属）"""
    print(f"\n{'='*70}")
    print(f"开始监控 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}")

    try:
        # 获取所有金属的数据
        all_metals_data = {}
        failed_metals = []

        for metal_type in METAL_TYPES.keys():
            metal_name = METAL_TYPES[metal_type]['name']
            print(f"正在获取{metal_name}数据...")

            try:
                data = get_metal_price_with_retry(metal_type)
                parsed_data = parse_price_data(data)
                all_metals_data[metal_type] = {
                    'raw_data': data,
                    'parsed_data': parsed_data
                }
                print(f"  ✓ {metal_name}数据获取成功")
            except Exception as e:
                print(f"  ✗ {metal_name}数据获取失败: {str(e)}")
                failed_metals.append((metal_name, str(e)))
                all_metals_data[metal_type] = None

        # 如果所有金属都失败，则抛出异常
        if len(failed_metals) == len(METAL_TYPES):
            error_msg = "所有贵金属数据获取失败:\n" + "\n".join([f"  - {name}: {err}" for name, err in failed_metals])
            raise Exception(error_msg)

        # 如果有部分失败，打印警告
        if failed_metals:
            print(f"\n⚠️ 警告: {len(failed_metals)}种金属数据获取失败:")
            for name, err in failed_metals:
                print(f"  - {name}: {err}")

        # 生成可视化（为每种金属生成独立图表）
        print("\n正在生成可视化图表...")
        chart_files = create_visualization(all_metals_data)
        print(f"✓ 图表已保存: 共{len(chart_files)}张")
        for chart_file in chart_files:
            print(f"  - {Path(chart_file).name}")

        # 检测暴跌（检查所有金属）
        print("\n正在检测价格异常...")
        crash_list = detect_crash(all_metals_data)

        # 检查是否需要发送暴跌邮件
        need_crash_email = False
        if crash_list:
            crash_names = [crash['metal_name'] for crash in crash_list]
            print(f"⚠️  检测到价格暴跌! 涉及金属: {', '.join(crash_names)}")
            for crash in crash_list:
                print(f"  - {crash['metal_name']}: {crash['rate']:.2f}%")

            # 检查是否应该发送（1小时去重）
            need_crash_email = should_send_crash_email(crash_list)
            if not need_crash_email:
                print("  （暴跌邮件已在1小时内发送过，跳过本次发送）")
        else:
            print(f"✓ 所有金属价格正常")

        # 检测价格阈值
        print("\n正在检测价格阈值...")
        price_alert_list = check_price_thresholds(all_metals_data)

        # 检查是否需要发送价格阈值提醒
        alerts_to_send = []
        if price_alert_list:
            alert_details = [f"{alert['metal_name']}¥{alert['threshold']}" for alert in price_alert_list]
            print(f"💰 检测到价格阈值触发! 涉及: {', '.join(alert_details)}")

            # 检查是否应该发送（每个阈值1小时去重）
            alerts_to_send = should_send_price_alert(price_alert_list)
            if not alerts_to_send:
                print("  （所有阈值提醒均已在1小时内发送过，跳过本次发送）")
        else:
            print(f"✓ 未触发价格阈值")

        # 检查是否需要发送每日报告
        need_daily_report = should_send_daily_report()

        # 检查是否是首次运行（需要发送启动邮件）
        global IS_FIRST_RUN
        need_startup_email = IS_FIRST_RUN

        # 只有在需要发送邮件时才进行AI分析（节省API调用）
        ai_analysis = None
        if need_crash_email or need_daily_report or need_startup_email or alerts_to_send:
            if CONFIG['ai']['enable']:
                print("\n正在进行AI分析（结合最近新闻）...")
                ai_analysis = get_ai_analysis(all_metals_data, chart_files)
                if ai_analysis:
                    print(f"✓ AI分析完成")
                    # 保存AI分析结果
                    save_ai_analysis(ai_analysis, chart_files, all_metals_data)
                else:
                    print("✗ AI分析失败")
            else:
                print("\n  ℹ️  AI分析未启用")

        # 发送启动邮件（首次运行）
        if need_startup_email:
            print("\n📧 发送系统启动邮件...")
            subject, body = format_startup_email(all_metals_data, chart_files, ai_analysis)
            send_email(subject, body, chart_files)
            IS_FIRST_RUN = False  # 标记为已发送

        # 发送暴跌邮件
        if need_crash_email:
            print("\n📧 发送暴跌警告邮件...")
            subject, body = format_crash_email(crash_list, all_metals_data, chart_files, ai_analysis)
            send_email(subject, body, chart_files)

        # 发送每日报告
        if need_daily_report:
            print("\n📧 发送每日报告...")
            subject, body = format_daily_email(all_metals_data, chart_files, ai_analysis)
            send_email(subject, body, chart_files)

        # 发送价格阈值提醒
        if alerts_to_send:
            print(f"\n📧 发送价格阈值提醒（{len(alerts_to_send)}个阈值）...")
            subject, body = format_price_alert_email(alerts_to_send, all_metals_data, chart_files, ai_analysis)
            send_email(subject, body, chart_files)

        # 显示当前价格信息
        print("\n=== 当前价格概览 ===")
        for metal_type, metal_data in all_metals_data.items():
            if metal_data and metal_data.get('parsed_data') and metal_data['parsed_data']['realtime']:
                latest = metal_data['parsed_data']['realtime'][-1]
                metal_name = METAL_TYPES[metal_type]['name']
                print(f"{metal_name}: ¥{latest['price']:.2f} 元/克 ({latest['rate']:+.2f}%)")

        # 清理过期图表
        clean_old_charts()

        print(f"{'='*70}\n")

    except Exception as e:
        error_msg = str(e)
        print(f"\n✗ 监控失败: {error_msg}")

        # 检查是否应该发送错误邮件（避免重复）
        if should_send_error_email(error_msg):
            print("📧 发送错误警告邮件...")
            subject, body = format_error_email(error_msg)
            send_email(subject, body)
        else:
            print("  （错误邮件已在近期发送，跳过本次发送）")

        print(f"{'='*70}\n")


def main():
    """主函数"""
    print("="*70)
    print("贵金属价格监控系统启动")
    print("="*70)
    print(f"监控金属: {', '.join([METAL_TYPES[t]['name'] for t in METAL_TYPES.keys()])}")
    print(f"监控间隔: {CONFIG['monitor']['check_interval']}秒 ({CONFIG['monitor']['check_interval']//60}分钟)")
    print("暴跌阈值:")
    print(f"  · 黄金: {CONFIG['monitor']['gold_crash_threshold']:.1f}%")
    print(f"  · 白银: {CONFIG['monitor']['silver_crash_threshold']:.1f}%")
    print(f"  · 铂金: {CONFIG['monitor']['platinum_crash_threshold']:.1f}%")
    print(f"  · 钯金: {CONFIG['monitor']['palladium_crash_threshold']:.1f}%")

    # 显示价格阈值配置
    print("价格阈值:")
    has_thresholds = False
    for metal_type in METAL_TYPES.keys():
        metal_name = METAL_TYPES[metal_type]['name']
        thresholds = CONFIG['price_thresholds'].get(metal_type, [])
        if thresholds:
            has_thresholds = True
            threshold_count = len(thresholds)
            threshold_range = f"¥{min(thresholds):.0f}-{max(thresholds):.0f}"
            print(f"  · {metal_name}: {threshold_count}个阈值 ({threshold_range})")
        else:
            print(f"  · {metal_name}: 未设置")

    if has_thresholds:
        interval_minutes = CONFIG['monitor']['price_alert_interval'] / 60
        print(f"  提醒间隔: {interval_minutes:.0f}分钟")

    print(f"重试次数: {CONFIG['monitor']['max_retries']}次")
    print(f"重试延迟: {CONFIG['monitor']['retry_delay']}秒")
    print(f"通知邮箱: {CONFIG['email']['receiver_email']}")
    print(f"每日报告: {', '.join(CONFIG['monitor']['daily_report_times'])}")
    ai_status = "已启用（结合最近新闻）" if CONFIG['ai']['enable'] else "未启用"
    print(f"AI分析: {ai_status} ({CONFIG['ai']['model']})" if CONFIG['ai']['enable'] else f"AI分析: {ai_status}")
    print(f"\n按 Ctrl+C 停止监控\n")
    print("="*70)

    try:
        while True:
            monitor_once()

            # 等待下一次检查
            print(f"等待 {CONFIG['monitor']['check_interval']} 秒后进行下一次检查...")
            time.sleep(CONFIG['monitor']['check_interval'])

    except KeyboardInterrupt:
        print("\n\n监控系统已停止")
        sys.exit(0)


if __name__ == "__main__":
    # 加载配置
    load_config()
    main()
