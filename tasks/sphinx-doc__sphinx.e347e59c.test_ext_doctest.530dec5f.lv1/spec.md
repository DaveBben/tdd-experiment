## Task
**Task Statement: Restore the Doctest Version Predicate**

Restore only `is_allowed_version(spec, version)`. It returns whether `version` belongs to
the supplied PEP 440 specifier set, including compound constraints, exclusions, compatible
release operators and PEP 440 pre/post/dev-version semantics. Invalid specifiers and invalid
versions propagate the corresponding packaging exceptions. Directive execution and the
rest of the doctest extension are outside this interface.

## Interface Descriptions

### Interface Description 1
Below is **Interface Description 1**

Path: `/testbed/sphinx/ext/doctest.py`
```python
def is_allowed_version(spec: str, version: str) -> bool:
    """
    Check if a version specification is satisfied by a given version string.
    
    This function validates whether a given version string satisfies the constraints
    specified in a PEP-440 compliant version specifier string.
    
    Parameters
    ----------
    spec : str
        A PEP-440 compliant version specifier string that defines version constraints.
        Examples include: ">=3.6", "<=3.5", ">3.2, <4.0", "==3.8.*", "~=3.7.0".
        Multiple specifiers can be combined with commas.
    version : str
        The version string to check against the specification. Should be a valid
        version string according to PEP-440, such as "3.8.0", "2.7.18", or "3.9.1".
    
    Returns
    -------
    bool
        True if the version satisfies the specification, False otherwise.
    
    Raises
    ------
    InvalidSpecifier
        If the spec parameter contains an invalid version specifier format.
    InvalidVersion
        If the version parameter is not a valid version string format.
    
    Notes
    -----
    This function follows PEP-440 (Python Package Index version identification
    and dependency specification) for both version parsing and specifier matching.
    Invalid inputs are not converted to `False`; their parsing exceptions propagate.
    
    Examples
    --------
    Basic version comparisons:
        is_allowed_version('<=3.5', '3.3')  # Returns True
        is_allowed_version('<=3.2', '3.3')  # Returns False
    
    Complex version specifications:
        is_allowed_version('>3.2, <4.0', '3.3')  # Returns True
        is_allowed_version('>=2.7, !=3.0.*, !=3.1.*', '2.7.18')  # Returns True
    """
    # <your code>
```

Remember, **the interface template above is extremely important**. You must generate callable interfaces strictly according to the specified requirements, as this will directly determine whether you can pass our tests. If your implementation has incorrect naming or improper input/output formats, it may directly result in a 0% pass rate for this case.
