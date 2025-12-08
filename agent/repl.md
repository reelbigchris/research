Gemini: This is the specific engineering challenge: **How do you safely run dynamic Python code inside a running Python application without crashing it or freezing the interface?**

The "Right Way" involves three specific architectural decisions:

1.  **The Container:** Using a shared `globals` dictionary to mimic "state."
2.  **The Trap:** Using `contextlib` to catch `stdout` (print statements).
3.  **The Thread:** Using a Textual `Worker` to keep the UI alive.

Here is the implementation designed for your air-gapped environment. You can copy this into a file named `execution_engine.py`.

### 1\. The Logic Layer: `ReplEngine`

This class handles the code execution. It knows nothing about the UI. It only cares about running Python and capturing output.

```python
import sys
import io
import traceback
import contextlib

class ReplEngine:
    """
    A persistent Python execution environment.
    Acts like a Jupyter kernel: variables defined in one run
    are available in the next.
    """
    def __init__(self, analysis_context):
        # 1. THE STATE CONTAINER
        # This dictionary holds the 'memory' of the agent.
        # We initialize it with 'ctx' so the agent has immediate access to tools.
        self.repl_globals = {
            "ctx": analysis_context,
            "print": print, # Ensure standard print is available
            "__builtins__": __builtins__ # Standard Python functions (len, int, etc.)
        }

    def execute(self, code_str: str) -> str:
        """
        Runs the code, captures stdout, and handles errors.
        Returns a string containing the output or the error trace.
        """
        # Create a buffer to trap text sent to 'print()'
        output_buffer = io.StringIO()

        # 2. THE TRAP (Redirect Stdout)
        # We redirect stdout to our buffer for the duration of this block.
        with contextlib.redirect_stdout(output_buffer):
            try:
                # 3. THE EXECUTION
                # exec() runs the string as code.
                # We pass 'self.repl_globals' as both global and local scope.
                # This ensures variables like 'x = 10' are stored in that dict.
                exec(code_str, self.repl_globals, self.repl_globals)

            except Exception:
                # If the agent writes bad code, we catch it here.
                # We print the traceback to the buffer so the agent sees the error.
                print(traceback.format_exc())

        # Return whatever was printed (or the error trace)
        return output_buffer.getvalue()
```

-----

### 2\. The Integration Layer: `AgentApp`

This is how you hook the `ReplEngine` into Textual. The key here is the `@work` decorator.

```python
from textual import work
from textual.app import App
from textual.widgets import Log, Input

# Import your context tools and the engine we just wrote
# from analysis_tools import AnalysisContext (Assuming this exists)
# from execution_engine import ReplEngine

class AgentApp(App):

    def on_mount(self):
        # Initialize the Tools
        self.ctx = AnalysisContext()

        # Initialize the Engine with the tools
        self.engine = ReplEngine(self.ctx)

        self.log_widget = self.query_one(Log)

    async def on_input_submitted(self, event: Input.Submitted):
        code = event.value
        event.input.value = "" # Clear the input box

        # Log the User's command
        self.log_widget.write(f">>> {code}")

        # Trigger the background worker
        self.run_agent_code(code)

    # 4. THE THREAD (The Worker)
    # 'thread=True' moves this function to a separate thread.
    # 'exclusive=True' ensures only one code block runs at a time (preventing race conditions).
    @work(thread=True, exclusive=True)
    def run_agent_code(self, code: str):

        # A. Run the code (This is blocking, but it's on a thread, so UI is safe)
        result = self.engine.execute(code)

        # B. Update the UI
        # CRITICAL: You cannot update widgets directly from a worker thread.
        # You must use 'self.call_from_thread' to schedule the update on the main thread.
        self.call_from_thread(self.log_widget.write, result)
```

-----

### Why this is the "Right Way"

#### 1\. The `exec(code, globals, globals)` Trick

Notice in `ReplEngine` I passed `self.repl_globals` twice:
`exec(code_str, self.repl_globals, self.repl_globals)`

If you don't do this, Python treats the code as if it's running inside a class method, and local variables (like `x = 5`) will vanish when `exec` finishes. By passing the same dictionary for both *globals* and *locals*, you force Python to store every variable in that persistent dictionary. This is exactly how Jupyter works.

#### 2\. `redirect_stdout` vs `return`

New users often try to make `exec` return a value. `exec` always returns `None`.
You *could* parse the code to find the last expression (like `2 + 2`) and print it automatically, but that requires complex AST manipulation.
**The Pro Approach:** Just instruct your System Prompt (the instructions you give the LLM): *"You are running in a Python REPL. If you want to see a value, you MUST print() it."* This is robust and requires zero extra code.

#### 3\. Exception Handling as Feedback

In the `try/except` block, notice I am **not** crashing the app. I am capturing `traceback.format_exc()`.
This is vital for an Agent. If the Agent tries to access a database table that doesn't exist, it needs to see the `sqlite3.OperationalError` so it can say, *"Oops, I made a mistake, let me try listing the tables first."* The error is not a failure; it is data.

#### 4\. Thread Safety

Since you are using SQLite, running queries on the main thread (the UI thread) will freeze your application. If the query takes 5 seconds, your app will be unresponsive for 5 seconds. The `@work(thread=True)` decorator solves this entirely by offloading the `engine.execute()` call to a background worker.

Me: Are there any other important architectural details that enable this "right way"?

Gemini:Yes, there are three critical architectural details that often get overlooked but are essential for a smooth "Researcher" experience. Without them, you will find yourself constantly fighting the LLM's formatting or manually updating prompts every time you change a line of code.

Here are the missing pieces of the "Right Way."

### 1\. The "Code Sanitizer" (The Middleman)

**The Problem:** LLMs rarely output pure Python. They output Markdown.

  * *Agent:* "Sure, here is the code to check the symbol:\\n`python\nprint(ctx.fw.get_symbol('main'))\n`"
  * *Exec:* SyntaxError.

**The Architectural Fix:** You need a rigid **Sanitization Layer** between the Textual Input and the `ReplEngine`. This layer extracts the *executable content* from the chat wrapper.

**Add this to your `execution_engine.py`:**

````python
import re

class CodeSanitizer:
    @staticmethod
    def extract_code(llm_response: str) -> str:
        """
        Extracts the code block from Markdown, or returns the raw text
        if no markdown is found.
        """
        # Regex to find content inside ```python ... ``` or just ``` ... ```
        code_block_pattern = r"```(?:python)?\s*(.*?)```"
        match = re.search(code_block_pattern, llm_response, re.DOTALL)

        if match:
            # Return just the code inside the block
            return match.group(1).strip()

        # Fallback: Assume the whole string is code if no markdown tags
        # (Be careful with this, but for a researcher agent it's usually safe)
        return llm_response.strip()
````

### 2\. Dynamic Introspection (Self-Documentation)

**The Problem:** You are going to add methods to `FirmwareContext` constantly. You do not want to manually update the "System Prompt" (the text telling the LLM what tools it has) every time you add a helper function.

**The Architectural Fix:** Make the System Prompt **dynamic**. The Agent should inspect the `ctx` object at runtime to see what tools are available.

**Add this to your `AnalysisContext` class:**

```python
import inspect

class AnalysisContext:
    # ... your existing __init__ and tools ...

    def get_api_docs(self) -> str:
        """
        Architectural Magic: Generates a 'User Manual' for the Agent
        based on the actual code definitions.
        """
        docs = ["## Available Tools (ctx object)"]

        # Iterate over all components (fw, src, etc.)
        for name, component in [('fw', self.fw), ('src', self.src)]:
            docs.append(f"\n### ctx.{name} Tools:")

            # Inspect methods of the component
            for method_name, method in inspect.getmembers(component, predicate=inspect.ismethod):
                if method_name.startswith('_'): continue # Skip private methods

                # Get the signature (params) and docstring
                sig = inspect.signature(method)
                doc = inspect.getdoc(method) or "No description."

                # Format: get_symbol(name) - Finds a function in the DB.
                docs.append(f"- `{method_name}{sig}`: {doc.splitlines()[0]}")

        return "\n".join(docs)
```

**How to use it:**
When you initialize your LLM conversation, you inject this:
`system_prompt = "You are a researcher... Here are your tools:\n" + ctx.get_api_docs()`

Now, whenever you add a new tool to your Python code, the Agent "knows" about it instantly.

### 3\. The "Output Truncator" (Safety Valve)

**The Problem:** The Agent runs `print(ctx.fw.read_bytes(0x0, 1000000))`.

  * **Result:** Python tries to print 1MB of text. Textual tries to render it. Your application hangs. The LLM context window explodes on the next turn.

**The Architectural Fix:** The `ReplEngine` must enforce a **hard limit** on output size before returning it to the UI/LLM.

**Update your `ReplEngine.execute` method:**

```python
    def execute(self, code_str: str) -> str:
        output_buffer = io.StringIO()
        MAX_CHARS = 2000 # Limit to ~500 tokens of output

        with contextlib.redirect_stdout(output_buffer):
            try:
                exec(code_str, self.repl_globals, self.repl_globals)
            except Exception:
                print(traceback.format_exc())

        full_output = output_buffer.getvalue()

        # The Safety Valve
        if len(full_output) > MAX_CHARS:
            return full_output[:MAX_CHARS] + f"\n... [Output Truncated. Total size: {len(full_output)} chars]"

        return full_output or "[No Output. Did you forget to print()?]"
```

### 4\. The Loop Diagram

To visualize how these "Safety" details fit into the main flow, here is the updated interaction loop:

### Summary of the "Right Way" Checklist

If you are taking this into an air-gapped room, verify you have these three logic blocks:

1.  **Sanitizer:** `Regex` to strip markdown. (Ensures `exec` doesn't choke on formatting).
2.  **Introspection:** `inspect.getmembers()` to build the System Prompt. (Ensures the Agent knows its tools).
3.  **Truncation:** `len(output) > MAX` check. (Ensures you don't crash the UI or the LLM context).

With these three guards in place, your Notebook environment becomes robust enough for real work.
