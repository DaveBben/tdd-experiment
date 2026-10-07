## Task
**Task Statement: Dataset Identification and Tracking Interface**

Implement the base dataset identity, naming, source, and serialization interface used by MLflow Tracking. The core functionality involves:

1. **Dataset Identification**: Compute or retain a compact digest/fingerprint for a dataset
2. **Dataset Naming**: Provide human-readable names for datasets with fallback defaults
3. **Source Integration**: Work with various dataset sources while maintaining consistent identification

**Key Requirements:**
- Automatic digest computation for dataset fingerprinting
- Flexible naming with default fallbacks
- Integration with MLflow tracking systems
- Support for serialization and metadata management

**Main Challenges:**
- Following the recommended compact digest length without promising collision-free identity
- Treating the digest as an initialization-time fingerprint rather than a live view of later source mutations

## Interface Descriptions

### Interface Description 1
Below is **Interface Description 1**

Path: `/testbed/mlflow/data/dataset.py`
```python
class Dataset:
    """
    
        Represents a dataset for use with MLflow Tracking, including the name, digest (hash),
        schema, and profile of the dataset as well as source information (e.g. the S3 bucket or
        managed Delta table from which the dataset was derived). Most datasets expose features
        and targets for training and evaluation as well.
        
    """

    def __init__(self, source: DatasetSource, name: str | None = None, digest: str | None = None):
        """Initialize a dataset with its source and optional identity metadata.

        If ``digest`` is falsy (including None or an empty string), compute it with the subclass's
        ``_compute_digest()``. Subclasses should call this constructor only after initializing the
        state needed for that computation. If ``name`` is None, ``name`` falls back to ``"dataset"``.
        """
        # <your code>

    def to_dict(self) -> dict[str, str]:
        """Return the base dataset configuration with ``name``, ``digest``, serialized ``source``, and ``source_type`` entries."""
        # <your code>

    @property
    def digest(self) -> str:
        """
        A compact hash or fingerprint of the dataset, e.g. ``"498c7496"``.
        
        This property returns the stored dataset fingerprint. It is computed during initialization
        when the supplied digest is falsy; the base class does not guarantee collision-free uniqueness.
        
        Returns:
            str: A string digest representing the dataset fingerprint. The digest is typically
                 8-10 characters long and serves as a compact identifier.
        
        Notes:
            - The digest is computed once during dataset initialization and then returned unchanged
            - If a falsy digest is provided during construction, it is computed using the
              dataset's ``_compute_digest()`` method
            - Digests can be used to compare separately constructed or logged dataset snapshots;
              the stored value is not recomputed when source state later mutates
        """
        # <your code>

    @property
    def name(self) -> str:
        """
        The name of the dataset, e.g. ``"iris_data"``, ``"myschema.mycatalog.mytable@v1"``, etc.
        
        This property returns the dataset's name if one was provided during initialization,
        otherwise returns the default name ``"dataset"``.
        
        Returns:
            str: The name of the dataset. If no name was specified during dataset creation,
                 returns the default value ``"dataset"``.
        
        Note:
            The name is typically used for identification and logging purposes in MLflow
            tracking. It should be descriptive enough to distinguish this dataset from
            others in your MLflow experiments.
        """
        # <your code>
```

### Interface Description 2

Path: `/testbed/mlflow/data/dataset_source.py`
```python
class DatasetSource:
    def to_json(self) -> str:
        """Serialize this source's ``to_dict()`` representation as a JSON string."""
        # <your code>
```

Remember, **the interface template above is extremely important**. You must generate callable interfaces strictly according to the specified requirements, as this will directly determine whether you can pass our tests. If your implementation has incorrect naming or improper input/output formats, it may directly result in a 0% pass rate for this case.
