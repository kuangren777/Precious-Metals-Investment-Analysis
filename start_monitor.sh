#!/bin/bash
# 黄金价格监控系统启动脚本

cd "$(dirname "$0")"

echo "======================================"
echo "  黄金价格监控系统"
echo "======================================"
echo ""

# 设置OpenSSL配置以支持旧版SSL协议
export OPENSSL_CONF="$(pwd)/openssl_legacy.cnf"

# 检查配置文件
if [ ! -f "config.ini" ]; then
    echo "❌ 错误: 配置文件不存在"
    echo ""
    echo "请先创建配置文件："
    echo "  cp config.example.ini config.ini"
    echo ""
    echo "然后编辑 config 文件，填写您的配置信息："
    echo "  - 邮箱账号和授权码"
    echo "  - 监控参数"
    echo "  - AI分析配置（可选）"
    echo ""
    echo "126邮箱授权码获取方法："
    echo "  1. 登录 126 邮箱"
    echo "  2. 设置 -> POP3/SMTP/IMAP"
    echo "  3. 开启 SMTP 服务"
    echo "  4. 获取授权密码（非登录密码）"
    echo ""
    exit 1
fi

echo "✓ 配置文件已加载"
echo ""

# 使用 -u 参数禁用输出缓冲，确保实时显示日志
python3 -u gold_monitor.py
