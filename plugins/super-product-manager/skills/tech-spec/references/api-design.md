# API 设计指南

## RESTful API 基础

### HTTP 方法

| 方法 | 用途 | 示例 |
|------|------|------|
| **GET** | 获取数据 | 获取用户列表 |
| **POST** | 创建数据 | 创建新用户 |
| **PUT** | 更新数据（完整） | 更新用户全部信息 |
| **PATCH** | 更新数据（部分） | 更新用户昵称 |
| **DELETE** | 删除数据 | 删除用户 |

### URL 设计规范

```markdown
## URL 设计原则

### 基本规则
- 使用名词，不用动词：/users（不是 /getUsers）
- 使用复数：/users（不是 /user）
- 层级清晰：/users/{id}/orders
- 全小写，用连字符：/user-profiles

### 示例
| 操作 | 方法 | URL |
|------|------|-----|
| 获取用户列表 | GET | /users |
| 获取单个用户 | GET | /users/{id} |
| 创建用户 | POST | /users |
| 更新用户 | PUT | /users/{id} |
| 删除用户 | DELETE | /users/{id} |
| 获取用户订单 | GET | /users/{id}/orders |
```

### HTTP 状态码

| 状态码 | 含义 | 使用场景 |
|--------|------|---------|
| **200** | 成功 | GET/PUT/PATCH 成功 |
| **201** | 已创建 | POST 成功创建 |
| **204** | 无内容 | DELETE 成功 |
| **400** | 请求错误 | 参数格式错误 |
| **401** | 未授权 | 未登录 |
| **403** | 禁止访问 | 无权限 |
| **404** | 未找到 | 资源不存在 |
| **500** | 服务器错误 | 系统异常 |

## API 文档模板

### 接口文档格式

```markdown
## 接口：[接口名称]

### 基本信息
| 项目 | 内容 |
|------|------|
| 接口路径 | `[METHOD] /api/v1/xxx` |
| 功能描述 | [一句话描述] |
| 权限要求 | 登录/无需登录 |

---

### 请求参数

#### Header 参数
| 参数名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| Authorization | string | 是 | Bearer {token} |

#### Query 参数（GET 请求）
| 参数名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| page | int | 否 | 页码，默认1 | 1 |
| size | int | 否 | 每页条数，默认20 | 20 |

#### Body 参数（POST/PUT 请求）
| 参数名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| name | string | 是 | 用户名 | "张三" |
| phone | string | 是 | 手机号 | "13800138000" |

---

### 响应结果

#### 成功响应
```json
{
  "code": 0,
  "message": "success",
  "data": {
    "id": 123,
    "name": "张三",
    "phone": "138****8000",
    "createdAt": "2024-01-01T00:00:00Z"
  }
}
```

#### 错误响应
```json
{
  "code": 40001,
  "message": "手机号格式错误",
  "data": null
}
```

---

### 错误码说明
| 错误码 | 说明 | 处理建议 |
|--------|------|---------|
| 40001 | 手机号格式错误 | 提示用户重新输入 |
| 40002 | 用户名已存在 | 提示换一个用户名 |
```

## 分页设计

### 标准分页响应

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "list": [
      { "id": 1, "name": "item1" },
      { "id": 2, "name": "item2" }
    ],
    "pagination": {
      "page": 1,
      "size": 20,
      "total": 100,
      "totalPages": 5
    }
  }
}
```

### 游标分页（大数据量）

```json
{
  "code": 0,
  "data": {
    "list": [...],
    "nextCursor": "xxx123",
    "hasMore": true
  }
}
```

## 版本控制

### URL 版本

```
/api/v1/users    # 版本1
/api/v2/users    # 版本2
```

### Header 版本

```
Accept: application/vnd.api+json; version=1
```

## 认证方式

### Token 认证

```markdown
## JWT Token 认证

### 登录获取 Token
POST /api/v1/auth/login
Body: { "phone": "xxx", "code": "xxx" }
Response: { "token": "eyJhbGci..." }

### 携带 Token 访问
Header: Authorization: Bearer eyJhbGci...

### Token 刷新
POST /api/v1/auth/refresh
Header: Authorization: Bearer {oldToken}
Response: { "token": "newToken" }
```

## API 设计检查清单

```markdown
## API 设计自查

### 接口设计
- [ ] URL 使用名词复数
- [ ] HTTP 方法正确
- [ ] 状态码使用恰当
- [ ] 有版本控制

### 请求设计
- [ ] 参数命名一致（驼峰/下划线）
- [ ] 必填参数有校验
- [ ] 敏感参数有脱敏

### 响应设计
- [ ] 统一响应格式
- [ ] 错误码有文档
- [ ] 分页格式统一

### 安全设计
- [ ] 需要认证的接口有权限控制
- [ ] 敏感操作有日志
- [ ] 有限流保护
```
