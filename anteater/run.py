import token
import tokenize
from enum import Enum, auto
from typing import Callable, Iterator
import os
import openai
import subprocess


def make_readline(s: str):
    lines = s.split("\n")
    for line in lines:
        if line.strip():
            yield line


def detect_prompt(src: str) -> tuple[str, list[str]]:

    # State machine:
    #
    #         start -> start         (sees comment; adds comment)
    #         start -> def/class     (def/class)
    #         start -> start         (all else)
    #     def/class -> colon         (colon)
    #     def/class -> def/class     (comment; adds comment)
    #     def/class -> def/class     (def/class; throws away content)
    #     def/class -> def/class     (all else)
    #         colon -> colon         (comment; adds comment)
    #         colon -> ind def/class (indent)
    #         colon -> after_colon   (docstring; adds comment)
    #         colon -> after_colon   (all else)
    #   after_colon -> after_colon   (docstring/comment; adds comment)
    #   after_colon -> after_colon   (whitespace)
    #   after_colon -> end           (all else)
    # ind def/class -> ind def/class (comment; adds comment)
    # ind def/class -> ind def/class (docstring; adds comment)
    # ind def/class -> def/class     (def/class; partially throws away content)
    # ind def/class -> end           (dedent)
    # ind def/class -> body          (all else)
    #          body -> end           (dedent)
    #          body -> body          (all else)
    #           end -> end           (whitespace)
    #           end -> start         (non-whitespace code; throws away content)

    class State(Enum):
        START = auto()
        DEF_CLASS = auto()
        COLON = auto()
        AFTER_COLON = auto()
        IND_DEF_CLASS = auto()
        BODY = auto()
        END = auto()

    state = State.START
    sig: list[tokenize.TokenInfo] = []
    content: list[str] = []
    prev_tok = None
    def_class_idx = -1
    body_nesting = 0
    decl_nesting = 0

    for tok in tokenize.generate_tokens(make_readline(src).__next__):

        to_continue = True
        while to_continue:
            to_continue = False

            print(state, len(sig), len(content), tok)

            if state == State.START:
                if tok.type == token.NAME and (
                    tok.string == "def" or tok.string == "class"
                ):
                    state = State.DEF_CLASS
                    sig.append(tok)
                    def_class_idx = len(content)
                elif tok.type == token.COMMENT:
                    content.append(tok.string)

            elif state == State.DEF_CLASS:
                if decl_nesting == 0 and tok.type == token.OP and tok.string == ":":
                    state = State.COLON
                elif tok.type == token.COMMENT:
                    content.append(tok.string)
                else:
                    if tok.type == token.OP and (
                        tok.string == "{" or tok.string == "[" or tok.string == "("
                    ):
                        decl_nesting += 1
                    elif tok.type == token.OP and (
                        tok.string == "}" or tok.string == "]" or tok.string == ")"
                    ):
                        decl_nesting -= 1
                    elif tok.type == token.NAME and (
                        tok.string == "def" or tok.string == "class"
                    ):
                        content.clear()

                    sig.append(tok)

            elif state == State.COLON:
                if tok.type == token.INDENT:
                    state = State.IND_DEF_CLASS
                    body_nesting = 0
                elif tok.type == token.COMMENT:
                    content.append(tok.string)
                elif tok.type == token.STRING and (
                    tok.string.startswith('"""') or tok.string.startswith("'''")
                ):
                    content.append(tok.string[3:-3])
                    def_class_idx = len(content)
                    state = State.AFTER_COLON
                elif prev_tok is not None and tok.start[0] > prev_tok.end[0]:
                    state = State.END
                elif tok.type == token.NL or tok.type == token.NEWLINE:
                    pass
                else:
                    state = State.AFTER_COLON

            elif state == State.AFTER_COLON:
                if tok.type == token.COMMENT:
                    content.append(tok.string)
                elif tok.type == token.STRING and (
                    tok.string.startswith('"""') or tok.string.startswith("'''")
                ):
                    content.append(tok.string[3:-3])
                elif tok.type == token.NL or tok.type == token.NEWLINE:
                    pass
                else:
                    state = State.END

            elif state == State.IND_DEF_CLASS:
                if body_nesting == 0 and tok.type == token.DEDENT:
                    state = State.END
                elif tok.type == token.DEDENT:
                    body_nesting -= 1
                elif tok.type == token.INDENT:
                    body_nesting += 1
                elif tok.type == token.COMMENT:
                    content.append(tok.string)
                elif tok.type == token.STRING and (
                    tok.string.startswith('"""') or tok.string.startswith("'''")
                ):
                    content.append(tok.string[3:-3])
                    def_class_idx = len(content)
                elif tok.type == token.NAME and (
                    tok.string == "def" or tok.string == "class"
                ):
                    content = content[def_class_idx:]
                    sig = [tok]
                    def_class_idx = len(content)
                    state = State.DEF_CLASS
                elif tok.type == token.NL or tok.type == token.NEWLINE:
                    pass
                else:
                    state = State.BODY

            elif state == State.BODY:
                if body_nesting == 0 and tok.type == token.DEDENT:
                    state = State.END
                elif tok.type == token.DEDENT:
                    body_nesting -= 1
                elif tok.type == token.INDENT:
                    body_nesting += 1
                elif tok.type == token.COMMENT:
                    content.append(tok.string)
                elif tok.type == token.NAME and (
                    tok.string == "def" or tok.string == "class"
                ):
                    content = content[def_class_idx:]
                    sig = []
                    def_class_idx = 0
                    state = State.START
                    to_continue = True
                elif tok.type == token.NEWLINE or tok.type == token.NL:
                    pass
                else:
                    def_class_idx = len(content)

            elif state == State.END:
                if (
                    tok.type == token.NEWLINE
                    or tok.type == token.NL
                    or tok.type == token.ENDMARKER
                    or tok.type == token.INDENT
                    or tok.type == token.DEDENT
                ):
                    pass
                else:
                    content = content[def_class_idx:]
                    sig = []
                    def_class_idx = 0
                    state = State.START
                    to_continue = True

        prev_tok = tok

    untok = ""
    if sig:
        # Prepend NL tokens to align to the correct line.
        out_sig = []
        first_line = sig[0].start[0]
        for i in range(1, first_line):
            out_sig.append(
                tokenize.TokenInfo(token.NL, "", start=(i, 0), end=(i, 0), line="")
            )
        out_sig += sig
        untok = tokenize.untokenize(out_sig).strip()
    return untok, content


def gpt_complete(prompt, **kwargs) -> str:
    if "model" not in kwargs:
        kwargs["model"] = "text-davinci-003"
    if "prompt" not in kwargs:
        kwargs["prompt"] = prompt
    if "temperature" not in kwargs:
        kwargs["temperature"] = 0.7
    if "max_tokens" not in kwargs:
        kwargs["max_tokens"] = 40
    if "top_p" not in kwargs:
        kwargs["top_p"] = 1
    if "frequency_penalty" not in kwargs:
        kwargs["frequency_penalty"] = 0
    if "presence_penalty" not in kwargs:
        kwargs["presence_penalty"] = 0

    res = openai.Completion.create(**kwargs)
    answer = res.choices[0].text
    return answer


def yes_or_no(prompt, **kwargs) -> bool | None:
    if "temperature" not in kwargs:
        kwargs["temperature"] = 0
    print(f"> {prompt}")
    answer = gpt_complete(prompt, **kwargs).strip()
    print(f"< {answer}")
    if answer.lower().startswith("yes"):
        return True
    elif answer.lower().startswith("no"):
        return False
    else:
        return None


def codex_complete(prompt: str, **kwargs) -> str:
    if "model" not in kwargs:
        kwargs["model"] = "code-davinci-002"
    if "temperature" not in kwargs:
        kwargs["temperature"] = 0.1
    if "max_tokens" not in kwargs:
        kwargs["max_tokens"] = 100
    return gpt_complete(prompt, **kwargs)


def run(code: str, force: int | None = None):
    sig, docs = detect_prompt(code)

    if not sig:
        print("Not requesting any function. Escaping.")
        return

    print(f"Requesting function {sig}, with prompt {docs}")

    is_creating_html = yes_or_no(
        f"Yes or no: When I ask you to write a function `{sig}`, am I asking for a function that creates HTML code?"
    )
    if is_creating_html:
        # Check if we specified the library to use.
        specified_lib = any("jinja" in d.lower() for d in docs)
        if not specified_lib:
            print(
                "Please specify an HTML template library to use! Examples include Jinja."
            )
            print(
                "Make your prompt as detailed as possible. Make sure to import the library."
            )
            if force and force > 0:
                print("Okay, overridden")
            else:
                return

    is_encrypting = yes_or_no(
        f"Yes or no: When I ask you to write a function `{sig}`, am I asking for a function that encrypts data?"
    )
    if is_encrypting:
        # Check if we specified the library to use.
        specified_lib = any("aes" in d.lower() for d in docs)
        if not specified_lib:
            print("Please specify a cipher to use! Examples include AES-GCM.")
            print(
                "Make your prompt as detailed as possible. Make sure to import any cryptography library as needed."
            )
            if force and force > 1:
                print("Okay, overridden")
            else:
                return

    codex_out = codex_complete(code, stop=["def"])
    with open("test-output.py", "w") as f:
        f.write(code)
        f.write(codex_out)
    subprocess.run(["semgrep", "-c", "python-xss.yaml", "--autofix", "test-output.py"])
    with open("test-output.py") as f:
        print(f.read())


# Yes or no: In a function `def render_page(raw_html: str, title: str)`, is one of the arguments HTML code?
# Yes or no: When I ask you to write a function `def render_page(raw_html: str)`, am I asking you to create HTML code?

# Early stage:
#  XSS:
#   GPT-check if producing HTML. Regex-check if jinja, flask, etc., are part of the prompt.
#  Crypto:
#   Check if prompt asks for encryption. For best result, specify the exact algorithm

run(
    '''
def render_html(title: str, content: str) -> str:
  """
  Returns an HTML page with the given information.
  """
''',
    force=1,
)
