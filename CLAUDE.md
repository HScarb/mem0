# CLAUDE.md

此文件为 Claude Code (claude.ai/code) 在此代码库中工作时提供指导。

## 开发命令

### 核心开发
- `make install` - 创建 hatch 环境
- `make install_all` - 安装所有可选依赖
- `make test` - 使用 hatch 运行 pytest 测试套件
- `make test-py-3.X` - 运行特定 Python 版本的测试 (3.9, 3.10, 3.11, 3.12)
- `make format` - 使用 ruff 格式化代码
- `make sort` - 使用 isort 排序导入
- `make lint` - 使用 ruff 检查代码
- `make build` - 使用 hatch 构建包
- `make clean` - 删除 dist 目录

### Hatch 命令（推荐）
- `hatch run test` - 运行测试
- `hatch run format` - 格式化代码
- `hatch run lint` - 检查代码
- `hatch run format-check` - 检查格式

### 特定测试命令
- `pytest tests/` - 直接运行所有测试
- `pytest tests/test_file.py` - 运行特定测试文件
- `pytest tests/ -v` - 运行详细输出的测试

## 架构概述

### 核心组件

**记忆系统 (`mem0/memory/`)**
- `main.py` - 主要的 `Memory` 和 `AsyncMemory` 类
- `base.py` - 记忆基础接口
- `storage.py` - SQLite 存储管理器
- `graph_memory.py` - 基于图的记忆实现
- `kuzu_memory.py` - Kuzu 图数据库集成
- `memgraph_memory.py` - Memgraph 数据库集成

**客户端系统 (`mem0/client/`)**
- `main.py` - 用于 API 交互的 `MemoryClient` 和 `AsyncMemoryClient`
- `project.py` - 项目管理功能
- `utils.py` - 客户端工具和错误处理

**LLM 支持 (`mem0/llms/`)**
- 支持多个提供商：OpenAI、Anthropic、AWS Bedrock、Groq、Together、Ollama 等
- `base.py` - LLM 基础接口
- 支持结构化输出的特定提供商实现

**向量存储 (`mem0/vector_stores/`)**
- 支持：Qdrant、Pinecone、Chroma、Weaviate、Elasticsearch、Redis 等
- `base.py` - 向量存储基础接口
- 特定提供商实现

**嵌入模型 (`mem0/embeddings/`)**
- 支持：OpenAI、HuggingFace、Ollama、Azure OpenAI 等
- `base.py` - 嵌入基础接口

**图存储 (`mem0/graphs/`)**
- 支持 Neptune、Neo4j 的基于图的记忆存储
- 增强关系跟踪和检索

### 配置系统 (`mem0/configs/`)
- `base.py` - 核心配置类和记忆项模式
- `enums.py` - 记忆类型和配置枚举
- `prompts.py` - 记忆操作的系统提示
- 特定提供商配置类

### 关键特性
- **多级记忆**：用户、会话和代理记忆上下文
- **混合架构**：结合向量相似性和图关系
- **提供商灵活性**：可插拔的 LLM、嵌入和向量存储
- **记忆类型**：支持不同记忆类别（情景、语义、程序性）
- **异步支持**：整个代码库完全支持 async/await

### 记忆操作
- `add()` - 从对话中提取和存储记忆
- `search()` - 使用相似性和图搜索检索相关记忆
- `get()` - 按 ID 获取特定记忆
- `delete()` - 删除记忆
- `update()` - 修改现有记忆
- `history()` - 获取记忆操作历史

### 使用模式
- **自托管**：直接使用带本地配置的 `Memory()` 类
- **托管平台**：使用带 API 密钥的 `MemoryClient()` 管理服务
- **异步操作**：在异步上下文中使用 `AsyncMemory()` 和 `AsyncMemoryClient()`

## mem0/ 目录详细结构

### 1. 记忆核心模块 (`mem0/memory/`)

**主要文件：**
- **`main.py`** - 记忆系统的核心实现
  - `Memory` 类：同步记忆操作的主入口点
  - `AsyncMemory` 类：异步记忆操作
  - `_build_filters_and_metadata()` - 构建过滤器和元数据的工具函数
  - 支持多种会话标识符（user_id、agent_id、run_id）
  - 内置遥测和错误处理

- **`base.py`** - `MemoryBase` 抽象基类
  - 定义记忆系统的标准接口
  - 所有记忆实现必须继承此类

- **`storage.py`** - `SQLiteManager` 
  - 本地 SQLite 数据库管理
  - 记忆历史持久化
  - 支持事务和并发访问

- **`graph_memory.py`** - 图记忆实现
  - 基于图数据库的记忆存储
  - 支持复杂关系建模
  - 增强的检索能力

- **`setup.py`** - 环境配置和初始化
- **`telemetry.py`** - 遥测数据收集
- **`utils.py`** - 工具函数集合

### 2. 配置管理 (`mem0/configs/`)

**核心配置：**
- **`base.py`** - 基础配置类
  - `MemoryConfig` - 主配置类
  - `MemoryItem` - 记忆项数据模型
  - `AzureConfig` - Azure 服务配置

- **`enums.py`** - 枚举定义
  - `MemoryType` - 记忆类型枚举
  - 各种配置选项枚举

- **`prompts.py`** - 系统提示模板
  - 事实提取提示
  - 记忆更新提示
  - 程序性记忆提示

**提供商配置子目录：**
- **`llms/`** - LLM 提供商配置
  - `base.py` - LLM 基础配置类
  - `openai.py` - OpenAI 配置
  - `anthropic.py` - Anthropic 配置
  - `aws_bedrock.py` - AWS Bedrock 配置
  - `azure.py` - Azure OpenAI 配置
  - 其他提供商配置文件

- **`vector_stores/`** - 向量存储配置
  - 支持 20+ 种向量存储解决方案
  - 每个提供商的特定配置参数

- **`embeddings/`** - 嵌入模型配置
  - `base.py` - 嵌入基础配置

### 3. LLM 集成 (`mem0/llms/`)

**架构设计：**
- **`base.py`** - `LLMBase` 抽象类
  - 统一 LLM 接口
  - 配置验证
  - 推理模型检测

**支持的提供商：**
- **OpenAI 系列**：`openai.py`, `openai_structured.py`
- **云服务**：`azure_openai.py`, `aws_bedrock.py`, `vertexai.py`
- **开源模型**：`ollama.py`, `vllm.py`, `lmstudio.py`
- **商业服务**：`anthropic.py`, `groq.py`, `together.py`
- **其他**：`gemini.py`, `deepseek.py`, `xai.py`, `sarvam.py`

**功能特点：**
- 结构化输出支持
- 流式响应
- 错误重试机制
- 令牌使用跟踪

### 4. 向量存储 (`mem0/vector_stores/`)

**基础架构：**
- **`base.py`** - `VectorStoreBase` 抽象类
- **`configs.py`** - 向量存储配置定义

**支持的存储后端：**
- **云服务**：`pinecone.py`, `weaviate.py`, `qdrant.py`
- **搜索引擎**：`elasticsearch.py`, `opensearch.py`
- **数据库**：`redis.py`, `supabase.py`, `s3_vectors.py`
- **本地存储**：`chroma.py`, `faiss.py`
- **专业方案**：`milvus.py`, `vertex_ai_vector_search.py`

### 5. 嵌入模型 (`mem0/embeddings/`)

**支持的嵌入提供商：**
- **`openai.py`** - OpenAI 文本嵌入
- **`azure_openai.py`** - Azure OpenAI 嵌入
- **`huggingface.py`** - HuggingFace 模型
- **`ollama.py`** - 本地 Ollama 模型
- **`vertexai.py`** - Google Vertex AI
- **`together.py`** - Together AI
- **`langchain.py`** - LangChain 集成
- **`mock.py`** - 测试用模拟嵌入

### 6. 图存储 (`mem0/graphs/`)

**图数据库支持：**
- **`neptune/`** - AWS Neptune 集成
  - `main.py` - Neptune 图存储实现
  - `base.py` - Neptune 基础类
- **`configs.py`** - 图存储配置
- **`tools.py`** - 图操作工具
- **`utils.py`** - 图相关工具函数

### 7. 客户端接口 (`mem0/client/`)

**API 客户端：**
- **`main.py`** - HTTP 客户端实现
  - `MemoryClient` - 同步客户端
  - `AsyncMemoryClient` - 异步客户端
  - 支持完整的 CRUD 操作
  - 内置错误处理和重试

- **`project.py`** - 项目管理
  - `Project` 和 `AsyncProject` 类
  - 项目级别的记忆操作

- **`utils.py`** - 客户端工具
  - API 错误处理装饰器
  - 响应解析工具

### 8. 工具和代理 (`mem0/proxy/`)

**代理功能：**
- **`main.py`** - 代理服务实现
- 支持记忆代理和转发

### 9. 工厂模式 (`mem0/utils/`)

**组件工厂：**
- 自动化组件实例化
- 支持配置驱动的组件选择
- `EmbedderFactory`, `LlmFactory`, `VectorStoreFactory`, `GraphStoreFactory`

## 项目结构
- `/mem0/` - 核心记忆系统和组件
- `/tests/` - 测试套件
- `/examples/` - 使用示例和演示
- `/docs/` - 文档（Mintlify）
- `/embedchain/` - 旧版 EmbedChain 兼容层
- `/server/` - 服务器实现
- `/openmemory/` - OpenMemory 评估框架
- `/evaluation/` - 记忆评估和基准测试