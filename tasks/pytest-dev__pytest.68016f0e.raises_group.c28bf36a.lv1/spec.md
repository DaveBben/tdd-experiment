## Task
**Task Statement: Pytest Exception-Matching Helpers**

Restore the missing helpers used by pytest's existing exception-matching and assertion-diff
flow. This includes unescaping fully escaped regular-expression text for diagnostics and the
supporting logic used by `RaisesGroup` to pair expected and actual exceptions and report failed
matches. Preserve the existing public `RaisesExc`/`RaisesGroup` behavior, including nested groups,
`flatten_subgroups`, `allow_unwrapped`, regex/check predicates, and context-manager or direct
matching usage; this task does not require redesigning the exception framework.

## Interface Descriptions

### Interface Description 1
Below is **Interface Description 1**

Path: `/testbed/src/_pytest/raises.py`
```python
def unescape(s: str) -> str:
    """
    Unescape a regular expression string by removing backslash escapes from regex metacharacters.
    
    This function removes backslash escapes from common regex metacharacters and whitespace
    characters, effectively converting an escaped regex pattern back to its literal form.
    
    Args:
        s (str): The escaped regular expression string to unescape.
    
    Returns:
        str: The unescaped string with backslash escapes removed from metacharacters.
    
    Note:
        This function specifically unescapes the following characters when they are
        preceded by a backslash: {}()+-.*?^$[]\\s (curly braces, parentheses, plus,
        minus, dot, asterisk, question mark, caret, dollar sign, square brackets,
        whitespace, and backslash itself).
    
        This is used internally by pytest's exception matching logic to convert
        fully escaped regex patterns back to their literal string representation
        for better error reporting and diffs.
    
    """
    # <your code>
```

Remember, **the interface template above is extremely important**. You must generate callable interfaces strictly according to the specified requirements, as this will directly determine whether you can pass our tests. If your implementation has incorrect naming or improper input/output formats, it may directly result in a 0% pass rate for this case.
