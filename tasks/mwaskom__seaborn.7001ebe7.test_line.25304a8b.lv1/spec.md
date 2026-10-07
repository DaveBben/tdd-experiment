## Task
**Task Statement: Dodge Positioning, Path Rendering, and Continuous Scale Setup**

Implement the listed interfaces for `Dodge`, `Paths`, and `ContinuousBase`.
They group and reposition marks, render grouped path segments and legend artists
with matplotlib, and configure a continuous scale pipeline. For normalized
properties, the pipeline applies an affine normalization relative to data-derived
or explicit bounds; values outside those bounds are not clipped to `[0, 1]`.

## Interface Descriptions

### Interface Description 1
Below is **Interface Description 1**

Path: `/testbed/seaborn/_core/moves.py`
```python
@dataclass
class Dodge(Move):
    """
    
        Displacement and narrowing of overlapping marks along orientation axis.
    
        Parameters
        ----------
        empty : {'keep', 'drop', 'fill'}
        gap : float
            Size of gap between dodged marks.
        by : list of variable names
            Variables to apply the movement to, otherwise use all.
    
        Examples
        --------
        .. include:: ../docstrings/objects.Dodge.rst
    
        
    """
    empty: str = 'keep'
    gap: float = 0
    by: Optional[list[str]] = None

    def __call__(self, data: DataFrame, groupby: GroupBy, orient: str, scales: dict[str, Scale]) -> DataFrame:
        # <your code>
```

Additional information:
- Dodging is computed independently for each spatial position and facet.
- Within a group, non-missing widths retain their relative proportions and their
  filled output widths sum to the largest filled input width.
- The `empty` policy controls whether missing groups are kept, dropped, or treated
  as zero-width groups. Kept missing groups use the group's mean width.
- The resulting marks are placed next to one another without overlap and the whole
  group remains centered on its original position.

### Interface Description 2
Below is **Interface Description 2**

Path: `/testbed/seaborn/_marks/line.py`
```python
@document_properties
@dataclass
class Paths(Mark):
    """
    
        A faster but less-flexible mark for drawing many paths.
    
        See also
        --------
        Path : A mark connecting data points in the order they appear.
    
        Examples
        --------
        .. include:: ../docstrings/objects.Paths.rst
    
        
    """
    color: MappableColor = Mappable('C0')
    alpha: MappableFloat = Mappable(1)
    linewidth: MappableFloat = Mappable(rc='lines.linewidth')
    linestyle: MappableString = Mappable(rc='lines.linestyle')
    _sort: ClassVar[bool] = False

    def _legend_artist(self, variables, value, scales):
        """
        Create a legend artist for the Paths mark.
        
        This method generates a matplotlib Line2D artist that represents the visual
        appearance of the Paths mark in a legend. The artist is configured with
        the resolved visual properties (color, linewidth, linestyle) based on the
        provided variables and values.
        
        Parameters
        ----------
        variables : list or sequence
            The variable names that are being represented in the legend entry.
        value : scalar
            The specific value for the legend entry that determines the visual
            properties of the artist.
        scales : dict
            A mapping of scale objects used to resolve the visual properties
            from the raw values.
        
        Returns
        -------
        matplotlib.lines.Line2D
            A Line2D artist with empty data ([], []) but configured with the
            appropriate visual properties for legend display. The artist includes
            color, linewidth, and linestyle properties resolved from the scales.
        
        Notes
        -----
        The returned Line2D artist has no actual data points (empty x and y arrays)
        since it is only used for legend display. Solid and dashed lines use a
        consistent cap style.
        """
        # <your code>

    def _plot(self, split_gen, scales, orient):
        """
        Render multiple path segments as a LineCollection on matplotlib axes.
        
        This method processes data splits to create path segments and renders them efficiently
        using matplotlib's LineCollection. It handles property resolution, color mapping,
        and data sorting based on the orientation axis.
        
        Parameters
        ----------
        split_gen : callable
            Produces an iterable of `(keys, data, ax)` tuples for each data split.
            - keys: Dictionary of grouping variable values for the current split
            - data: DataFrame containing x, y coordinates for the path
            - ax: matplotlib Axes object to draw on
        scales : dict
            Dictionary mapping variable names to scale objects used for property resolution
            and color transformation.
        orient : str
            The orientation axis ("x" or "y") used for sorting data when _sort is True.
        
        Returns
        -------
        None
            This method modifies the axes in-place by adding LineCollection artists.
        
        Notes
        -----
        - Uses LineCollection for efficient rendering of multiple path segments
        - Automatically handles data limits update due to matplotlib issue #23129
        - Properties like color, linewidth, and linestyle are resolved per data split
        - When _sort is True, data is sorted along the orientation axis before plotting
        - The capstyle follows the configured artist properties or matplotlib default
        - All segments in a single axes share the same capstyle, even for dashed lines
        """
        # <your code>
```

### Interface Description 3
Below is **Interface Description 3**

Path: `/testbed/seaborn/_core/scales.py`
```python
@dataclass
class ContinuousBase(Scale):
    values: tuple | str | None = None
    norm: tuple | None = None

    def _setup(self, data: Series, prop: Property, axis: Axis | None = None) -> Scale:
        # <your code>
```

Remember, **the interface template above is extremely important**. You must generate callable interfaces strictly according to the specified requirements, as this will directly determine whether you can pass our tests. If your implementation has incorrect naming or improper input/output formats, it may directly result in a 0% pass rate for this case.
