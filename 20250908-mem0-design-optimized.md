# Mem0 Event记忆优化设计文档

## 背景

大模型的上下文窗口是有限的，在对话长度超过大模型的上下文窗口大小的时候，大模型无法保持对话的连贯性和一致性。记忆系统是目前的解决方案之一，其中mem0是一种可扩展的以内存为中心的架构，它通过从正在进行的对话中动态提取、评估和管理重要信息的方式进行记忆的提取和更新。但是mem0无法有效处理有时效性的信息，针对这个问题，我们希望引入事件记忆来提升mem0的性能。

### 当前Mem0架构分析

Mem0目前实际支持以下记忆类型：
- **通用记忆（General Memory）**：默认的主要记忆类型，通过向量存储用户信息和对话内容，支持智能的ADD/UPDATE/DELETE操作
- **程序性记忆（Procedural Memory）**：特殊的记忆类型，需要`agent_id`和`memory_type="procedural_memory"`参数，使用专门的LLM提示词生成程序性知识摘要

**注意**：虽然枚举中定义了`SEMANTIC`和`EPISODIC`类型，但当前代码中没有这两种类型的特殊处理逻辑，它们会按通用记忆处理。

### Event记忆的必要性

参考Memobase的设计，我们需要在现有通用记忆的基础上，区分两种不同性质的记忆内容：

1. **Profile记忆**（对应当前通用记忆的一部分）：
   - 静态、结构化的用户信息（姓名、偏好、技能等）
   - 相对稳定，变化频率低
   - 需要智能合并，避免重复信息
   - **这部分功能当前的mem0已经支持**

2. **Event记忆**（新增的记忆处理方式）：
   - 动态、时序性的事件信息
   - 带有明确时间戳
   - 累积存储，记录用户的行为轨迹和经历
   - **这是我们需要新增的功能**

当前mem0的通用记忆主要处理的是Profile类型的信息，缺乏对时序事件的专门处理能力。

## 概要设计

### 设计原则

1. **最小化改动**：复用现有的向量存储架构，通过metadata区分记忆类型
2. **配置驱动**：通过配置控制Event记忆功能的启用和参数
3. **向后兼容**：保持现有API的兼容性
4. **性能优化**：通过并行处理提升性能

### 核心改动

1. **配置扩展**：在`MemoryConfig`中新增Event记忆相关配置
2. **记忆类型扩展**：在`MemoryType`枚举中新增`EVENT`类型
3. **提示词扩展**：新增Event记忆提取的专用提示词
4. **处理流程扩展**：在add/search流程中并行处理Profile和Event记忆

## 详细设计

### 1. 配置系统扩展

#### 1.1 MemoryType枚举扩展

```python
# mem0/configs/enums.py
from enum import Enum

class MemoryType(Enum):
    SEMANTIC = "semantic_memory"     # 现有，但未特殊处理
    EPISODIC = "episodic_memory"     # 现有，但未特殊处理  
    PROCEDURAL = "procedural_memory" # 现有，有特殊处理逻辑
    EVENT = "event_memory"           # 新增
```

**说明**：
- `SEMANTIC`和`EPISODIC`虽然已定义但当前代码中无特殊处理
- `PROCEDURAL`有完整的实现逻辑
- `EVENT`是我们新增的类型

#### 1.2 MemoryConfig配置扩展

```python
# mem0/configs/base.py
@dataclass
class MemoryConfig:
    # ... 现有配置 ...
    
    # Event记忆相关配置
    enable_event_memory: bool = True  # 是否启用Event记忆
    event_memory_collection_suffix: str = "_events"  # Event记忆集合后缀
    event_time_window_days: int = 30  # Event搜索时间窗口（天）
    event_max_facts: int = 5  # 每次提取的最大Event数量
    custom_event_extraction_prompt: Optional[str] = None  # 自定义Event提取提示词
```

### 2. 数据结构设计

#### 2.1 Event记忆的metadata结构

```python
# Event记忆的metadata结构
{
    "data": "用户今天买了一辆新车，感到很兴奋",
    "hash": "md5_hash_of_data",
    "memory_type": "event_memory",  # 标识为Event记忆
    "event_timestamp": "2024-09-08T14:30:00Z",  # 事件时间戳
    "event_tags": ["购买", "情感:兴奋"],  # 事件标签
    "created_at": "2024-09-08T14:30:00Z",
    "user_id": "user_123",
    "agent_id": "agent_456",
    "run_id": "run_789"
}
```

#### 2.2 通用记忆的metadata结构（现有）

```python
# 当前mem0通用记忆的metadata结构
{
    "data": "用户喜欢中式料理",
    "hash": "md5_hash_of_data", 
    "created_at": "2024-09-08T14:30:00Z",
    "updated_at": "2024-09-08T14:35:00Z",  # 更新时添加
    "user_id": "user_123",
    "agent_id": "agent_456",  # 可选
    "run_id": "run_789",      # 可选
    "actor_id": "actor_001",  # 可选，来自message的name字段
    "role": "user"            # 可选，来自message的role字段
}
```

**注意**：当前的通用记忆没有明确的`memory_type`字段，我们建议为其添加以便区分。

### 3. 向量存储策略

#### 3.1 复用现有向量存储

**优化方案**：不创建独立的`event_vector_store`，而是：

1. **通过collection区分**：
   - Profile记忆：使用原collection名称
   - Event记忆：使用`{原collection名称}_events`

2. **通过metadata过滤**：
   - 在搜索时通过`memory_type`字段过滤不同类型的记忆
   - 保持数据隔离的同时复用基础设施

#### 3.2 Memory类扩展

```python
class Memory(MemoryBase):
    def __init__(self, config: MemoryConfig = MemoryConfig()):
        # ... 现有初始化代码 ...
        
        # Event记忆的向量存储（复用同一个provider，不同collection）
        if self.config.enable_event_memory:
            event_config = deepcopy(self.config.vector_store.config)
            event_config.collection_name = f"{self.collection_name}{self.config.event_memory_collection_suffix}"
            self.event_vector_store = VectorStoreFactory.create(
                self.config.vector_store.provider,
                event_config
            )
        else:
            self.event_vector_store = None
```

### 4. 提示词设计

#### 4.1 Event提取提示词

```python
# mem0/configs/prompts.py

EVENT_RETRIEVAL_PROMPT = """你是一个专门从对话中提取事件信息的专家。你的任务是从用户与助手的对话中识别和提取具有时间性的事件。

## 什么是事件记忆
事件记忆是指用户经历的具体事件、行为、活动或状态变化，这些信息：
- 具有明确的时间特征
- 代表用户的具体经历或行为
- 可能包含情感、决策、目标等信息
- 与特定的时间点或时间段相关

## 提取规则
1. 关注用户的具体行为和经历
2. 包含时间信息（如果对话中提及）
3. 记录情感状态变化
4. 记录重要决策和目标
5. 忽略纯粹的偏好或静态信息

## 输出格式
请以JSON格式输出，包含一个"events"数组：

```json
{
  "events": [
    "用户今天买了一辆新车",
    "用户对购车感到兴奋",
    "用户计划下周开车去旅行"
  ]
}
```

## 示例
输入对话：
User: 我今天终于买了那辆车，太兴奋了！下周计划开它去海边。
Assistant: 恭喜你！新车一定很棒。

输出：
```json
{
  "events": [
    "用户今天购买了新车",
    "用户对购买新车感到兴奋",
    "用户计划下周开车去海边旅行"
  ]
}
```
"""

def get_event_retrieval_messages(messages: str) -> tuple[str, str]:
    """
    获取事件提取的系统和用户提示词
    
    Args:
        messages: 解析后的对话内容
        
    Returns:
        tuple: (系统提示词, 用户提示词)
    """
    system_prompt = EVENT_RETRIEVAL_PROMPT
    user_prompt = f"请从以下对话中提取事件信息：\n\n{messages}"
    
    return system_prompt, user_prompt
```

### 5. 核心方法实现

#### 5.1 add方法扩展

```python
def add(self, messages, *, user_id: Optional[str] = None, ...):
    """扩展现有add方法以支持Event记忆"""
    
    processed_metadata, effective_filters = _build_filters_and_metadata(...)
    
    # ... 现有逻辑 ...
    
    with concurrent.futures.ThreadPoolExecutor() as executor:
        # 现有的Profile记忆处理
        future1 = executor.submit(
            self._add_to_vector_store, 
            messages, processed_metadata, effective_filters, infer
        )
        
        # 新增的Event记忆处理
        future2 = executor.submit(
            self._add_event_to_vector_store, 
            messages, processed_metadata, effective_filters, infer
        ) if self.config.enable_event_memory else None
        
        # 图存储处理
        future3 = executor.submit(self._add_to_graph, messages, effective_filters)
        
        # 等待所有任务完成
        futures = [future1, future3]
        if future2:
            futures.append(future2)
        concurrent.futures.wait(futures)
        
        profile_result = future1.result()
        event_result = future2.result() if future2 else []
        graph_result = future3.result()
    
    # 合并结果
    if self.api_version == "v1.1":
        result = {"results": profile_result + event_result}
        if self.enable_graph:
            result["relations"] = graph_result
        return result
    else:
        return profile_result + event_result
```

#### 5.2 Event记忆添加核心方法

```python
def _add_event_to_vector_store(self, messages, metadata, filters, infer):
    """添加Event记忆到向量存储"""
    
    if not self.config.enable_event_memory or not self.event_vector_store:
        return []
    
    if not infer:
        # 直接存储模式：将所有非系统消息作为事件存储
        return self._store_raw_events(messages, metadata)
    
    # 智能提取模式
    parsed_messages = parse_messages(messages)
    
    # 使用Event专用提示词
    if self.config.custom_event_extraction_prompt:
        system_prompt = self.config.custom_event_extraction_prompt
        user_prompt = f"Input:\n{parsed_messages}"
    else:
        system_prompt, user_prompt = get_event_retrieval_messages(parsed_messages)
    
    # LLM提取事件
    response = self.llm.generate_response(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        response_format={"type": "json_object"}
    )
    
    try:
        response = remove_code_blocks(response)
        extracted_events = json.loads(response).get("events", [])
    except Exception as e:
        logger.error(f"Error extracting events: {e}")
        extracted_events = []
    
    if not extracted_events:
        logger.debug("No events extracted from messages")
        return []
    
    # 存储提取的事件
    returned_events = []
    current_time = datetime.now(pytz.timezone("US/Pacific")).isoformat()
    
    for event_text in extracted_events[:self.config.event_max_facts]:
        event_metadata = deepcopy(metadata)
        event_metadata["memory_type"] = MemoryType.EVENT.value
        event_metadata["event_timestamp"] = current_time
        
        # 生成embedding并存储
        embeddings = self.embedding_model.embed(event_text, "add")
        memory_id = self._create_event_memory(event_text, embeddings, event_metadata)
        
        returned_events.append({
            "id": memory_id,
            "memory": event_text,
            "event": "ADD",
            "memory_type": MemoryType.EVENT.value,
            "event_timestamp": current_time
        })
    
    return returned_events

def _store_raw_events(self, messages, metadata):
    """直接存储原始消息作为事件"""
    returned_events = []
    current_time = datetime.now(pytz.timezone("US/Pacific")).isoformat()
    
    for message_dict in messages:
        if (message_dict.get("role") == "system" or 
            not isinstance(message_dict, dict) or
            not message_dict.get("content")):
            continue
            
        event_metadata = deepcopy(metadata)
        event_metadata["memory_type"] = MemoryType.EVENT.value
        event_metadata["event_timestamp"] = current_time
        event_metadata["role"] = message_dict["role"]
        
        if message_dict.get("name"):
            event_metadata["actor_id"] = message_dict["name"]
        
        content = message_dict["content"]
        embeddings = self.embedding_model.embed(content, "add")
        memory_id = self._create_event_memory(content, embeddings, event_metadata)
        
        returned_events.append({
            "id": memory_id,
            "memory": content,
            "event": "ADD",
            "memory_type": MemoryType.EVENT.value,
            "role": message_dict["role"],
            "event_timestamp": current_time
        })
    
    return returned_events

def _create_event_memory(self, data, embeddings, metadata):
    """创建Event记忆"""
    memory_id = str(uuid.uuid4())
    metadata["data"] = data
    metadata["hash"] = hashlib.md5(data.encode()).hexdigest()
    
    if "created_at" not in metadata:
        metadata["created_at"] = datetime.now(pytz.timezone("US/Pacific")).isoformat()
    
    self.event_vector_store.insert(
        vectors=[embeddings],
        ids=[memory_id],
        payloads=[metadata]
    )
    
    # 记录历史（复用现有历史表，通过memory_type区分）
    self.db.add_history(
        memory_id,
        None,
        data,
        "ADD",
        created_at=metadata.get("created_at"),
        actor_id=metadata.get("actor_id"),
        role=metadata.get("role")
    )
    
    return memory_id
```

#### 5.3 search方法扩展

```python
def search(self, query: str, *, user_id: Optional[str] = None, ...):
    """扩展搜索以支持Event记忆"""
    
    _, effective_filters = _build_filters_and_metadata(...)
    
    with concurrent.futures.ThreadPoolExecutor() as executor:
        # Profile记忆搜索
        future_profile = executor.submit(
            self._search_vector_store, query, effective_filters, limit, threshold
        )
        
        # Event记忆搜索
        future_event = executor.submit(
            self._search_event_vector_store, query, effective_filters, limit, threshold
        ) if self.config.enable_event_memory else None
        
        # 图搜索
        future_graph = executor.submit(
            self.graph.search, query, effective_filters, limit
        ) if self.enable_graph else None
        
        # 等待完成
        futures = [future_profile]
        if future_event:
            futures.append(future_event)
        if future_graph:
            futures.append(future_graph)
            
        concurrent.futures.wait(futures)
        
        profile_memories = future_profile.result()
        event_memories = future_event.result() if future_event else []
        graph_entities = future_graph.result() if future_graph else None
    
    # 合并搜索结果
    all_memories = self._merge_search_results(profile_memories, event_memories)
    
    if self.enable_graph:
        return {"results": all_memories, "relations": graph_entities}
    else:
        return {"results": all_memories}

def _search_event_vector_store(self, query, filters, limit, threshold):
    """搜索Event记忆"""
    if not self.event_vector_store:
        return []
    
    embeddings = self.embedding_model.embed(query, "search")
    
    # 添加时间窗口过滤
    time_threshold = datetime.now(pytz.timezone("US/Pacific")) - timedelta(
        days=self.config.event_time_window_days
    )
    
    # 搜索Event记忆
    memories = self.event_vector_store.search(
        query=query,
        vectors=embeddings,
        limit=limit,
        filters={**filters, "memory_type": MemoryType.EVENT.value}
    )
    
    # 处理结果格式
    formatted_memories = []
    for mem in memories:
        # 时间过滤
        event_time_str = mem.payload.get("event_timestamp")
        if event_time_str:
            event_time = datetime.fromisoformat(event_time_str.replace('Z', '+00:00'))
            if event_time < time_threshold:
                continue
        
        if threshold is None or mem.score >= threshold:
            memory_dict = self._format_memory_item(mem)
            memory_dict["memory_type"] = MemoryType.EVENT.value
            formatted_memories.append(memory_dict)
    
    return formatted_memories

def _merge_search_results(self, profile_memories, event_memories):
    """合并Profile和Event搜索结果"""
    # 按相关性分数排序合并
    all_memories = []
    
    # 为Profile记忆添加类型标识
    for memory in profile_memories:
        memory["memory_type"] = "profile_memory"
        all_memories.append(memory)
    
    # Event记忆已经包含类型标识
    all_memories.extend(event_memories)
    
    # 按score降序排列
    all_memories.sort(key=lambda x: x.get("score", 0), reverse=True)
    
    return all_memories
```

#### 5.4 CRUD操作扩展

```python
def get(self, memory_id, memory_type: Optional[str] = None):
    """扩展get方法支持指定记忆类型"""
    if memory_type == MemoryType.EVENT.value and self.event_vector_store:
        memory = self.event_vector_store.get(vector_id=memory_id)
        vector_store = self.event_vector_store
    else:
        memory = self.vector_store.get(vector_id=memory_id)
        vector_store = self.vector_store
    
    if not memory:
        return None
    
    return self._format_memory_item(memory)

def update(self, memory_id, data, memory_type: Optional[str] = None):
    """扩展update方法支持Event记忆"""
    if memory_type == MemoryType.EVENT.value and self.event_vector_store:
        existing_embeddings = {data: self.embedding_model.embed(data, "update")}
        return self._update_event_memory(memory_id, data, existing_embeddings)
    else:
        return super().update(memory_id, data)

def delete(self, memory_id, memory_type: Optional[str] = None):
    """扩展delete方法支持Event记忆"""
    if memory_type == MemoryType.EVENT.value and self.event_vector_store:
        return self._delete_event_memory(memory_id)
    else:
        return super().delete(memory_id)
```

### 6. AsyncMemory支持

对`AsyncMemory`类进行相应的异步实现，主要方法包括：

- `_add_event_to_vector_store()` 的异步版本
- `_search_event_vector_store()` 的异步版本
- `_create_event_memory()` 的异步版本
- `_update_event_memory()` 的异步版本
- `_delete_event_memory()` 的异步版本

### 7. API兼容性

#### 7.1 向后兼容

- 现有API调用保持不变
- 通过配置`enable_event_memory=False`可以完全禁用Event记忆功能
- 现有的记忆类型自动标记为`profile_memory`

#### 7.2 新增API参数

```python
# add方法新增可选参数
def add(self, messages, *, 
        memory_types: Optional[List[str]] = None,  # 指定要处理的记忆类型
        ...):
    """
    memory_types: 可选的记忆类型列表，支持：
    - ["profile_memory"] - 仅处理Profile记忆
    - ["event_memory"] - 仅处理Event记忆  
    - ["profile_memory", "event_memory"] - 处理两种类型（默认）
    - None - 根据配置自动决定
    """

# search方法新增过滤参数
def search(self, query: str, *,
           memory_types: Optional[List[str]] = None,  # 指定搜索的记忆类型
           event_time_range_days: Optional[int] = None,  # Event记忆时间范围
           ...):
```

## 实施计划

### 第一阶段：基础架构
1. 扩展配置系统（MemoryConfig, MemoryType）
2. 实现Event记忆的向量存储初始化
3. 添加Event提取提示词

### 第二阶段：核心功能
1. 实现`_add_event_to_vector_store`方法
2. 实现`_search_event_vector_store`方法
3. 扩展现有add和search方法

### 第三阶段：完善功能
1. 实现Event记忆的CRUD操作
2. 添加AsyncMemory支持
3. 完善错误处理和日志

### 第四阶段：测试和优化
1. 编写单元测试
2. 性能测试和优化
3. 文档更新

## 测试方案

### 单元测试
- Event记忆的添加、搜索、更新、删除
- Profile和Event记忆的隔离性测试
- 时间窗口过滤测试
- 配置开关测试

### 集成测试
- 同时启用Profile和Event记忆的完整流程测试
- 异步和同步版本的一致性测试
- 多用户隔离测试

### 性能测试
- 并行处理性能测试
- 大规模数据存储和搜索性能测试

## 预期效果

1. **增强时序记忆能力**：能够有效处理和检索带时间戳的事件信息
2. **保持高性能**：通过并行处理和复用现有架构，性能影响最小
3. **良好的可扩展性**：为未来添加更多记忆类型奠定基础
4. **完全向后兼容**：现有用户无需修改任何代码

通过这个设计，mem0将能够更好地处理时序性事件记忆，同时保持系统的稳定性和性能。