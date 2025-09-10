import os

import httpx
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from qdrant_client import QdrantClient

from mem0 import Memory

load_dotenv()

chat_openai = ChatOpenAI(model="qwen3-30b-a3b-instruct-2507",
                   api_key=os.environ["DASHSCOPE_API_KEY"],
                   base_url=os.environ["DASHSCOPE_BASE_URL"],
                   temperature=0.0, streaming=True,
                   http_client=httpx.Client(verify=False),
                   async_client=httpx.AsyncClient(verify=False),
                   )

embeddings = OpenAIEmbeddings(api_key=os.environ["DASHSCOPE_API_KEY"],
                              base_url=os.environ["DASHSCOPE_BASE_URL"],
                              model="text-embedding-v4",
                              async_client=httpx.AsyncClient(verify=False),
                              check_embedding_ctx_length=False)

client = QdrantClient(host="localhost", port=6333, verify=False, prefer_grpc=True)

config = {
    "llm": {
        "provider": "langchain",
        "config": {
            "model": chat_openai
        }
    },
    "vector_store": {
        "provider": "qdrant",
        "config": {
            "collection_name": "mem0-locomo",
            # "client": client,
            "embedding_model_dims": 1024,
            "host": "localhost",
            "port": 6333,
            "verify": False,
            "prefer_grpc": True,
            # "path": "env:CHROMADB_PATH",
        }
    },
    "embedder": {
        "provider": "langchain",
        "config": {
            "model": embeddings
        }
    },
}

mem0_client = Memory.from_config(config_dict=config)
