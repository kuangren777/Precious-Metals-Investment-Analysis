# 贵金属价格监控系统

自动监控工商银行贵金属价格（黄金、白银、铂金、钯金），生成可视化图表，并在价格暴跌时发送邮件警告。支持AI智能分析投资建议。

## 功能特性

- ✨ **多金属监控** - 同时监控4种贵金属（黄金、白银、铂金、钯金）
- 📊 **独立可视化** - 每种金属生成独立的4面板图表（实时、日线、周线、月线）
- 💾 **历史图表** - 保留带时间戳的历史图表，可配置保留期限
- ⚠️ **智能预警** - 每种金属独立的暴跌阈值（黄金-2%、白银-3%、铂金-2.5%、钯金-3.5%）
- 📧 **定时报告** - 每天下午3点和晚上12点发送所有金属的分析报告
- 🤖 **AI分析** - 支持多种AI模型智能分析，结合最新新闻提供专业投资建议
- 🔧 **灵活配置** - 使用配置文件管理所有设置

## 环境要求

- Python 3.7+
- 网络连接
- 126邮箱账号（用于发送邮件）
- Anthropic API密钥（可选，用于AI分析）

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置系统

```bash
# 复制配置示例文件
cp config.example config

# 编辑配置文件，填写您的信息
nano config  # 或使用其他编辑器
```

**必需配置项：**
- `sender_email` - 发件邮箱（126邮箱）
- `sender_password` - 邮箱授权码（不是登录密码）
- `receiver_email` - 收件邮箱

**可选配置项：**
- `ai_service` - AI服务（anthropic/openai/none）
- `ai_api_key` - AI API密钥
- `check_interval` - 检查间隔（秒）
- `gold_crash_threshold` - 黄金暴跌阈值（%，默认-2.0）
- `silver_crash_threshold` - 白银暴跌阈值（%，默认-3.0）
- `platinum_crash_threshold` - 铂金暴跌阈值（%，默认-2.5）
- `palladium_crash_threshold` - 钯金暴跌阈值（%，默认-3.5）
- `daily_report_times` - 定时报告时间

### 3. 快速测试（推荐首次使用）

```bash
./quick_test.sh
```

这将运行一次监控测试，验证系统是否正常工作并生成图表。

### 4. 启动完整监控

```bash
./start_monitor.sh
```

## 配置说明

### 获取126邮箱授权码

1. 登录 [126邮箱](https://mail.126.com)
2. 进入"设置" → "POP3/SMTP/IMAP"
3. 开启"SMTP服务"
4. 点击"获取授权密码"
5. 将获得的授权码填入config文件的`sender_password`

### 配置AI分析（可选）

如需启用AI智能分析功能：

1. 获取Anthropic API密钥（访问 https://console.anthropic.com）
2. 编辑config文件：
   ```ini
   [AI]
   ai_service = anthropic
   ai_api_key = your_api_key_here
   ai_model = claude-sonnet-4.5-20250929
   ```

AI分析将提供：
- 市场趋势分析（短期、中期、长期）
- 关键价格支撑位和压力位
- 投资建议（买入/持有/观望/卖出）
- 风险提示

### 配置参数详解

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| check_interval | 监控检查间隔（秒） | 600（10分钟） |
| gold_crash_threshold | 黄金暴跌预警阈值（%） | -2.0 |
| silver_crash_threshold | 白银暴跌预警阈值（%） | -3.0 |
| platinum_crash_threshold | 铂金暴跌预警阈值（%） | -2.5 |
| palladium_crash_threshold | 钯金暴跌预警阈值（%） | -3.5 |
| daily_report_times | 定时报告时间 | 15:00,00:00 |
| charts_dir | 图表保存目录 | charts |
| keep_history | 是否保留历史图表 | true |
| history_days | 历史图表保留天数 | 30 |

## 使用方法

### 方式1：使用启动脚本（推荐）

```bash
./start_monitor.sh
```

### 方式2：直接运行Python脚本

```bash
export OPENSSL_CONF="$(pwd)/openssl_legacy.cnf"
python gold_monitor.py
```

### 停止监控

按 `Ctrl+C` 停止程序。

### 后台运行

```bash
# 启动后台运行
nohup ./start_monitor.sh > gold_monitor.log 2>&1 &

# 查看日志
tail -f gold_monitor.log

# 停止后台进程
pkill -f gold_monitor.py
```

## 输出文件

### 图表文件

- 保存位置：`charts/` 目录
- 文件命名（每次监控生成4个文件）：
  - `gold_chart_YYYYMMDD_HHMMSS.png`
  - `silver_chart_YYYYMMDD_HHMMSS.png`
  - `platinum_chart_YYYYMMDD_HHMMSS.png`
  - `palladium_chart_YYYYMMDD_HHMMSS.png`
- 每个图表包含4个子图：
  1. **实时价格走势** - 最近的实时价格变化
  2. **日K线图** - 最近30天的价格波动区间
  3. **周度价格趋势** - 周度收盘价走势
  4. **月度价格趋势** - 最近12个月的价格趋势（含趋势线）

### 日志输出

每次监控会输出：
- 当前时间
- 获取数据状态
- 当前价格和涨跌幅
- AI分析结果（如启用）
- 邮件发送状态

## 邮件通知

系统会在以下情况自动发送邮件：

### 1. 价格暴跌警告

当任意金属跌幅超过其设定阈值时：
- 📧 主题：`⚠️ 贵金属价格暴跌警告 - [金属名称]`
- 📎 附件：所有4种金属的价格走势图
- 🤖 内容：包含AI综合投资建议（如启用）
- ⏰ 去重：同样的暴跌情况1小时内只发送一次

### 2. 系统启动通知

系统首次运行时：
- 📧 主题：`🚀 贵金属价格监控系统已启动`
- 📎 附件：所有金属的当前走势图
- 📊 内容：系统配置和当前市场概况

### 3. 每日定时报告

每天下午3点和晚上12点（可配置）：
- 📧 主题：`📊 贵金属价格每日报告`
- 📎 附件：所有4种金属的完整价格走势图
- 📊 内容：
  - 所有金属的当前市场概况
  - 价格关键数据
  - AI综合智能分析（如启用）

### 4. 系统错误警告

当API请求失败或系统出错时：
- 📧 主题：`⚠️ 贵金属价格监控系统错误`
- 📝 内容：错误信息和时间戳
- ⏰ 去重：相同错误30分钟内只发送一次

## 中文显示

系统已配置使用以下中文字体（按优先级）：
1. Noto Sans CJK SC（简体中文）
2. Noto Sans CJK TC（繁体中文）
3. DejaVu Sans（备用）

图表中的中文文字将正确显示。

## 故障排查

### 无法获取数据

- 检查网络连接
- 确认API地址可访问
- 查看防火墙设置
- 确认OPENSSL_CONF已设置

### 邮件发送失败

- 确认config文件已正确配置
- 检查邮箱授权码是否正确（不是登录密码）
- 确认SMTP服务已开启
- 检查网络连接

### AI分析失败

- 确认ai_service配置正确
- 检查API密钥是否有效
- 确认网络可访问Anthropic API
- 查看日志获取详细错误信息

### 配置文件错误

```bash
# 如果配置文件损坏，重新复制示例文件
cp config.example config
```

## 项目结构

```
260108gold_price/
├── gold_monitor.py          # 主监控程序
├── config.example           # 配置文件示例
├── config                   # 配置文件（需要创建）
├── start_monitor.sh         # 启动脚本
├── quick_test.sh            # 快速测试脚本
├── test_monitor.py          # 单次测试程序
├── openssl_legacy.cnf       # OpenSSL配置
├── requirements.txt         # Python依赖
├── README.md                # 使用文档
└── charts/                  # 图表保存目录（自动创建）
    ├── gold_chart_20260108_150000.png
    ├── gold_chart_20260108_160000.png
    └── ...
```

## 技术特性

- ✅ 支持旧版SSL协议（工商银行API兼容）
- ✅ 多维度数据可视化
- ✅ 智能时间序列分析
- ✅ 图表中文字体自动配置
- ✅ 历史数据自动清理
- ✅ 定时任务精确调度
- ✅ 完整的错误处理
- ✅ AI视觉分析支持

## 更新日志

### v2.0.0 (2026-01-08)

- ✨ 新增AI智能分析功能
- ✨ 新增定时邮件报告（每天3点和12点）
- ✨ 新增历史图表保存功能
- ✨ 修复中文字体显示问题
- ✨ 改用配置文件替代环境变量
- ✨ 优化图表可视化效果
- ✨ 添加历史图表自动清理

### v1.0.0 (2026-01-08)

- 🎉 初始版本发布
- ✨ 基础监控功能
- ✨ 价格暴跌预警
- ✨ 邮件通知

## 许可证

MIT License

## 支持

如有问题或建议，请提交Issue。
