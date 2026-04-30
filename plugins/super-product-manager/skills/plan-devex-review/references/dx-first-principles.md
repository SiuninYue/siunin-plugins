# DX 第一原则：完整描述 + 金标准对标

按需加载。仅在需要原则完整描述或金标准参考时读取本文件。

---

## 原则 1：Zero Friction Onboarding

**定义**：新开发者应能在 5 分钟内完成 Hello World，不需要任何人工协助。

**评估方式**：
- 计时实测：从打开文档到看到第一个输出
- 统计安装步骤数（≤ 3 步为优秀）
- 统计需要手动创建的文件数（0 为优秀）

**金标准**：
- **Stripe**：API Key 申请 → 第一个 API 调用 < 3 分钟，文档首页有可直接运行的代码
- **Tailwind CSS**：一行 CDN 引入即可开始使用，零配置可选
- **Vercel**：`vercel deploy` 一条命令，60 秒内拿到线上 URL

---

## 原则 2：Progressive Complexity

**定义**：简单任务简单做，复杂任务可做。不强迫初学者先掌握高级概念才能完成基础任务。

**评估方式**：
- "Hello World" 代码行数（≤ 10 行为优秀）
- 从基础用法到高级用法的跨越是否有明确的学习路径
- 是否存在"必须理解 X 才能做 Y，但 Y 是入门任务"的反模式

**金标准**：
- **React**：函数组件 + JSX 即可入门，Hooks/Context/Suspense 在需要时再学
- **Tailwind**：直接在 class 里写样式，不需要先理解 utility-first 哲学
- **Express.js**：3 行代码起一个 HTTP 服务器，中间件/路由/错误处理按需引入

---

## 原则 3：Errors Are Teachers

**定义**：错误信息应该主动教导开发者，而不只是报告失败。好的错误包含：发生了什么 + 为什么 + 怎么修。

**评估方式**：
- 随机触发 5 个常见错误，评估信息质量
- 检查是否有"错误码 + 文档链接"的模式
- 检查错误堆栈是否有足够上下文（文件名 + 行号 + 变量值）

**金标准**：
- **TypeScript**：错误信息包含类型不匹配的具体字段路径，而不只是"Type 'X' is not assignable to type 'Y'"
- **Rust**：编译器错误包含"考虑这样修改："的具体建议和代码片段
- **Next.js**：运行时错误在浏览器中显示源码位置 + 错误说明 + 文档链接

---

## 原则 4：Predictability

**定义**：相似的操作有相似的结果。API 行为符合最小惊讶原则（principle of least astonishment）。

**评估方式**：
- 如果 `getUser(id)` 返回 User，那 `getUsers()` 是否返回 User[]？
- 错误处理是否一致（都 throw？都返回 {error}？）
- 命名是否一致（camelCase vs snake_case 混用？）
- 副作用是否清晰标注？

**金标准**：
- **Stripe API**：所有列表接口都返回 `{data: [], has_more: bool, ...}` 统一格式
- **React**：所有 Hook 都以 `use` 开头，返回值结构可预期
- **TypeScript**：类型系统的规则在整个语言中高度一致

---

## 原则 5：Fast Feedback Loops

**定义**：开发者的每一个操作应该能快速得到反馈。本地开发 < 1 秒，CI < 5 分钟。

**评估方式**：
- Hot reload 速度实测
- 测试套件运行时间
- CI pipeline 总时长
- 错误到屏幕上显示的延迟

**金标准**：
- **Vite**：HMR 更新 < 50ms，冷启动 < 300ms
- **Vitest**：测试运行比 Jest 快 2-10 倍，Watch 模式即时反馈
- **Vercel Preview**：每个 PR 自动部署，2 分钟内可访问预览 URL

---

## 原则 6：Escape Hatches

**定义**：高层抽象必须提供低层逃生口。不允许"高级功能无法实现，因为框架不支持"的情况。

**评估方式**：
- 是否有 `raw`/`unsafe`/`native` 级别的 API？
- 能否绕过默认行为？
- 插件/扩展机制是否足够强大？
- 有没有"不可能完成"的常见用例（即框架限制）？

**金标准**：
- **Next.js**：提供 `next.config.js` 修改 Webpack，提供 `pages/_app.tsx` 控制全局布局
- **Tailwind**：允许 `[arbitrary-value]` 直接写任意 CSS 值
- **Prisma**：提供 `$queryRaw` 在需要时执行原始 SQL

---

## 原则 7：Docs as Product

**定义**：文档不是附属品，而是开发者体验的核心部分。好的文档像好的产品一样被设计。

**评估方式**：
- 文档是否与代码同步更新？（版本标注是否准确）
- 是否有搜索功能且结果准确？
- Guide（教程）+ Reference（参考）+ Cookbook（示例）三类是否齐全？
- 代码示例是否可以直接运行？

**金标准**：
- **Stripe**：文档被公认为行业最佳，每个 API 都有多语言示例、错误说明、测试模式
- **React**：新版文档重构为交互式学习路径，区分初学者 / 有经验开发者
- **MDN**：浏览器 API 参考的终极标准，兼容性表格 + 示例 + 详细说明

---

## 原则 8：Version Stability

**定义**：升级依赖版本不应破坏已有代码。Breaking changes 必须有清晰标注和迁移路径。

**评估方式**：
- CHANGELOG 是否区分 breaking / non-breaking？
- 是否有 codemod 工具自动迁移代码？
- Deprecation warning 是否提前足够多版本给出？
- 是否遵循 SemVer？

**金标准**：
- **React**：每次 major 版本提供 migration guide，提供 `react-codemod` 工具
- **TypeScript**：发布前有详细的 breaking changes 说明，社区有充分讨论窗口
- **Node.js**：LTS 策略明确，安全补丁 backport 策略公开透明
