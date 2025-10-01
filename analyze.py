from common.api import ExtensionAPI
from common.llm import call_llm
from common.utils import add_line_numbers, parse_json
from common.file_type import get_file_type


def get_system_prompt() -> str:
    return """
You are an expert code analyst specializing in static code analysis. Your goal is to find syntax errors in code. Carefully analyze the code (with line numbers) and identify the syntax errors.

1. Only identify syntax errors. Do not identify logic errors.

2. Output only in JSON format:
* A list of JSON object. One object per systax error.
* Each object should be like `{'error': 'description of the error', 'line_no': 'line number with the error', 'contents': 'contents of that line'}

3. Do not make up facts or hallucinate.
""".strip()


def get_prompt(code: str, file_type: str) -> str:
    return f"""
# {file_type.title()} code (with line numbers)

```{file_type}
{add_line_numbers(code)}
```
""".strip()


def extension(api: ExtensionAPI):
    current_file_content = api.current_file.get_content()
    current_file_type = get_file_type(api.current_file.path)

    prompt = get_prompt(current_file_content, current_file_type)

    messages = [
        {"role": "system", "content": get_system_prompt()},
        {'role': 'user', 'content': prompt}
    ]

    response = call_llm(api,
                        'v3',
                        messages,
                        push_to_chat=False,
                        max_tokens=1024,
                        temperature=0.8,
                        top_p=0.8,
                        )

    api.log(f"LLM response:\n {response}")

    errors = parse_json(api, response)

    res = []
    for error in errors:
        res.append(dict(line_number=error["line_no"], description=error["error"]))

    api.send_diagnostics(res)
