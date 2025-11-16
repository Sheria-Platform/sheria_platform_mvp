import os
import sys
from typing import List, Optional
from dotenv import load_dotenv

# CORRECTED IMPORTS for LangChain 1.0+ / LangGraph
from langchain_core.tools import tool, Tool
from langchain_ollama import ChatOllama
from langgraph.prebuilt import create_react_agent
import datetime

load_dotenv()

# ==================== TOOLS ====================

@tool
def get_current_datetime(format: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    Returns the current date and time, formatted according to the provided Python strftime format string.
    Use this tool whenever the user asks for the current date, time, or both.
    Example format strings: '%Y-%m-%d' for date, '%H:%M:%S' for time, '%I:%M %p' for 12-hour format.
    If no format is specified, defaults to '%Y-%m-%d %H:%M:%S'.
    """
    try:
        return datetime.datetime.now().strftime(format)
    except Exception as e:
        return f"Error formatting date/time: {e}. Use valid Python strftime format codes."


@tool
def calculate(expression: str) -> str:
    """
    Safely evaluates a mathematical expression and returns the result.
    Supports basic arithmetic operations: +, -, *, /, **, (), and common math functions.
    Example: "2 + 2", "10 * 5", "sqrt(16)", "pow(2, 3)"
    """
    try:
        # Safer evaluation with limited scope
        import math
        allowed_names = {
            k: v for k, v in math.__dict__.items() 
            if not k.startswith("__")
        }
        allowed_names.update({"abs": abs, "round": round})
        
        result = eval(expression, {"__builtins__": {}}, allowed_names)
        return str(result)
    except Exception as e:
        return f"Error evaluating expression: {e}"


# Define available tools
TOOLS = [get_current_datetime, calculate]


# ==================== CONFIGURATION ====================

class AgentConfig:
    """Configuration for the agent system."""
    DEFAULT_MODEL = "qwen3:30b-a3b"
    FALLBACK_MODELS = ["llama3.2:3b", "mistral:7b"]
    DEFAULT_TEMPERATURE = 0.0
    DEFAULT_CONTEXT_WINDOW = 8192
    MAX_ITERATIONS = 15  # Prevent infinite loops
    MAX_EXECUTION_TIME = 60  # seconds


# ==================== AGENT SETUP ====================

def get_agent_llm(
    model_name: str = AgentConfig.DEFAULT_MODEL,
    temperature: float = AgentConfig.DEFAULT_TEMPERATURE,
    num_ctx: int = AgentConfig.DEFAULT_CONTEXT_WINDOW
) -> ChatOllama:
    """
    Initializes the ChatOllama model for the agent with enhanced configuration.
    
    Args:
        model_name: The Ollama model to use
        temperature: Controls randomness (0 = deterministic, 1 = creative)
        num_ctx: Context window size in tokens
    
    Returns:
        Configured ChatOllama instance
    """
    try:
        llm = ChatOllama(
            model=model_name,
            temperature=temperature,
            num_ctx=num_ctx,
            # Additional optimizations
            num_predict=512,  # Limit response length for faster responses
            repeat_penalty=1.1,  # Reduce repetition
        )
        
        # Test the model with a simple query
        print(f"Testing model '{model_name}'...")
        llm.invoke("Hello")
        print(f"✓ Model '{model_name}' initialized successfully")
        return llm
        
    except Exception as e:
        print(f"✗ Error initializing model '{model_name}': {e}")
        print("\nTroubleshooting:")
        print("1. Ensure Ollama is running: ollama serve")
        print(f"2. Pull the model: ollama pull {model_name}")
        print(f"3. Try fallback models: {', '.join(AgentConfig.FALLBACK_MODELS)}")
        raise


def create_agent_executor(
    llm: ChatOllama,
    tools: List[Tool],
    system_message: str = None
):
    """
    Creates the agent using LangGraph's create_react_agent.
    
    Args:
        llm: The language model instance
        tools: List of available tools
        system_message: Optional system message for the agent
    
    Returns:
        Configured agent executor (CompiledGraph)
    """
    if system_message is None:
        tool_names = ", ".join([tool.name for tool in tools])
        system_message = f"""You are a helpful AI assistant with access to tools.

Your capabilities:
- Use the available tools to answer questions that require real-time data or calculations
- Think step-by-step about which tools to use and when
- If a tool returns an error, try a different approach or inform the user
- Provide clear, concise answers based on tool results

Available tools: {tool_names}

Guidelines:
1. ALWAYS use the appropriate tool when the question requires it
2. For date/time questions, use get_current_datetime
3. For calculations, use calculate
4. If no tool is needed, answer directly
5. Be precise and accurate in your responses"""

    # Use create_react_agent from langgraph.prebuilt
    agent_executor = create_react_agent(
        llm,
        tools
        # state_modifier=system_message
    )
    print("✓ Agent executor created")
    return agent_executor


# ==================== EXECUTION ====================

def run_agent(executor, user_input: str) -> dict:
    """
    Runs the agent executor with the given input and enhanced error handling.
    
    Args:
        executor: The agent executor (CompiledGraph)
        user_input: User's question or command
    
    Returns:
        Response dictionary with 'output' and optional 'error' keys
    """
    print("\n" + "=" * 80)
    print(f"Input: {user_input}")
    print("-" * 80)
    
    try:
        # LangGraph agents return state updates
        # We stream through the graph and collect the final state
        final_state = None
        for state in executor.stream(
            {"messages": [("user", user_input)]},
            stream_mode="values"
        ):
            final_state = state
        
        # Extract the final assistant message from the state
        if final_state and "messages" in final_state:
            messages = final_state["messages"]
            # Get the last message (should be from assistant)
            for msg in reversed(messages):
                if hasattr(msg, 'content') and msg.type == "ai":
                    final_message = msg.content
                    break
            else:
                # Fallback: get the last message content
                final_message = messages[-1].content if messages else "No response"
        else:
            final_message = "No response generated"
        
        print("\n✓ Agent Response:")
        print(final_message)
        print("=" * 80)
        return {"output": final_message}
        
    except Exception as e:
        error_msg = f"Error running agent: {e}"
        print(f"\n✗ {error_msg}")
        print("=" * 80)
        return {"output": error_msg, "error": str(e)}


def interactive_mode(executor):
    """
    Runs an interactive command-line interface for the agent.
    """
    print("\n" + "=" * 80)
    print("Interactive Agent Mode")
    print("=" * 80)
    print("Commands:")
    print("  - Type your question to ask the agent")
    print("  - 'help' - Show available tools")
    print("  - 'quit', 'exit', or 'q' - Exit the program")
    print("-" * 80)
    
    while True:
        try:
            user_input = input("\n👤 You: ").strip()
            
            if not user_input:
                continue
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("\n👋 Goodbye!")
                break
            
            if user_input.lower() == 'help':
                print("\n📋 Available Tools:")
                for tool in TOOLS:
                    print(f"\n• {tool.name}")
                    print(f"  {tool.description}")
                continue
            
            run_agent(executor, user_input)
            
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"\n✗ Unexpected error: {e}")


def setup_agent_system(
    model_name: str = AgentConfig.DEFAULT_MODEL,
    verbose: bool = True
) -> Optional[any]:
    """
    Sets up the complete agent system.
    
    Args:
        model_name: Ollama model to use
        verbose: Whether to print verbose output
    
    Returns:
        Configured agent executor or None if setup fails
    """
    print("=" * 80)
    print("Agent System Setup")
    print("=" * 80)
    
    try:
        # 1. Initialize LLM
        print("\n🤖 Initializing language model...")
        llm = get_agent_llm(model_name=model_name)
        
        # 2. Create agent executor
        print("\n⚙️  Creating agent executor...")
        executor = create_agent_executor(llm, TOOLS)
        
        print("\n✅ Agent system ready!")
        print("=" * 80)
        return executor
        
    except Exception as e:
        print(f"\n❌ Failed to setup agent system: {e}")
        print("=" * 80)
        return None


# ==================== MAIN ====================

def main():
    """Main entry point for the agent system."""
    # Parse command line arguments
    args = sys.argv[1:]
    
    model_name = AgentConfig.DEFAULT_MODEL
    verbose = True
    direct_question = None
    
    # Parse arguments
    i = 0
    while i < len(args):
        if args[i] == "--model" and i + 1 < len(args):
            model_name = args[i + 1]
            i += 2
        elif args[i] == "--question" and i + 1 < len(args):
            direct_question = args[i + 1]
            i += 2
        elif args[i] == "--quiet":
            verbose = True
            i += 1
        else:
            i += 1
    
    # Setup agent system
    executor = setup_agent_system(
        model_name=model_name,
        verbose=verbose
    )
    
    if executor is None:
        print("\n❌ Failed to setup agent system. Exiting.")
        sys.exit(1)
    
    # Run in appropriate mode
    if direct_question:
        run_agent(executor, direct_question)
    else:
        interactive_mode(executor)


if __name__ == "__main__":
    main()