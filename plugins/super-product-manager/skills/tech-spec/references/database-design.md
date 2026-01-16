# 数据库设计指南

## 数据建模基础

### 实体关系

| 关系类型 | 说明 | 示例 |
|---------|------|------|
| **一对一** | 1:1 | 用户 - 用户详情 |
| **一对多** | 1:N | 用户 - 订单 |
| **多对多** | M:N | 用户 - 角色 |

### 表设计原则

| 原则 | 说明 |
|------|------|
| **单一职责** | 一张表只存一类数据 |
| **避免冗余** | 不重复存储相同数据 |
| **适度反范式** | 为性能可适当冗余 |
| **预留扩展** | 考虑未来字段扩展 |

## 数据表设计模板

### 标准表结构

```markdown
## 表名：users（用户表）

### 表说明
存储用户基本信息

### 字段设计
| 字段名 | 类型 | 长度 | 允许空 | 默认值 | 说明 |
|--------|------|------|--------|--------|------|
| id | bigint | - | N | 自增 | 主键 |
| phone | varchar | 20 | N | - | 手机号 |
| nickname | varchar | 50 | Y | - | 昵称 |
| avatar | varchar | 255 | Y | - | 头像URL |
| status | tinyint | - | N | 1 | 状态：1正常 2禁用 |
| created_at | datetime | - | N | CURRENT | 创建时间 |
| updated_at | datetime | - | N | CURRENT | 更新时间 |
| deleted_at | datetime | - | Y | NULL | 删除时间（软删除）|

### 索引设计
| 索引名 | 类型 | 字段 | 说明 |
|--------|------|------|------|
| uk_phone | UNIQUE | phone | 手机号唯一 |
| idx_status | INDEX | status | 状态查询 |
| idx_created | INDEX | created_at | 时间排序 |

### 关联关系
- users.id → orders.user_id（一对多）
- users.id → user_roles.user_id（多对多）
```

## 常用字段设计

### 通用字段

```markdown
## 每张表都应该有的字段

| 字段 | 类型 | 说明 |
|------|------|------|
| id | bigint | 主键，自增 |
| created_at | datetime | 创建时间 |
| updated_at | datetime | 更新时间 |
| deleted_at | datetime | 软删除时间 |
```

### 状态字段设计

```markdown
## 状态字段设计规范

### 方式一：数字状态
| 值 | 含义 |
|----|------|
| 0 | 未激活 |
| 1 | 正常 |
| 2 | 禁用 |
| -1 | 已删除 |

### 方式二：枚举状态
| 值 | 含义 |
|----|------|
| pending | 待处理 |
| processing | 处理中 |
| completed | 已完成 |
| cancelled | 已取消 |

### 建议
- 简单状态用数字（0/1/2）
- 复杂状态用枚举字符串
- 状态变更要有记录
```

### 金额字段设计

```markdown
## 金额存储规范

### 推荐：存储分
| 字段 | 类型 | 说明 |
|------|------|------|
| amount | bigint | 金额（分） |

优点：
- 避免浮点数精度问题
- 计算更简单

### 备选：decimal 类型
| 字段 | 类型 | 说明 |
|------|------|------|
| amount | decimal(10,2) | 金额（元） |

适用：
- 需要支持多位小数
- 国际化货币
```

## 常见业务表设计

### 用户体系

```markdown
## 用户相关表

### users（用户表）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | bigint | 主键 |
| phone | varchar(20) | 手机号 |
| password | varchar(255) | 密码（加密）|
| salt | varchar(32) | 密码盐 |
| nickname | varchar(50) | 昵称 |
| avatar | varchar(255) | 头像 |
| status | tinyint | 状态 |

### user_profiles（用户详情）
| 字段 | 类型 | 说明 |
|------|------|------|
| user_id | bigint | 用户ID |
| real_name | varchar(50) | 真实姓名 |
| id_card | varchar(18) | 身份证（加密）|
| gender | tinyint | 性别 |
| birthday | date | 生日 |

### user_login_logs（登录日志）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | bigint | 主键 |
| user_id | bigint | 用户ID |
| ip | varchar(50) | IP地址 |
| device | varchar(100) | 设备信息 |
| login_at | datetime | 登录时间 |
```

### 订单体系

```markdown
## 订单相关表

### orders（订单表）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | bigint | 主键 |
| order_no | varchar(32) | 订单号 |
| user_id | bigint | 用户ID |
| total_amount | bigint | 总金额（分）|
| pay_amount | bigint | 实付金额（分）|
| status | varchar(20) | 订单状态 |
| paid_at | datetime | 支付时间 |

### order_items（订单项）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | bigint | 主键 |
| order_id | bigint | 订单ID |
| product_id | bigint | 商品ID |
| product_name | varchar(100) | 商品名称（冗余）|
| price | bigint | 单价（分）|
| quantity | int | 数量 |

### order_logs（订单日志）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | bigint | 主键 |
| order_id | bigint | 订单ID |
| action | varchar(50) | 操作类型 |
| operator | varchar(50) | 操作人 |
| remark | text | 备注 |
```

## 索引设计

### 索引类型

| 类型 | 用途 | 示例 |
|------|------|------|
| **主键索引** | 唯一标识 | id |
| **唯一索引** | 确保唯一 | phone, email |
| **普通索引** | 加速查询 | status, created_at |
| **组合索引** | 多条件查询 | (user_id, status) |

### 索引设计原则

```markdown
## 索引设计规范

### 需要加索引
- [ ] 经常用于 WHERE 条件的字段
- [ ] 经常用于 ORDER BY 的字段
- [ ] 外键关联字段
- [ ] 唯一性约束字段

### 不建议加索引
- [ ] 数据量很小的表
- [ ] 频繁更新的字段
- [ ] 区分度很低的字段（如性别）

### 组合索引规则
- 最左前缀原则
- 高区分度字段在前
- 范围查询字段在后
```

## 数据库设计检查清单

```markdown
## 设计自查

### 表设计
- [ ] 表名有意义，使用复数
- [ ] 有主键（推荐自增 bigint）
- [ ] 有 created_at, updated_at
- [ ] 考虑软删除（deleted_at）

### 字段设计
- [ ] 字段名清晰，使用下划线
- [ ] 类型选择合适
- [ ] 必填字段设置 NOT NULL
- [ ] 敏感字段标注加密

### 索引设计
- [ ] 主键索引
- [ ] 唯一约束有唯一索引
- [ ] 常用查询条件有索引
- [ ] 避免过多索引

### 关联设计
- [ ] 外键关系明确
- [ ] 级联删除/更新策略明确
```
