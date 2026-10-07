## Task
**Task Statement: Implement Per-Group Sampling**

Implement `GroupBy.sample` so that every group is sampled independently and the result
contains the selected rows with their original labels. The output follows group iteration
order. An empty selected object is returned immediately before argument validation.

## Interface Descriptions

### Interface Description 1
Below is **Interface Description 1**

Path: `/testbed/pandas/core/groupby/groupby.py`
```python
class GroupBy:
    """
    
        Class for grouping and aggregating relational data.
    
        See aggregate, transform, and apply functions on this object.
    
        It's easiest to use obj.groupby(...) to use GroupBy, but you can also do:
    
        ::
    
            grouped = groupby(obj, ...)
    
        Parameters
        ----------
        obj : pandas object
        level : int, default None
            Level of MultiIndex
        groupings : list of Grouping objects
            Most users should ignore this
        exclusions : array-like, optional
            List of columns to exclude
        name : str
            Most users should ignore this
    
        Returns
        -------
        **Attributes**
        groups : dict
            {group name -> group labels}
        len(grouped) : int
            Number of groups
    
        Notes
        -----
        After grouping, see aggregate, apply, and transform functions. Here are
        some other brief notes about usage. When grouping by multiple groups, the
        result index will be a MultiIndex (hierarchical) by default.
    
        Iteration produces (key, group) tuples, i.e. chunking the data by group. So
        you can write code like:
    
        ::
    
            grouped = obj.groupby(keys)
            for key, group in grouped:
                # do something with the data
    
        Function calls on GroupBy, if not specially implemented, "dispatch" to the
        grouped data. So if you group a DataFrame and wish to invoke the std()
        method on each group, you can simply do:
    
        ::
    
            df.groupby(mapper).std()
    
        rather than
    
        ::
    
            df.groupby(mapper).aggregate(np.std)
    
        You can pass arguments to these "wrapped" functions, too.
    
        See the online documentation for full exposition on these topics and much
        more
        
    """
    _grouper: ops.BaseGrouper
    as_index: bool

    @final
    def sample(self, n: int | None = None, frac: float | None = None, replace: bool = False, weights: Sequence | Series | None = None, random_state: RandomState | None = None):
        """
        Return a random sample of items from each group.
        
        You can use `random_state` for reproducibility.
        
        Parameters
        ----------
        n : int, optional
            Number of items to return for each group. Cannot be used with
            `frac` and must be no larger than the smallest group unless
            `replace` is True. Default is one if `frac` is None.
        frac : float, optional
            Fraction of items to return. Cannot be used with `n`.
        replace : bool, default False
            Allow or disallow sampling of the same row more than once.
        weights : list-like, optional
            Default None results in equal probability weighting.
            If passed a list-like then values must have the same length as
            the underlying DataFrame or Series object and will be used as
            sampling probabilities after normalization within each group.
            Values must be non-negative with at least one positive element
            within each group.
        random_state : int, np.ndarray, BitGenerator, np.random.RandomState, np.random.Generator, optional
            If int, NumPy ndarray, or BitGenerator, seed for random number generator.
            If np.random.RandomState or np.random.Generator, use as given.
            Default ``None`` results in sampling with the current state of np.random.
        
            .. versionchanged:: 1.4.0
        
                np.random.Generator objects now accepted
        
        Returns
        -------
        Series or DataFrame
            A new object of same type as caller containing items randomly
            sampled within each group from the caller object.
        
        Raises
        ------
        ValueError
            If both `n` and `frac` are provided.
            If `n` is larger than the smallest group size and `replace` is False.
            If `weights` contains negative values or all values are zero within a group.
        
        Notes
        -----
        This method performs random sampling within each group independently. The sampling
        is done without replacement by default, but can be changed using the `replace`
        parameter. When `weights` are provided, they are normalized within each group
        to create sampling probabilities.
        
        If the selected object is empty, it is returned before `n`, `frac`, weights,
        or random_state are processed, so invalid sampling arguments are not rejected.
        
        See Also
        --------
        DataFrame.sample: Generate random samples from a DataFrame object.
        Series.sample: Generate random samples from a Series object.
        numpy.random.choice: Generate a random sample from a given 1-D numpy array.
        
        
        Select one row at random for each distinct value in column a. The
        `random_state` argument can be used to guarantee reproducibility:
        
        
        Set `frac` to sample fixed proportions rather than counts:
        
        
        Control sample probabilities within groups by setting weights:
        

        Notes:
            - If the grouped selection is empty, return the corresponding empty object before
              processing any arguments.
            - If both `n` and `frac` are omitted, sample one row per group; specifying both is invalid.
              `n` must be a non-negative integer. `frac` must be non-negative, and values greater
              than one require replacement.
            - Series weights are aligned to the selected object's index. Weight vectors must have the
              same length as that object, cannot contain infinities or negative values, and treat NaNs
              as zero. Weights are normalized independently in each group; a group whose weights sum
              to zero is invalid. For sampling without replacement, pandas also rejects a group when
              `sample_size * max(normalized_group_weights) > 1`.
            - `random_state` accepts an integer, NumPy ndarray, BitGenerator, RandomState, Generator,
              or None. A Python list is not accepted despite the broader legacy wording.
            - The number selected from a group is `n`, or `round(frac * group_size)` when using `frac`.
              Sampling is independent per group, while one random state is advanced across the operation.
              Results retain the corresponding original index labels and follow group iteration order.
        """
        # <your code>
```

Remember, **the interface template above is extremely important**. You must generate callable interfaces strictly according to the specified requirements, as this will directly determine whether you can pass our tests. If your implementation has incorrect naming or improper input/output formats, it may directly result in a 0% pass rate for this case.
