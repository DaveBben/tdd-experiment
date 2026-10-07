## Task
**Task Statement: Restore Four Pydantic Compatibility Helpers**

Restore Pydantic-v1 `get_model_fields` and its no-op
`with_info_plain_validator_function`, plus the cross-version `_get_model_config` and
`_is_model_field` compatibility helpers. The first returns the model's ordered v1 field
definitions, the validator-schema shim accepts its compatibility arguments but returns
`{}`, and the two main-module helpers recognize the applicable v1/v2 representation.
Broader schema generation,
validation, serialization, caching, and annotation analysis are outside these four helpers.

## Interface Descriptions

### Interface Description 1
Below is **Interface Description 1**

Path: `/testbed/fastapi/_compat/v1.py`
```python
def get_model_fields(model: Type[BaseModel]) -> List[ModelField]:
    """
    Extract all model fields from a Pydantic BaseModel class.
    
    This function retrieves all field definitions from a Pydantic model class and returns
    them as a list of ModelField objects, preserving model field-definition order.
    
    Parameters:
        model (Type[BaseModel]): A Pydantic BaseModel class (not an instance) from which
                               to extract the field definitions.
    
    Returns:
        List[ModelField]: A list of ModelField objects representing all fields defined
                         in the model. Each ModelField contains metadata about the field
                         including its name, type, validation rules, default values, and
                         other field-specific configuration.
    
    Notes:
        - This function is designed to work with Pydantic V1 models and uses the V1
          compatibility layer when running with Pydantic V2
        - The returned ModelField objects contain comprehensive information about each
          field's configuration, validation rules, and type annotations
        - This function expects a model class, not a model instance
    """
    # <your code>

def with_info_plain_validator_function(
    function: Callable[..., Any],
    *,
    ref: Union[str, None] = None,
    metadata: Any = None,
    serialization: Any = None,
) -> Any:
    """
    Provide the Pydantic-v1 compatibility shim for a plain validator schema.
    
    This compatibility implementation accepts the same callable and optional schema
    arguments as its counterpart, ignores them, and returns an empty dictionary.
    
    Args:
        function (Callable[..., Any]): Accepted for signature compatibility and ignored.
        ref (Union[str, None], optional): Accepted and ignored. Defaults to None.
        metadata (Any, optional): Accepted and ignored. Defaults to None.
        serialization (Any, optional): Accepted and ignored. Defaults to None.
    
    Returns:
        Any: An empty dictionary ({}).
    
    Note:
        No validator is wrapped and no metadata is stored by the Pydantic-v1 shim.
    """
    # <your code>
```

### Interface Description 2
Below is **Interface Description 2**

Path: `/testbed/fastapi/_compat/main.py`
```python
def _get_model_config(model: BaseModel) -> Any:
    """
    Retrieve the configuration object from a Pydantic BaseModel instance.
    
    This function acts as a compatibility layer that handles both Pydantic v1 and v2 models
    for both Pydantic v1 and v2 model instances.
    
    Args:
        model (BaseModel): A Pydantic BaseModel instance from which to extract the configuration.
                          Can be either a Pydantic v1 or v2 model instance.
    
    Returns:
        Any: The model's configuration object. The exact type and structure depends on the
             Pydantic version:
             - For Pydantic v1: Returns the model's Config class or configuration dict
             - For Pydantic v2: Returns the model's ConfigDict or configuration object
    
    Notes:
        - This function automatically detects the Pydantic version of the input model
        - The function may return None if no configuration is found or if the model
          type is not recognized
        - This is an internal function used for maintaining compatibility across
          different Pydantic versions in FastAPI
    """
    # <your code>

def _is_model_field(value: Any) -> bool:
    """
    Check if a given value is a ModelField instance from either Pydantic v1 or v2.
    
    This function provides compatibility checking across different versions of Pydantic by
    determining whether the provided value is a ModelField from either supported
    Pydantic generation.
    
    Parameters:
        value (Any): The value to check for being a ModelField instance.
    
    Returns:
        bool: True if the value is a ModelField instance from either Pydantic v1 or v2,
              False otherwise.
    
    Notes:
        - This function handles version compatibility between Pydantic v1 and v2
        - Pydantic-v2 fields are recognized when v2 support is active
        - Returns False if the value is not a ModelField instance from any supported version
    """
    # <your code>
```

Remember, **the interface template above is extremely important**. You must generate callable interfaces strictly according to the specified requirements, as this will directly determine whether you can pass our tests. If your implementation has incorrect naming or improper input/output formats, it may directly result in a 0% pass rate for this case.
