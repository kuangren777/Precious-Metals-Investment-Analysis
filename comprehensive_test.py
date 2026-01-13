#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
黄金价格监控系统 - 综合测试套件
测试所有核心功能，确保系统正常运行
"""

import sys
import os
import json
import time
from pathlib import Path
from datetime import datetime, timedelta

# 设置环境变量（必须在导入gold_monitor之前）
config_file = Path(__file__).parent / 'openssl_legacy.cnf'
os.environ['OPENSSL_CONF'] = str(config_file)

# 添加当前目录到路径
sys.path.insert(0, str(Path(__file__).parent))

# 导入主程序模块
import gold_monitor
from gold_monitor import (
    get_gold_price, parse_price_data,
    create_visualization, detect_crash, should_send_daily_report,
    clean_old_charts
)


class TestResult:
    """测试结果类"""
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.tests = []

    def add_test(self, name, passed, message=""):
        self.tests.append({
            'name': name,
            'passed': passed,
            'message': message,
            'time': datetime.now().strftime('%H:%M:%S')
        })
        if passed:
            self.passed += 1
        else:
            self.failed += 1

    def print_summary(self):
        print("\n" + "="*70)
        print("测试总结")
        print("="*70)

        for test in self.tests:
            status = "✓ PASS" if test['passed'] else "✗ FAIL"
            print(f"{status} [{test['time']}] {test['name']}")
            if test['message']:
                print(f"     {test['message']}")

        print("\n" + "-"*70)
        total = self.passed + self.failed
        pass_rate = (self.passed / total * 100) if total > 0 else 0
        print(f"总计: {total} 个测试")
        print(f"通过: {self.passed} 个 ({pass_rate:.1f}%)")
        print(f"失败: {self.failed} 个")
        print("="*70 + "\n")

        return self.failed == 0


class ComprehensiveTest:
    """综合测试类"""

    def __init__(self):
        self.result = TestResult()
        self.test_data = None
        self.test_chart = None

    def run_all(self):
        """运行所有测试"""
        print("\n" + "="*70)
        print("黄金价格监控系统 - 综合测试套件")
        print("="*70)
        print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*70 + "\n")

        # 先加载配置
        try:
            gold_monitor.load_config()
        except Exception as e:
            print(f"⚠️  配置加载失败: {e}")
            print("部分测试可能无法运行\n")

        # 按顺序执行测试
        self.test_1_config_loading()
        self.test_2_api_connection()
        self.test_3_data_parsing()
        self.test_4_visualization()
        self.test_5_chinese_font()
        self.test_6_crash_detection()
        self.test_7_daily_report_timing()
        self.test_8_chart_history()
        self.test_9_config_validation()
        self.test_10_file_structure()

        # 打印总结
        success = self.result.print_summary()

        if success:
            print("🎉 所有测试通过！系统运行正常。")
            return 0
        else:
            print("⚠️  部分测试失败，请检查上述错误信息。")
            return 1

    def test_1_config_loading(self):
        """测试1: 配置文件加载"""
        print("测试 1/10: 配置文件加载")
        try:
            # 配置已在run_all()中加载，这里只验证

            # 验证必需配置项
            required_keys = {
                'email': ['sender_email', 'admin_emails', 'user_emails', 'smtp_server', 'smtp_port'],
                'monitor': ['check_interval', 'gold_crash_threshold', 'daily_report_times'],
                'api': ['gold_api_url', 'silver_api_url'],
                'ai': ['enable', 'api_base_url', 'api_key', 'model'],
                'storage': ['charts_dir', 'keep_history', 'history_days']
            }

            for section, keys in required_keys.items():
                for key in keys:
                    if key not in gold_monitor.CONFIG[section]:
                        raise KeyError(f"缺少配置项: {section}.{key}")

            self.result.add_test(
                "配置文件加载",
                True,
                f"成功加载配置，监控间隔={gold_monitor.CONFIG['monitor']['check_interval']}秒"
            )
        except Exception as e:
            self.result.add_test("配置文件加载", False, str(e))

    def test_2_api_connection(self):
        """测试2: API连接和数据获取"""
        print("测试 2/10: API连接和数据获取")
        try:
            data = get_gold_price()

            # 验证数据结构
            if not isinstance(data, dict):
                raise ValueError("API返回的数据格式不正确")

            required_fields = ['realtimeData', 'dayData', 'weekData', 'monthData']
            for field in required_fields:
                if field not in data:
                    raise KeyError(f"缺少数据字段: {field}")

            self.test_data = data

            # 统计数据量
            stats = {
                'realtime': len(data.get('realtimeData', [])),
                'day': len(data.get('dayData', [])),
                'week': len(data.get('weekData', [])),
                'month': len(data.get('monthData', []))
            }

            self.result.add_test(
                "API连接和数据获取",
                True,
                f"成功获取数据: 实时={stats['realtime']}, 日={stats['day']}, 周={stats['week']}, 月={stats['month']}"
            )
        except Exception as e:
            self.result.add_test("API连接和数据获取", False, str(e))

    def test_3_data_parsing(self):
        """测试3: 数据解析"""
        print("测试 3/10: 数据解析")
        try:
            if self.test_data is None:
                raise ValueError("没有可用的测试数据")

            parsed = parse_price_data(self.test_data)

            # 验证解析后的数据结构
            required_keys = ['realtime', 'day', 'week', 'month']
            for key in required_keys:
                if key not in parsed:
                    raise KeyError(f"缺少解析后的数据字段: {key}")

            # 验证数据内容
            if parsed['realtime']:
                sample = parsed['realtime'][0]
                if 'price' not in sample or 'rate' not in sample:
                    raise ValueError("实时数据字段不完整")

            if parsed['day']:
                sample = parsed['day'][0]
                required = ['open', 'close', 'high', 'low']
                for field in required:
                    if field not in sample:
                        raise ValueError(f"日数据缺少字段: {field}")

            # 获取当前价格
            current_price = parsed['realtime'][-1]['price'] if parsed['realtime'] else 0
            current_rate = parsed['realtime'][-1]['rate'] if parsed['realtime'] else 0

            self.result.add_test(
                "数据解析",
                True,
                f"成功解析数据，当前价格=¥{current_price:.2f}，涨跌={current_rate:+.2f}%"
            )
        except Exception as e:
            self.result.add_test("数据解析", False, str(e))

    def test_4_visualization(self):
        """测试4: 图表生成"""
        print("测试 4/10: 图表生成")
        try:
            if self.test_data is None:
                raise ValueError("没有可用的测试数据")

            parsed = parse_price_data(self.test_data)

            # 生成测试图表
            test_chart_path = Path(__file__).parent / 'charts' / 'test_chart.png'
            chart_path = create_visualization(parsed, str(test_chart_path))

            # 验证图表文件
            if not os.path.exists(chart_path):
                raise FileNotFoundError("图表文件未生成")

            file_size = os.path.getsize(chart_path) / 1024

            # 验证文件大小（应该大于100KB，包含字体数据）
            if file_size < 100:
                raise ValueError(f"图表文件太小: {file_size:.1f}KB")

            self.test_chart = chart_path

            self.result.add_test(
                "图表生成",
                True,
                f"成功生成图表，大小={file_size:.1f}KB，路径={chart_path}"
            )
        except Exception as e:
            self.result.add_test("图表生成", False, str(e))

    def test_5_chinese_font(self):
        """测试5: 中文字体显示"""
        print("测试 5/10: 中文字体显示")
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt

            # 检查字体配置
            font_config = plt.rcParams['font.sans-serif']

            if 'Noto Sans CJK JP' not in font_config:
                raise ValueError("未配置中文字体")

            # 验证图表文件大小（包含字体数据的文件会更大）
            if self.test_chart and os.path.exists(self.test_chart):
                file_size = os.path.getsize(self.test_chart) / 1024

                # 包含中文字体的图表通常 > 160KB
                if file_size > 160:
                    self.result.add_test(
                        "中文字体显示",
                        True,
                        f"中文字体已正确配置和嵌入，图表大小={file_size:.1f}KB"
                    )
                else:
                    self.result.add_test(
                        "中文字体显示",
                        False,
                        f"图表可能未包含中文字体数据，大小={file_size:.1f}KB < 160KB"
                    )
            else:
                self.result.add_test(
                    "中文字体显示",
                    True,
                    f"中文字体配置正确: {font_config[0]}"
                )
        except Exception as e:
            self.result.add_test("中文字体显示", False, str(e))

    def test_6_crash_detection(self):
        """测试6: 暴跌检测"""
        print("测试 6/10: 暴跌检测")
        try:
            if self.test_data is None:
                raise ValueError("没有可用的测试数据")

            parsed = parse_price_data(self.test_data)
            crash_info = detect_crash(parsed)

            # 验证返回数据结构
            required_keys = ['is_crash', 'rate', 'current_price']
            for key in required_keys:
                if key not in crash_info:
                    raise KeyError(f"缺少字段: {key}")

            threshold = gold_monitor.CONFIG['monitor']['crash_threshold']

            if crash_info['is_crash']:
                message = f"检测到暴跌: 跌幅={crash_info['rate']:.2f}% (阈值={threshold}%)"
            else:
                message = f"价格正常: 涨跌={crash_info['rate']:+.2f}% (阈值={threshold}%)"

            self.result.add_test("暴跌检测", True, message)
        except Exception as e:
            self.result.add_test("暴跌检测", False, str(e))

    def test_7_daily_report_timing(self):
        """测试7: 定时报告逻辑"""
        print("测试 7/10: 定时报告逻辑")
        try:
            # 获取配置的报告时间
            report_times = gold_monitor.CONFIG['monitor']['daily_report_times']

            if not report_times or len(report_times) == 0:
                raise ValueError("未配置定时报告时间")

            # 验证时间格式
            for time_str in report_times:
                parts = time_str.split(':')
                if len(parts) != 2:
                    raise ValueError(f"时间格式错误: {time_str}")
                hour, minute = int(parts[0]), int(parts[1])
                if not (0 <= hour < 24 and 0 <= minute < 60):
                    raise ValueError(f"时间超出范围: {time_str}")

            # 测试should_send_daily_report函数
            # 注意：这个函数基于当前时间，可能返回False
            result = should_send_daily_report()

            self.result.add_test(
                "定时报告逻辑",
                True,
                f"定时配置正确: {', '.join(report_times)}，当前是否应发送={result}"
            )
        except Exception as e:
            self.result.add_test("定时报告逻辑", False, str(e))

    def test_8_chart_history(self):
        """测试8: 历史图表管理"""
        print("测试 8/10: 历史图表管理")
        try:
            charts_dir = Path(__file__).parent / gold_monitor.CONFIG['storage']['charts_dir']

            if not charts_dir.exists():
                raise FileNotFoundError("图表目录不存在")

            # 统计现有图表
            charts = list(charts_dir.glob('gold_chart_*.png'))
            chart_count = len(charts)

            # 测试清理函数（不会真正删除，因为没有过期文件）
            clean_old_charts()

            # 验证配置
            keep_history = gold_monitor.CONFIG['storage']['keep_history']
            history_days = gold_monitor.CONFIG['storage']['history_days']

            self.result.add_test(
                "历史图表管理",
                True,
                f"现有图表={chart_count}个，保留历史={keep_history}，保留天数={history_days}天"
            )
        except Exception as e:
            self.result.add_test("历史图表管理", False, str(e))

    def test_9_config_validation(self):
        """测试9: 配置验证"""
        print("测试 9/10: 配置验证")
        try:
            issues = []

            # 检查邮箱配置
            if gold_monitor.CONFIG['email']['sender_email'] == 'test@126.com':
                issues.append("发件邮箱使用默认测试值")

            if gold_monitor.CONFIG['email']['sender_password'] in ['test_password', '']:
                issues.append("邮箱密码未配置或使用默认值")

            # 检查监控配置
            if gold_monitor.CONFIG['monitor']['check_interval'] < 60:
                issues.append(f"检查间隔过短: {gold_monitor.CONFIG['monitor']['check_interval']}秒")

            # 检查AI配置
            if gold_monitor.CONFIG['ai']['enable'] and not gold_monitor.CONFIG['ai']['api_key']:
                issues.append("AI分析已启用但未配置API密钥")

            if issues:
                message = "配置警告: " + "; ".join(issues)
                self.result.add_test("配置验证", True, message)
            else:
                self.result.add_test("配置验证", True, "所有配置正常")
        except Exception as e:
            self.result.add_test("配置验证", False, str(e))

    def test_10_file_structure(self):
        """测试10: 文件结构完整性"""
        print("测试 10/10: 文件结构完整性")
        try:
            base_dir = Path(__file__).parent

            required_files = {
                'gold_monitor.py': '主程序',
                'config.ini': '配置文件',
                'config.example.ini': '配置示例',
                'start_monitor.sh': '启动脚本',
                'openssl_legacy.cnf': 'SSL配置',
                'requirements.txt': '依赖列表',
                'README.md': '使用文档'
            }

            missing = []
            for file, desc in required_files.items():
                if not (base_dir / file).exists():
                    missing.append(f"{file} ({desc})")

            if missing:
                raise FileNotFoundError(f"缺少文件: {', '.join(missing)}")

            # 检查目录
            charts_dir = base_dir / 'charts'
            if not charts_dir.exists():
                raise FileNotFoundError("缺少 charts 目录")

            self.result.add_test(
                "文件结构完整性",
                True,
                f"所有必需文件和目录存在，共{len(required_files)}个文件"
            )
        except Exception as e:
            self.result.add_test("文件结构完整性", False, str(e))


def main():
    """主函数"""
    # 设置环境变量（SSL配置）
    config_file = Path(__file__).parent / 'openssl_legacy.cnf'
    os.environ['OPENSSL_CONF'] = str(config_file)

    # 运行测试
    tester = ComprehensiveTest()
    exit_code = tester.run_all()

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
