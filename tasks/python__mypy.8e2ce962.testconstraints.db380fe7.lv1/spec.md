## Task
**Task Statement: Type Constraint Equality**

Implement `Constraint.__eq__` in `mypy/constraints.py`. A `Constraint` is equal only to another `Constraint` whose `type_var`, `op`, and `target` attributes are all equal; comparisons with other object types must return `False`. The existing hash implementation already uses these same three attributes and should remain consistent with the equality behavior.

## Interface Descriptions

### Interface Description 1
Below is **Interface Description 1**

Path: `/testbed/mypy/constraints.py`
```python
class Constraint:
    """
    A representation of a type constraint.
    
        It can be either T <: type or T :> type (T is a type variable).
        
    """
    type_var: TypeVarId
    op = 0
    target: Type

    def __eq__(self, other: object) -> bool:
        """
        Check equality between two Constraint objects.
        
        Two constraints are considered equal if they have the same type variable ID,
        the same operation (SUBTYPE_OF or SUPERTYPE_OF), and the same target type.
        
        Parameters:
            other: The object to compare against. Can be any type, but only Constraint
                   objects can be equal to this constraint.
        
        Returns:
            bool: True if the other object is a Constraint with identical type_var,
                  op, and target attributes; False otherwise.
        
        Notes:
            Equality is structural over exactly these three attributes. Instances of
            `Constraint` subclasses participate in the same comparison; unrelated
            object types compare unequal.
        """
        # <your code>
```

Remember, **the interface template above is extremely important**. You must generate callable interfaces strictly according to the specified requirements, as this will directly determine whether you can pass our tests. If your implementation has incorrect naming or improper input/output formats, it may directly result in a 0% pass rate for this case.
