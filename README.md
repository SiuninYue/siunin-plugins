# Claude Plugins

siunin的Claude插件集合仓库。

## 插件列表

### 1. 超级产品经理 (super-product-manager)
- **版本**: 1.3.0
- **描述**: 全能产品经理插件 - 为超级个体/一人企业设计，帮助从想法到产品的全流程管理
- **类别**: 生产力 (productivity)
- **功能**: 14个命令、8个专业Agent、16个专业技能

## 安装

### 方法1：从GitHub安装（推荐）
```bash
# 添加市场
/plugin marketplace add https://github.com/SiuninYue/siunin-plugins.git

# 安装超级产品经理插件
/plugin install super-product-manager@siunin-plugins
```

### 方法2：本地开发安装
```bash
# 添加本地市场
/plugin marketplace add /path/to/siunin-plugins

# 安装插件
/plugin install super-product-manager@siunin-plugins
```

## 项目结构

```
siunin-plugins/
├── plugins/                       # 所有插件目录
│   └── super-product-manager/     # 超级产品经理插件
│       ├── .claude-plugin/
│       │   └── plugin.json       # 插件配置
│       ├── commands/             # 14个命令
│       ├── skills/               # 16个专业技能
│       ├── agents/               # 8个专业Agent
│       ├── README.md             # 插件文档
│       ├── CHANGELOG.md          # 变更日志
│       └── LICENSE               # MIT许可证
├── marketplace/                   # 统一市场配置
│   └── .claude-plugin/
│       └── marketplace.json      # 包含所有插件的市场配置
├── README.md                      # 项目说明（本文件）
└── .gitignore                     # Git忽略文件
```

## 添加新插件

要在本仓库中添加新插件：

1. 在 `plugins/` 目录下创建新插件目录
2. 确保插件包含正确的 `.claude-plugin/plugin.json` 配置
3. 在 `marketplace/.claude-plugin/marketplace.json` 的 `plugins` 数组中添加新条目
4. 更新版本和配置信息
5. 提交并推送到GitHub

## 更新现有插件

1. 修改对应插件目录中的代码
2. 如果需要，更新 `marketplace.json` 中的版本号
3. 提交并推送到GitHub

## 用户安装体验

用户只需执行一次市场添加命令：
```bash
/plugin marketplace add https://github.com/SiuninYue/siunin-plugins.git
```

之后可以通过以下命令安装任何插件：
```bash
/plugin install <plugin-name>@siunin-plugins
```

## 许可证

本仓库中的插件遵循各自的许可证（通常是MIT许可证）。

## 维护者

- siunin