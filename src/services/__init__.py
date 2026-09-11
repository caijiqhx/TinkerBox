"""跨工具公共服务层（纯标准库）。

- jsonio   原子 JSON 读写
- config   全局配置
- logs     日志
- platform 平台差异（全项目唯一允许出现平台分支的地方）
"""

__all__ = ["jsonio", "config", "logs", "platform"]
