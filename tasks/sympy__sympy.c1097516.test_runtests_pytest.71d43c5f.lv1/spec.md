## Task
**Task Statement: Path Resolution and Test Configuration for SymPy Testing Framework**

Restore the two path-processing helpers used by SymPy's pytest compatibility layer.
`make_absolute_path` resolves paths rooted at the `sympy` source directory and rejects
other roots. `update_args_with_paths` augments an existing pytest argument list from
default test roots, explicit paths, partial directory or test-file selectors, and
optional keyword filters. Missing partial selectors contribute no matches rather than
raising an error.

## Interface Descriptions

### Interface Description 1
Below is **Interface Description 1**

Path: `/testbed/sympy/testing/runtests_pytest.py`
```python
def make_absolute_path(partial_path: str) -> str:
    """
    Convert a partial path to an absolute path within the SymPy directory structure.
    
    This function takes a partial path that begins with 'sympy' and converts it to an
    absolute path by prepending the SymPy root directory. This is necessary for pytest
    arguments to avoid errors that arise from nonexistent or ambiguous paths.
    
    Parameters
    ----------
    partial_path : str
        A partial path string that must begin with 'sympy' as the root directory.
        For example: 'sympy/core', 'sympy/functions/tests', etc.
    
    Returns
    -------
    str
        The absolute path string constructed by joining the SymPy root directory
        with the provided partial path.
    
    Raises
    ------
    ValueError
        If the partial_path does not begin with 'sympy' as the root directory.
        The function validates that partial paths follow the expected convention
        of starting from the sympy directory.
    
    Notes
    -----
    The path is joined to the project root even if the target itself does not exist.
    Merely containing the word ``sympy`` later in the path is not sufficient.
    
    Examples
    --------
    Convert a partial path to absolute:
        make_absolute_path('sympy/core') 
        # Returns: '/path/to/sympy/installation/sympy/core'
    
    Convert a test directory path:
        make_absolute_path('sympy/functions/tests')
        # Returns: '/path/to/sympy/installation/sympy/functions/tests'
    """
    # <your code>

def update_args_with_paths(paths: List[str], keywords: Optional[Tuple[str]], args: List[str]) -> List[str]:
    """
    Appends valid paths and flags to the args `list` passed to `pytest.main`.
    
    This function processes different types of path inputs that users may pass and
    converts them into appropriate arguments for pytest execution. It handles three
    main scenarios for path resolution and optionally filters tests by keywords.
    
    Parameters
    ----------
    paths : List[str]
        A list of path strings. An empty list selects the existing default test roots.
        Existing files or directories are resolved to absolute paths. Other values are
        treated as partial directory or test-file selectors within those roots; test
        filenames may omit the conventional ``test`` prefix and/or ``.py`` suffix.
    keywords : Optional[Tuple[str]]
        Optional tuple of keyword strings used to match test-function declarations
        case-insensitively. If ``None`` or empty, no keyword filtering is applied.
    args : List[str]
        The existing list of arguments that will be passed to ``pytest.main``. It is
        modified in place.
    
    Returns
    -------
    List[str]
        The same ``args`` list with resolved candidates appended. With keywords,
        matching tests are appended as ``filepath::test_function_name`` node IDs;
        otherwise the candidate files or directories are appended.
    
    Notes
    -----
    Partial selectors are searched recursively beneath the available default roots.
    Directory selectors use substring matching and select a matched directory as a
    unit, without continuing the search into that directory's descendants. For a
    test-file selector, an existing ``test`` prefix and ``.py`` suffix are respected;
    a missing prefix permits any ``test*`` prefix, a missing suffix permits any tail
    ending in ``.py``, and omitting both permits both forms of completion around the
    supplied fragment. Keyword filtering then searches only ``test_*.py`` candidates,
    using case-insensitive substring matches in function declarations, and emits the
    declared function name in each pytest node ID. Unmatched partial selectors append
    nothing.
    """
    # <your code>
```

Remember, **the interface template above is extremely important**. You must generate callable interfaces strictly according to the specified requirements, as this will directly determine whether you can pass our tests. If your implementation has incorrect naming or improper input/output formats, it may directly result in a 0% pass rate for this case.
