# IntelliTutor 用户隔离实现方案

## 当前状态
- auth.py 有 JWT 登录/注册，admin 路由有鉴权
- 其余所有 API 路由（sessions、knowledge、chat、settings 等）**完全无认证无隔离**
- 数据存储没有按用户区分

## 目标
实现完整的用户隔离：不同用户登录后只能看到自己的会话、知识库、设置。

## 实现方案

### 1. 数据库层
**文件**: `deeptutor/services/session/sqlite_store.py`
- sessions 表加 `user_id TEXT` 列（migration：ALTER TABLE ADD COLUMN）
- 所有查询加 `WHERE user_id = ?`
- create_session 时写入当前 user_id

### 2. 认证中间件
**文件**: `deeptutor/api/auth_deps.py`（已创建）
- `get_optional_user`: 可选认证，有 token 返回 user，没有返回 None
- `get_current_user`: 强制认证，401
- 注意：JWT_SECRET 必须和 auth.py 里的一致！

### 3. 路由层改造
给以下路由加 `Depends(get_optional_user)` 或 `Depends(get_current_user)`：

#### 必须强制认证（影响用户数据）：
- `sessions.py` - 列出/创建/删除会话 → 按 user_id 过滤
- `knowledge.py` - 知识库 CRUD → 按 user_id 过滤
- `settings.py` - 用户设置 → 按 user_id 隔离
- `chat.py` - 聊天 → 按 user_id
- `solve.py` - 解题 → 按 user_id
- `question.py` - 提问 → 按 user_id
- `co_writer.py` - 写作 → 按 user_id
- `notebook.py` - 笔记 → 按 user_id
- `memory.py` - 记忆 → 按 user_id
- `book.py` - 书本 → 按 user_id

#### 可选认证（公共功能但记录用户）：
- `system.py` - 系统信息
- `tutorbot.py` - 机器人

### 4. 知识库存储隔离
**文件**: `deeptutor/knowledge/manager.py`
- 知识库存储路径从 `data/user/knowledge_bases/{kb_name}/` 改为 `data/user/knowledge_bases/{user_id}/{kb_name}/`
- 如果 user_id 为 None，保持原路径（向后兼容）

### 5. 设置隔离
**文件**: `deeptutor/services/config/env_store.py` 或相关文件
- 设置路径从 `data/user/settings/` 改为 `data/user/settings/{user_id}/`
- 如果 user_id 为 None，保持原路径

### 6. 前端改造
**文件**: `web/lib/auth-client.ts`
- `authHeaders()` 已经存在，确保所有 API 调用都使用它
- 检查 `web/lib/api.ts` 的 fetch wrapper 是否自动附带 auth headers

### 7. 关键约束
- **向后兼容**：没有 token 时（未登录/开发模式）保持现有行为
- **不要破坏 auth.py** 里的现有认证逻辑，只复用
- **JWT_SECRET** 从 auth.py 里提取，确保一致（或者改成从 env 读取）
- **不要删现有数据**，migration 用 ALTER TABLE ADD COLUMN

### 文件位置
- 项目根目录: `/Users/pigou/.openclaw/workspace/ai-reading-companion/deeptutor/`
- 后端 Python: `deeptutor/`
- 前端: `web/`
- 认证路由: `deeptutor/api/routers/auth.py`
- 认证依赖: `deeptutor/api/auth_deps.py`（新创建）
