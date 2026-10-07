## Task
**Task Statement: Expose the Optional Secret on an MLflow Webhook Entity**

**Core Functionalities:**
- Provide read-only access to the optional secret supplied when a `Webhook` entity is constructed
- Preserve the security boundary of REST/protocol responses, which do not return webhook secrets

**Main Features & Requirements:**
- Return the directly constructed entity's secret value, or None when no secret is present
- Return None for webhook entities reconstructed from REST/protocol responses, even when a secret
  was supplied in the create request

**Key Challenges:**
- Keep direct entity construction behavior distinct from server responses that intentionally omit secrets
- Avoid inventing or recovering a secret that is not present in the protocol representation

## Interface Descriptions

### Interface Description 1
Below is **Interface Description 1**

Path: `/testbed/mlflow/entities/webhook.py`
```python
class Webhook:
    """
    
        MLflow entity for Webhook.
        
    """

    @property
    def secret(self) -> str | None:
        """
        Get the secret value stored on this Webhook entity.
        
        This property exposes the optional secret supplied when the entity was directly constructed.
        
        Returns:
            str | None: The value supplied when this entity object was constructed, or None.
        
        Notes:
            - Webhook protocol/REST responses do not expose the secret. Entities reconstructed
              from those responses therefore report None even when a secret was supplied in the
              create request.
            - Directly constructing `Webhook(..., secret=...)` retains and exposes that value.
        """
        # <your code>
```

Remember, **the interface template above is extremely important**. You must generate callable interfaces strictly according to the specified requirements, as this will directly determine whether you can pass our tests. If your implementation has incorrect naming or improper input/output formats, it may directly result in a 0% pass rate for this case.
