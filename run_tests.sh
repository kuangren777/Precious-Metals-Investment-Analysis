#!/bin/bash
# 运行综合测试套件

cd "$(dirname "$0")"

echo "======================================"
echo "  黄金价格监控系统 - 综合测试"
echo "======================================"
echo ""

# 设置OpenSSL配置
export OPENSSL_CONF="$(pwd)/openssl_legacy.cnf"

# 运行测试
python3 comprehensive_test.py

# 保存退出码
exit_code=$?

echo ""
if [ $exit_code -eq 0 ]; then
    echo "✓ 所有测试通过"
else
    echo "✗ 部分测试失败，退出码: $exit_code"
fi

exit $exit_code
