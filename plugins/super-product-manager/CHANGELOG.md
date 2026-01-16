# Changelog

All notable changes to this project will be documented in this file.

## [1.3.0] - 2025-01-15

### prd 技能升级 (v1.1.0 → v1.2.0)

#### 新增模板（4个PRD类型）
- `feature-prd.md` - 功能PRD：面向用户的功能需求，侧重用户价值和业务逻辑
- `data-prd.md` - 数据PRD：数据驱动的功能需求，侧重数据指标和分析
- `api-prd.md` - API PRD：API接口需求，侧重技术对接
- `general-prd.md` - 通用PRD：综合型PRD，覆盖所有基础场景

#### SKILL.md 完整重写
- **PRD类型识别**：根据关键词自动识别PRD类型（功能/数据/API/通用）
- **快速决策树**：清晰的选择逻辑流程图
- **示例对话**：3个完整示例（功能PRD、数据PRD、API PRD）
- **技能衔接**：与idea-concretization、market-validation、tech-spec、user-story的配合流程
- **质量检查清单**：完整性检查和质量检查
- **常见错误**：6种常见错误和正确做法
- **最佳实践**：5项PRD编写最佳实践

#### 从空白到完整
- 原 SKILL.md 仅35行基础框架
- 新 SKILL.md 超过300行完整内容
- 从0个模板到4个详细模板
- 达到与 tech-spec、market-validation 同等级别的专业水准

### market-research 技能升级 (v1.0.0 → v1.1.0)

#### 新增模板
- `swot-analysis.md` - SWOT分析：快速评估优势、劣势、机会、威胁的战略分析工具
- `user-segmentation.md` - 用户细分：识别和细分目标用户群体，支持B2C和B2B场景
- `pricing-research.md` - 定价研究：市场定价策略、价格敏感度测试和竞品定价分析
- `pestel-analysis.md` - PESTEL分析：宏观环境分析框架，涵盖政治、经济、社会、技术、环境、法律六个维度

#### 增强功能
- **方法选择决策树**：根据具体问题快速选择合适的调研方法
- **场景-方法映射表**：8种常见场景的推荐方法组合
- **快速诊断清单**：7个核心问题快速评估调研需求
- **技能衔接说明**：与idea-concretization和market-validation的配合使用流程

### market-validation 技能升级 (v1.1.0 → v1.3.0)

#### 新增功能
- **完整的5维度实验设计框架**：为所有验证模板添加了详细的实验设计框架，包含：
  1. 核心价值验证
  2. 用户需求验证
  3. 商业可行性验证
  4. 技术/运营可行性验证
  5. 市场/竞争验证

#### 新增模板类型
- `ideation.md` - 创意生成验证模板
- `education.md` - 教育/培训产品验证模板
- `game.md` - 游戏/娱乐产品验证模板
- `social.md` - 社交产品验证模板
- `tool.md` - 工具类产品验证模板

#### 完善现有模板
以下模板已完善，添加了完整的实验设计框架和决策阈值：
- `app.md` - 应用类（App/Web）验证
- `consumer.md` - 消费品/食品验证
- `saas.md` - SaaS/B2B验证
- `service.md` - 服务/咨询验证
- `platform.md` - 平台/双边验证
- `hardware.md` - 硬件/IoT验证
- `content.md` - 内容/媒体验证

#### 配置文件更新
- 更新 `market-research/SKILL.md` 到 v1.1.0
- 更新 `market-validation/SKILL.md` 到 v1.3.0
- 更新 `plugin.json` 到 v1.3.0
- 更新 `marketplace.json` 到 v1.3.0
- 新增统一的版本管理和changelog

### 改进
- market-research：每个新模板包含详细的分析框架、实用模板和常见错误
- market-validation：每个模板包含详细的决策阈值（继续推进/需要优化/重新构思）
- 统一的证据门槛示例格式
- 详细的实验设计方法论，包括方法、样本、周期和指标

## [1.2.0] - 2025-01-XX

### idea-concretization 技能升级
- 重命名验证模板
- 完善模板结构

---

## 版本说明

- **主版本号**：重大架构变更或不兼容更新
- **次版本号**：新增功能或模板
- **修订号**：bug修复或小改进
