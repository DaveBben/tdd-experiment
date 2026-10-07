## Task
**Task Statement: Numeric Representation Helpers**

Restore two helpers in `sympy/core/numbers.py`: convert a finite
`decimal.Decimal` to an exact SymPy number together with its stored coefficient-digit
count, and recognize the supported literal integer representations (Python integers,
SymPy ``Integer``, supported ground-integer backends, built-in `float`, and SymPy
`Float`). Non-finite decimals must be rejected,
and unsupported value types must not be treated as integer-valued.

## Interface Descriptions

### Interface Description 1
Below is **Interface Description 1**

Path: `/testbed/sympy/core/numbers.py`
```python
def _decimal_to_Rational_prec(dec):
    """
    Convert an ordinary decimal instance to a Rational.
    
    This function takes a decimal.Decimal instance and converts it to a SymPy Rational
    number while preserving the precision information from the original decimal.
    
    Parameters
    ----------
    dec : decimal.Decimal
        A finite decimal number to be converted. Must be a finite decimal (not NaN or infinity).
    
    Returns
    -------
    tuple[Rational, int]
        A tuple containing the exact SymPy ``Integer`` or ``Rational`` value and the
        number of digits in the Decimal's stored coefficient. Trailing coefficient
        zeros count toward this number.
    
    Raises
    ------
    TypeError
        If the input decimal is not finite (i.e., if it's NaN or infinity).
    
    Notes
    -----
    A non-negative decimal exponent produces a SymPy ``Integer``. A negative exponent
    is represented exactly and normalized as a SymPy rational number, which can itself
    simplify to an ``Integer``. The accompanying count describes the Decimal
    representation rather than the current decimal context precision.
    
    Examples
    --------
    For a decimal like 3.14:
    - Returns (Rational(157, 50), 3)
    
    For a decimal like 42 (integer):
    - Returns (Integer(42), 2) since there are 2 significant digits
    """
    # <your code>

def int_valued(x):
    """
    Check if a value has an integer representation.
    
    This function determines whether a supported literal numeric value represents an
    integer with no fractional part.
    
    Parameters
    ----------
    x : int, float, Integer, Float, or other numeric type
        The value to check for integer representation.
    
    Returns
    -------
    bool
        True if the value represents an integer (has no fractional part),
        False otherwise.
    
    Notes
    -----
    Python integer objects (including subclasses), SymPy ``Integer`` objects, and the
    supported ground-integer backend values return ``True``. Built-in ``float`` and
    SymPy ``Float`` values return ``True`` only when their literal representation is
    integral. All other types return ``False``.
    
    The function only checks if the value literally represents an integer,
    not whether it could be simplified to one. For example, it checks the
    internal binary representation rather than performing mathematical
    evaluation.
    
    Examples
    --------
    Basic integer types return True:
    
    Floats with no fractional part return True:
    
    Values with fractional parts return False:
    
    Non-numeric types return False:
    """
    # <your code>
```

Remember, **the interface template above is extremely important**. You must generate callable interfaces strictly according to the specified requirements, as this will directly determine whether you can pass our tests. If your implementation has incorrect naming or improper input/output formats, it may directly result in a 0% pass rate for this case.
