import os

import httpx
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langgraph.constants import START
from langgraph.graph import StateGraph, MessagesState

from mem0 import Memory

load_dotenv()

# Initialize LangChain and Mem0
llm = ChatOpenAI(model="moonshotai/kimi-k2", temperature=0, streaming=True, base_url="https://openrouter.ai/api/v1/",
                 api_key=os.environ['OPENROUTER_API_KEY'], http_client=httpx.Client(verify=False),
                 http_async_client=httpx.AsyncClient(verify=False), )

openai_embeddings = OpenAIEmbeddings(api_key=os.environ["DASHSCOPE_API_KEY"],
                                     base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                                     model="text-embedding-v4", async_client=httpx.AsyncClient(verify=False),
                                     check_embedding_ctx_length=False)
config = {
    "llm": {
        "provider": "langchain",
        "config": {
            "model": llm
        }
    },
    "vector_store": {
        "provider": "chroma",
        "config": {
            "collection_name": "test",
            "path": "db",
        }
    },
    "embedder": {
        "provider": "langchain",
        "config": {
            "model": openai_embeddings
        }
    }
}
mem0 = Memory.from_config(config)


class State(MessagesState):
    mem0_user_id: str


graph = StateGraph(State)


def chatbot(state: State):
    messages = state["messages"]
    user_id = state["mem0_user_id"]

    # Retrieve relevant memories
    memories = mem0.search(messages[-1].content, user_id=user_id)

    context = "Relevant information from previous conversations:\n"
    for memory in memories["results"]:
        context += f"- {memory['memory']}\n"

    system_message = SystemMessage(content=f"""You are a helpful customer support assistant. Use the provided context to personalize your responses and remember user preferences and past interactions.
{context}""")

    full_messages = [system_message] + messages
    response = llm.invoke(full_messages)

    # Store the interaction in Mem0
    mem0.add(f"User: {messages[-1].content}\nAssistant: {response.content}", user_id=user_id)
    return {"messages": [response]}


graph.add_node("chatbot", chatbot)
graph.add_edge(START, "chatbot")
graph.add_edge("chatbot", "chatbot")

compiled_graph = graph.compile()


def run_conversation(user_input: str, mem0_user_id: str):
    config = {"configurable": {"thread_id": mem0_user_id}}
    state = {"messages": [HumanMessage(content=user_input)], "mem0_user_id": mem0_user_id}

    for event in compiled_graph.stream(state, config):
        for value in event.values():
            if value.get("messages"):
                print("Customer Support:", value["messages"][-1].content)
                return


if __name__ == "__main__":
    print("Welcome to Customer Support! How can I assist you today?")
    mem0_user_id = "customer_123"  # You can generate or retrieve this based on your user management system
    while True:
        user_input = input("You: ")
        if user_input.lower() in ['quit', 'exit', 'bye']:
            print("Customer Support: Thank you for contacting us. Have a great day!")
            break
        run_conversation(user_input, mem0_user_id)
