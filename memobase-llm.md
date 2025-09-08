# Memobase Server Implementation - Agent Memory System

## 项目概述

Memobase Server是一个基于FastAPI的agent memory系统，专门为LLM应用提供持久化的用户记忆功能。系统的核心是通过结构化的用户档案(Profile)和时间线事件(Event)来管理用户的长期记忆。

**核心特性：**
- **双重记忆机制**: Profile存储静态用户信息，Event记录动态时间线事件
- **智能缓冲区**: 批量处理对话数据，优化LLM调用成本
- **向量化搜索**: 基于pgvector的语义搜索能力
- **多项目隔离**: 支持多租户架构
- **Redis缓存**: 高性能的用户档案缓存

## Profile 和 Event 记忆类型详解

### Profile（用户档案）

Profile 是用户长期稳定的结构化记忆，用于存储用户的个人信息、偏好、习惯等相对静态的内容。Profile 以 topic-subtopic 的结构组织，便于分类管理。

#### Profile 数据模型

在 Memobase 中，Profile 通过 `UserProfile` 数据模型表示：

```python
@REG.mapped_as_dataclass
class UserProfile(Base):
    __tablename__ = "user_profiles"
    
    # 核心字段
    content: Mapped[str] = mapped_column(TEXT, nullable=False)  # 档案内容
    attributes: Mapped[dict] = mapped_column(JSONB, nullable=True, default=None)  # 属性信息
    
    # 关联字段
    user_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    project_id: Mapped[str] = mapped_column(VARCHAR(64), default=DEFAULT_PROJECT_ID)
```

其中 `attributes` 字段包含 `topic` 和 `sub_topic` 两个关键属性，用于对档案进行分类。

#### Profile 生成过程

Profile 的生成是一个多步骤的处理流程：

1. **对话摘要**：首先通过 LLM 对用户对话进行摘要，提取关键信息
2. **信息提取**：使用专门的提示词模板从摘要中提取结构化的用户信息
3. **智能合并**：将新提取的信息与现有档案进行智能合并，避免重复和冲突
4. **质量控制**：对过长的档案内容进行总结，对过多的 subtopic 进行筛选和整理

具体流程如下：
- `entry_chat_summary()`: 生成用户会话摘要
- `extract_topics()`: 从摘要中提取新的 topic-subtopic 结构化信息
- `merge_or_valid_new_memos()`: 智能合并新信息与现有档案
- `organize_profiles()`: 整理档案，控制数量
- `re_summary()`: 对过长的档案内容进行总结

#### Profile 配置

Memobase 支持通过配置定义允许的 Profile 主题和子主题：

```yaml
additional_user_profiles:
  basic_info:
    - name
    - age
    - language_spoken
  interest:
    - hobbies
    - foods
    - music
  work:
    - title
    - company
    - skills
```

#### Profile 提示词详解

Profile 的生成主要依赖于以下提示词：

1. **对话摘要提示词** (`summary_entry_chats.py`):
   - 角色设定：专家级信息记录员
   - 任务：从用户与助手的对话中提取用户信息、日程和事件
   - 输出格式：Markdown无序列表，包含时间信息

2. **信息提取提示词** (`extract_profile.py`):
   - 角色设定：专业心理学家
   - 任务：从备忘录中提取用户的重要档案信息
   - 输出格式：`TOPIC::SUB_TOPIC::MEMO` 的列表形式
   - 示例：
     ```
     - basic_info::name::Gus
     - interest::foods::Chinese food
     - education::level::High School
     - psychological::emotional_state::Feels bored with high school
     ```

3. **智能合并提示词** (`merge_profile_yolo.py`):
   - 角色设定：用户备忘录维护专家
   - 任务：判断新信息是直接添加、更新现有备忘录还是丢弃
   - 输出格式：带有操作指令的编号列表
   - 操作类型：
     - `APPEND`：直接添加
     - `UPDATE`：更新备忘录
     - `ABORT`：丢弃合并

#### Profile 示例

根据extract_profile.py的提示词格式，应该是`TOPIC::SUB_TOPIC::MEMO`的列表形式：

```
- basic_info::name::Gus
- basic_info::age::25
- interest::foods::Chinese food
- education::level::High School
- psychological::emotional_state::Feels bored with high school
```

#### 从对话生成 Profile 的示例

**原始对话**：
```
[2024/05/15] user: Hello, this is Gus, how are you?
[2024/05/15] assistant: I am fine, thank you!
[2024/05/15] user: I'm 25 now, how time flies!
[2024/05/15] user: I really dig into Chinese food
[2024/05/15] assistant: Got it, Gus!
[2024/05/15] user: write me a homework letter about my final exam, high school is really boring.
```

**第一步：对话摘要** (`entry_chat_summary()`输出)：
```
- User introduced himself as Gus and mentioned his age is 25. [mention 2024/05/15]
- User expressed interest in Chinese food. [mention 2024/05/15] 
- User mentioned final exam homework and feels high school is boring. [mention 2024/05/15]
```

**第二步：Profile提取** (`extract_topics()`输出，基于extract_profile.py提示词)：
```
- basic_info::name::Gus
- basic_info::age::25
- interest::foods::Chinese food
- education::level::High School
- psychological::emotional_state::Feels bored with high school
```

**第三步：数据库存储** (UserProfile表结构)：
```json
[
  {
    "id": "uuid1",
    "content": "Gus",
    "attributes": {"topic": "basic_info", "sub_topic": "name"},
    "user_id": "user_uuid",
    "project_id": "__root__"
  },
  {
    "id": "uuid2", 
    "content": "25",
    "attributes": {"topic": "basic_info", "sub_topic": "age"},
    "user_id": "user_uuid",
    "project_id": "__root__"
  }
  // ... 其他档案条目
]
```

### Event（用户事件）

Event 是用户时间线上的具体事件记录，用于存储用户的重要经历、决策、情感状态等动态信息。每个事件都有时间戳，并可包含向量嵌入以支持相似度搜索。

#### Event 数据模型

在 Memobase 中，Event 通过 `UserEvent` 和 `UserEventGist` 数据模型表示：

```python
@REG.mapped_as_dataclass
class UserEvent(Base):
    __tablename__ = "user_events"
    
    # 核心字段
    event_data: Mapped[dict] = mapped_column(JSONB)  # 事件数据
    embedding: Mapped[Vector] = mapped_column(Vector(dim=CONFIG.embedding_dim), nullable=True, default=None)  # 向量嵌入
    
    # 关联字段
    user_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    project_id: Mapped[str] = mapped_column(VARCHAR(64), default=DEFAULT_PROJECT_ID)

@REG.mapped_as_dataclass
class UserEventGist(Base):
    __tablename__ = "user_event_gists"
    
    # 核心字段
    gist_data: Mapped[dict] = mapped_column(JSONB)  # 事件要点
    embedding: Mapped[Vector] = mapped_column(Vector(dim=CONFIG.embedding_dim), nullable=True, default=None)  # 向量嵌入
    
    # 关联字段
    event_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    user_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    project_id: Mapped[str] = mapped_column(VARCHAR(64), default=DEFAULT_PROJECT_ID)
```

#### Event 生成过程

Event 的生成过程包括以下步骤：

1. **会话摘要**：生成用户会话的摘要内容
2. **事件标签提取**：通过 LLM 从摘要中提取事件标签（如情感、目标等）
3. **向量化处理**：为事件内容生成向量嵌入（如果启用）
4. **要点生成**：创建事件要点摘要（gist），便于快速检索

具体流程如下：
- `entry_chat_summary()`: 生成会话摘要
- `tag_event()`: 提取事件标签
- `append_user_event()`: 创建用户事件记录和关联的要点

#### Event 配置

Memobase 支持通过配置定义事件标签：

```yaml
event_tags:
  - name: "emotion"
    description: "Record the current emotion of user"
  - name: "goal"  
    description: "Record the current goal of user"
```

#### Event 提示词详解

Event 的生成主要依赖于以下提示词：

1. **事件标签提取提示词** (`event_tagging.py`):
   - 角色设定：事件标签专家
   - 任务：从事件摘要中提取特定标签的值
   - 输出格式：`TAG::VALUE` 的列表形式
   - 示例：
     ```
     - emotion::happy
     - goal::prepare for final exams
     ```

#### Event 示例

根据event_tagging.py提示词格式，事件标签应该是`TAG::VALUE`的列表形式：

**事件标签提取** (`tag_event()`输出)：
```
- emotion::bored
- goal::complete final exam homework
```

**最终Event数据结构** (存储在UserEvent表)：
```json
{
  "id": "event_uuid",
  "event_data": {
    "event_tip": "User mentioned preparing for final exams and feeling bored with high school",
    "event_tags": [
      {"tag": "emotion", "value": "bored"},
      {"tag": "goal", "value": "complete final exam homework"}
    ],
    "profile_delta": [
      {
        "content": "High School",
        "attributes": {"topic": "education", "sub_topic": "level"}
      }
    ]
  },
  "embedding": [0.1, -0.2, 0.3, ...],  # 1536维向量(如果启用embedding)
  "user_id": "user_uuid",
  "project_id": "__root__",
  "created_at": "2024-05-15T14:30:00Z"
}
```

#### Event Gist 示例

每个 Event 可以生成多个 Gist（要点），用于更精细的搜索：

```json
[
  {
    "id": "gist_uuid1",
    "gist_data": {
      "content": "- User is preparing for final exams"
    }
  },
  {
    "id": "gist_uuid2",
    "gist_data": {
      "content": "- User feels stressed about high school being boring"
    }
  }
]
```

#### 从对话生成 Event 的示例

**原始对话**：
```
[2024/05/15] user: Hello, this is Gus, how are you?
[2024/05/15] assistant: I am fine, thank you!
[2024/05/15] user: I'm 25 now, how time flies!
[2024/05/15] user: I really dig into Chinese food
[2024/05/15] assistant: Got it, Gus!
[2024/05/15] user: write me a homework letter about my final exam, high school is really boring.
```

**第一步：对话摘要** (`entry_chat_summary()`输出)：
```
- User introduced himself as Gus and mentioned his age is 25. [mention 2024/05/15]
- User expressed interest in Chinese food. [mention 2024/05/15]
- User mentioned final exam homework and feels high school is boring. [mention 2024/05/15]
```

**第二步：事件标签提取** (`tag_event()`输出，基于event_tagging.py提示词)：
```
- emotion::bored
- goal::complete final exam homework
```

**第三步：Event Gist自动生成** (从event_tip按行分解)：
- 原始event_tip: "- User preparing for final exams\n- User feels bored with high school"
- 自动分解为gist列表: ["- User preparing for final exams", "- User feels bored with high school"]

**最终存储结构**：
- **UserEvent表**: 完整的event_data + 主embedding
- **UserEventGist表**: 每个gist独立存储 + 独立embedding，便于细粒度搜索

## 核心架构

### 1. 目录结构
```
src/server/api/
├── api.py                    # FastAPI应用入口和路由定义
├── memobase_server/
│   ├── api_layer/           # API层：路由处理逻辑
│   ├── controllers/         # 控制器层：业务逻辑
│   ├── models/              # 数据模型定义
│   ├── llms/                # LLM集成模块
│   ├── prompts/             # 提示词模板
│   └── connectors.py        # 数据库连接管理
```

### 2. 数据模型架构

#### 核心表结构
- **users**: 用户基础信息
- **general_blobs**: 原始数据存储(聊天、文档等)
- **buffer_zones**: 缓冲区管理，批量处理原始数据
- **user_profiles**: 结构化用户档案
- **user_events**: 用户事件时间线
- **user_event_gists**: 事件精华摘要(支持向量搜索)

#### 关系设计
所有表都支持多项目(project_id)隔离，用户与其相关数据通过复合主键(id, project_id)关联。

## 核心架构和数据流

### 系统架构概览

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   API Layer     │ -> │   Controllers   │ -> │   Data Layer    │
├─────────────────┤    ├─────────────────┤    ├─────────────────┤
│ • blob.py       │    │ • blob.py       │    │ • PostgreSQL    │
│ • buffer.py     │    │ • buffer.py     │    │ • Redis Cache   │
│ • profile.py    │    │ • profile.py    │    │ • pgvector      │
│ • event.py      │    │ • event.py      │    │ • JSONB         │
│ • context.py    │    │ • context.py    │    └─────────────────┘
└─────────────────┘    └─────────────────┘
```

## ADD流程详细实现

### 1. 数据插入入口 (`POST /blobs/insert/{user_id}`)

**API路径**: `api_layer/blob.py:insert_blob()` → `controllers/blob.py:insert_blob()`

**完整流程步骤**：
1. **输入验证**: BlobData验证和计费检查
2. **数据存储**: 创建GeneralBlob记录存储原始数据  
3. **缓冲区插入**: 调用`insert_blob_to_buffer()`添加到BufferZone
4. **容量检测**: `detect_buffer_full_or_not()`检查是否达到token阈值
5. **触发处理**: 超过`max_chat_blob_buffer_token_size`时触发flush

**关键实现特性**:
- 支持多种blob类型: `chat`/`doc`/`summary`
- 自动token计算: `get_blob_token_size()`
- 异步/同步处理: `wait_process`参数控制
- 错误恢复: 失败时标记状态为`failed`

### 2. 缓冲区管理 (`controllers/buffer.py`)

**核心机制**:
```python
# 触发flush的条件：
- 缓冲区token总量超过max_chat_blob_buffer_token_size(默认1024)  
- 手动调用flush API: POST /buffer/flush/{user_id}
- 支持立即处理模式: wait_process=true

# flush_buffer_by_ids()处理流程：
1. 查询BufferZone表中status='idle'的记录
2. JOIN GeneralBlob表获取完整的blob数据
3. 更新BufferZone状态为'processing'防止重复处理
4. 调用对应的modal处理器: BLOBS_PROCESS[blob_type]
   - BlobType.chat → chat.process_blobs()  
   - BlobType.summary → summary.process_blobs()
5. 处理成功后更新状态为'done'
6. 根据persistent_chat_blobs配置决定是否删除原始blob
```

**错误处理**:
- 处理失败时状态标记为`failed`
- 事务回滚确保数据一致性
- 连接池状态监控: `log_pool_status()`

### 3. Chat Modal处理流程 (`controllers/modal/chat/`)

#### 3.1 入口总流程 (`__init__.py:process_blobs()`)

**主要步骤**：
```python
1. truncate_chat_blobs(): 限制处理token数量(max_chat_blob_buffer_process_token_size)
2. get_project_profile_config(): 获取项目配置
3. get_user_profiles(): 获取当前用户档案  
4. entry_chat_summary(): 生成用户会话摘要
5. asyncio.gather()并行处理：
   - process_profile_res(): 档案提取、合并、组织、总结
   - process_event_res(): 事件标签提取
6. handle_session_event(): 创建UserEvent记录
7. handle_user_profile_db(): 批量更新用户档案数据库
```

**返回数据结构**:
```python
ChatModalResponse(
    event_id=str,                    # 新创建的事件ID
    add_profiles=List[str],          # 新增档案ID列表
    update_profiles=List[str],       # 更新档案ID列表  
    delete_profiles=List[str]        # 删除档案ID列表
)
```

#### 3.2 档案提取 (`extract.py::extract_topics()`)
```python
# LLM调用链：
1. 使用当前用户档案构建上下文
2. 调用LLM提取新的topic-subtopic结构化信息
3. parse_string_into_profiles()解析LLM响应
4. attribute_unify()统一属性格式
5. 过滤允许的topic-subtopic组合

# 关键配置：
- 支持strict_mode限制提取范围
- project_profile_slots定义允许的档案结构
- 多语言prompt支持(中英文)
```

#### 3.3 档案合并 (`merge_yolo.py::merge_or_valid_new_memos()`)
```python
# 智能合并策略：
1. 新信息与现有档案的topic-subtopic匹配
2. 相同topic-subtopic进行内容合并
3. 全新topic-subtopic直接添加
4. 返回MergeAddResult{add: [], update: [], delete: []}

# LLM合并提示：
- 使用专门的merge prompt
- 保持信息的时效性和准确性
- 避免重复和冲突信息
```

#### 3.4 档案组织 (`organize.py::organize_profiles()`)
```python
# 档案数量控制：
1. 检查每个topic下的subtopic数量
2. 超过max_profile_subtopics时触发整理
3. LLM选择保留最重要的subtopic
4. 自动删除过时或不重要的档案
```

#### 3.5 档案总结 (`summary.py::re_summary()`)
```python
# 长度控制机制：
1. 检查档案内容token长度
2. 超过max_single_profile_content_token_size时触发总结
3. LLM重新总结保持核心信息
4. 更新数据库中的档案内容
```

### 4. Event处理流程 (`memobase_server/controllers/event.py`)

#### 4.1 事件创建 (`append_user_event()`)
```python
# 处理步骤：
1. EventData验证事件数据格式
2. 生成事件embedding(如果enable_event_embedding=True)
3. 处理event_tip生成event_gists
4. 为每个gist生成独立embedding
5. 创建UserEvent和UserEventGist记录

# Embedding生成：
- 使用event_embedding_str()格式化事件内容
- 支持OpenAI/Jina等embedding provider
- 维度检查确保数据库兼容性
```

#### 4.2 事件标记 (`modal/chat/event_summary.py::tag_event()`)
```python
# 事件属性提取：
1. 读取项目配置的event_tags
2. LLM分析会话内容提取事件属性
3. 返回结构化的event_tags列表
4. 支持emotion、goal等预定义标签

# 配置示例：
event_tags:
  - name: "emotion"
    description: "Record the current emotion of user"
  - name: "goal"  
    description: "Record the current goal of user"
```

### 5. 数据库存储过程

#### 5.1 PostgreSQL + pgvector设计
```python
# 关键特性：
- 支持向量相似度搜索(cosine distance)
- JSONB存储灵活的事件和档案数据
- 复合主键支持多项目隔离
- 外键约束保证数据一致性
- 索引优化查询性能
```

#### 5.2 事务管理
```python
# 原子操作保证：
1. 使用SQLAlchemy Session()管理事务
2. 关键操作点：
   - buffer flush时的状态更新
   - profile的add/update/delete操作
   - event创建与gist关联
3. 异常时自动rollback，状态标记为failed
```

#### 5.3 缓存策略 (`Redis`)
```python
# 缓存机制：
- user_profiles缓存(TTL: cache_user_profiles_ttl)
- 自动缓存刷新机制
- 缓存失效时回退到数据库查询
```

## SEARCH和RETRIEVAL流程详细实现

### 1. 向量搜索系统

#### 1.1 事件向量搜索 (`controllers/event.py:search_user_events()`)

**前置条件**: `enable_event_embedding=true` 且配置了embedding provider

**搜索流程**：
```python
1. get_embedding(): 查询文本生成向量 (phase="query")
2. pgvector查询: UserEvent表的embedding字段进行cosine similarity搜索
3. 过滤条件:
   - similarity > similarity_threshold (默认0.2)
   - created_at > (now - time_range_in_days) 
   - user_id + project_id匹配
4. 排序: ORDER BY similarity DESC
5. 限制: LIMIT topk (默认10)
```

**SQL查询结构**:
```sql
SELECT *, (1 - embedding <=> $query_embedding) as similarity
FROM user_events 
WHERE user_id = $user_id 
  AND project_id = $project_id
  AND created_at > (now() - interval '$time_range_in_days days')
  AND (1 - embedding <=> $query_embedding) > $similarity_threshold
ORDER BY similarity DESC
LIMIT $topk
```

#### 1.2 事件Gist搜索 (`controllers/event_gist.py:search_user_event_gists()`)

**优势**: 更细粒度的搜索，每个事件可分解为多个gist进行独立向量化

**实现特点**:
- 搜索`UserEventGist`表而非`UserEvent`表
- 一个事件可产生多个gist，提高搜索召回率
- 相同的向量搜索机制和过滤条件
- 在context生成中优先使用gist搜索

### 3. 事件标签过滤 (`filter_user_events()`)

```python
# 结构化过滤：
1. has_event_tag: 检查事件是否包含特定标签
2. event_tag_equal: 精确匹配标签值
3. 使用PostgreSQL JSONB操作符(@>)进行高效查询
4. 支持多条件组合过滤
```

### 2. Context生成系统 (`controllers/context.py:get_user_context()`)

#### 2.1 核心功能
智能组合用户档案和事件数据，生成适合LLM的上下文字符串

#### 2.2 并行数据获取
```python
# asyncio.gather()并行执行：
profile_result = get_user_profiles_data(...)  # 获取和处理档案数据
event_result = get_user_event_gists_data(...) # 获取事件gist数据
```

#### 2.3 档案数据处理流程
```python
1. get_user_profiles(): 从Redis缓存或数据库获取档案
2. filter_profiles_with_chats(): (可选)基于当前对话过滤相关档案
3. truncate_profiles(): 档案截断和排序
   - prefer_topics: 优先话题排序
   - only_topics: 仅包含指定话题
   - max_token_size: token数量限制  
   - max_subtopic_size: subtopic数量限制
   - topic_limits: 每个topic的具体限制
4. 格式化为字符串: "topic::sub_topic: content"
```

#### 2.4 事件数据处理流程
```python
1. 如果有chats且启用embedding:
   - search_user_event_gists(): 基于对话内容语义搜索
2. 否则:
   - get_user_event_gists(): 获取时间范围内的最新事件
3. truncate_event_gists(): 根据剩余token空间截断事件
```

#### 2.5 Token分配策略
```python
max_profile_token_size = int(max_token_size * profile_event_ratio)  # 默认比例分配

# fill_window_with_events=true时:
max_event_token_size = max_token_size - actual_profile_tokens     # 用事件填满剩余空间

# 否则:
max_event_token_size = min(
    max_token_size - actual_profile_tokens,
    max_token_size - max_profile_token_size
)
```

#### 2.6 最终输出格式
```python
ContextData(
    context=context_prompt_func(profile_section, event_section)
)

# 其中：
# profile_section = "- basic_info::name: John\n- interest::hobby: reading"  
# event_section = "- user bought a new car\n- user feels happy about the purchase"
```

### 5. 档案搜索优化

#### 5.1 智能过滤 (`post_process/profile.py::filter_profiles_with_chats()`)
```python
# 上下文相关过滤：
1. 分析当前对话内容
2. LLM判断哪些档案与当前对话相关
3. 优先返回相关档案
4. 提高context质量和相关性
```

#### 5.2 截断策略 (`truncate_profiles()`)
```python
# 多维度截断：
- prefer_topics: 优先级话题
- only_topics: 仅包含指定话题  
- max_token_size: token数量限制
- max_subtopic_size: subtopic数量限制
- topic_limits: 每个topic的限制数量
```

## 系统特性

### 1. 性能优化
- 异步处理避免阻塞
- 批量操作减少数据库调用
- 缓冲区机制分摊计算成本
- Redis缓存加速频繁查询

### 2. 可扩展性
- 多项目隔离支持
- 插件化LLM provider
- 可配置的档案结构
- 灵活的事件标签系统

### 3. 可靠性
- 事务管理保证数据一致性
- 错误状态跟踪和恢复
- 缓存失效回退机制
- embedding维度验证

### 4. 多语言支持
- 中英文prompt模板
- 语言配置自动切换
- 统一的attribute处理

## 总结

Memobase Server通过以下核心机制实现了高效的agent memory系统：

1. **双层记忆模型**: Profile存储结构化长期记忆，Event记录时序化动态记忆
2. **智能缓冲机制**: 批量处理减少LLM调用成本，支持同步/异步模式
3. **向量化检索**: 基于pgvector的语义搜索，支持细粒度的gist搜索
4. **多级缓存**: Redis档案缓存 + PostgreSQL持久化存储  
5. **灵活配置**: 支持多种LLM provider、embedding provider和项目定制

该系统为LLM应用提供了生产级的长期记忆能力，支持大规模部署和多租户隔离。