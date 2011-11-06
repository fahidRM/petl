"""
TODO doc me

"""

from itertools import islice, groupby
from collections import deque, defaultdict
from operator import itemgetter


from petl.util import close, asindices, rowgetter, FieldSelectionError, asdict
import re

__all__ = ['rename', 'project', 'cat', 'convert', 'translate', 'extend', 'rowslice', \
           'head', 'tail', 'sort', 'melt', 'recast', 'duplicates', 'conflicts', \
           'merge', 'select', 'complement', 'diff', 'capture', \
           'split', 'fieldmap']


def rename(table, spec=dict()):
    """
    Replace one or more fields in the table's header row. E.g.::

        >>> from petl import look, rename
        >>> tbl1 = [['sex', 'age'],
        ...         ['M', 12],
        ...         ['F', 34],
        ...         ['-', 56]]
        >>> tbl2 = rename(tbl1, {'sex': 'gender', 'age': 'age_years'})
        >>> look(tbl2)
        +----------+-------------+
        | 'gender' | 'age_years' |
        +==========+=============+
        | 'M'      | 12          |
        +----------+-------------+
        | 'F'      | 34          |
        +----------+-------------+
        | '-'      | 56          |
        +----------+-------------+

    The returned table object can also be used to modify the field mapping, 
    using the suffix notation, e.g.::
    
        >>> tbl1 = [['sex', 'age'],
        ...         ['M', 12],
        ...         ['F', 34],
        ...         ['-', 56]]
        >>> tbl2 = rename(tbl1)
        >>> look(tbl2)
        +-------+-------+
        | 'sex' | 'age' |
        +=======+=======+
        | 'M'   | 12    |
        +-------+-------+
        | 'F'   | 34    |
        +-------+-------+
        | '-'   | 56    |
        +-------+-------+
        
        >>> tbl2['sex'] = 'gender'
        >>> look(tbl2)
        +----------+-------+
        | 'gender' | 'age' |
        +==========+=======+
        | 'M'      | 12    |
        +----------+-------+
        | 'F'      | 34    |
        +----------+-------+
        | '-'      | 56    |
        +----------+-------+

    """
    
    return RenameView(table, spec)


class RenameView(object):
    
    def __init__(self, table, spec=dict()):
        self.source = table
        self.spec = spec
        
    def __iter__(self):
        return iterrename(self.source, self.spec)
    
    def __setitem__(self, key, value):
        self.spec[key] = value
        
    def __getitem__(self, key):
        return self.spec[key]
    
    
def iterrename(source, spec):
    it = iter(source)
    spec = spec.copy() # make sure nobody can change this midstream
    try:
        sourceflds = it.next()
        newflds = [spec[f] if f in spec else f for f in sourceflds]
        yield newflds
        for row in it:
            yield row
    finally:
        close(it)
        
        
def project(table, *args, **kwargs):
    """
    Choose and/or re-order columns. E.g.::

        >>> from petl import look, project    
        >>> table1 = [['foo', 'bar', 'baz'],
        ...           ['A', 1, 2.7],
        ...           ['B', 2, 3.4],
        ...           ['B', 3, 7.8],
        ...           ['D', 42, 9.0],
        ...           ['E', 12]]
        >>> table2 = project(table1, 'foo', 'baz')
        >>> look(table2)
        +-------+-------+
        | 'foo' | 'baz' |
        +=======+=======+
        | 'A'   | 2.7   |
        +-------+-------+
        | 'B'   | 3.4   |
        +-------+-------+
        | 'B'   | 7.8   |
        +-------+-------+
        | 'D'   | 9.0   |
        +-------+-------+
        | 'E'   | None  |
        +-------+-------+

    Note that any short rows will be padded with `None` values (or whatever is
    provided via the `padding` keyword argument).
    
    Fields can also be specified by index, starting from zero. E.g.::

        >>> table3 = project(table1, 0, 2)
        >>> look(table3)
        +-------+-------+
        | 'foo' | 'baz' |
        +=======+=======+
        | 'A'   | 2.7   |
        +-------+-------+
        | 'B'   | 3.4   |
        +-------+-------+
        | 'B'   | 7.8   |
        +-------+-------+
        | 'D'   | 9.0   |
        +-------+-------+
        | 'E'   | None  |
        +-------+-------+

    Field names and indices can be mixed, e.g.::

        >>> table4 = project(table1, 'bar', 0)
        >>> look(table4)
        +-------+-------+
        | 'bar' | 'foo' |
        +=======+=======+
        | 1     | 'A'   |
        +-------+-------+
        | 2     | 'B'   |
        +-------+-------+
        | 3     | 'B'   |
        +-------+-------+
        | 42    | 'D'   |
        +-------+-------+
        | 12    | 'E'   |
        +-------+-------+

    Use the standard :func:`range` runction to select a range of fields, e.g.::
    
        >>> table5 = project(table1, *range(0, 2))
        >>> look(table5)    
        +-------+-------+
        | 'foo' | 'bar' |
        +=======+=======+
        | 'A'   | 1     |
        +-------+-------+
        | 'B'   | 2     |
        +-------+-------+
        | 'B'   | 3     |
        +-------+-------+
        | 'D'   | 42    |
        +-------+-------+
        | 'E'   | 12    |
        +-------+-------+

    """
    
    return ProjectView(table, args, **kwargs)


class ProjectView(object):
    
    def __init__(self, source, spec, missing=None):
        self.source = source
        self.spec = spec
        self.padding = missing
        
    def __iter__(self):
        return iterproject(self.source, self.spec, self.padding)
        
        
def iterproject(source, spec, missing=None):
    it = iter(source)
    spec = tuple(spec) # make sure no-one can change midstream
    try:
        
        # convert field selection into field indices
        flds = it.next()
        indices = asindices(flds, spec)

        # define a function to transform each row in the source data 
        # according to the field selection
        transform = rowgetter(*indices)
        
        # yield the transformed field names
        yield transform(flds)
        
        # construct the transformed data
        for row in it:
            try:
                yield transform(row) 
            except IndexError:
                # row is short, let's be kind and fill in any padding fields
                yield [row[i] if i < len(row) else missing for i in indices]

    finally:
        close(it)
    
    
def cat(*tables, **kwargs):
    """
    Concatenate data from two or more tables. Note that the tables do not need
    to share exactly the same fields, any padding fields will be padded with
    `None` (or whatever is provided via the `padding` keyword argument). E.g.::

        >>> from petl import look, cat    
        >>> table1 = [['foo', 'bar'],
        ...           [1, 'A'],
        ...           [2, 'B']]
        >>> table2 = [['bar', 'baz'],
        ...           ['C', True],
        ...           ['D', False]]
        >>> table3 = cat(table1, table2)
        >>> look(table3)
        +-------+-------+-------+
        | 'foo' | 'bar' | 'baz' |
        +=======+=======+=======+
        | 1     | 'A'   | None  |
        +-------+-------+-------+
        | 2     | 'B'   | None  |
        +-------+-------+-------+
        | None  | 'C'   | True  |
        +-------+-------+-------+
        | None  | 'D'   | False |
        +-------+-------+-------+

    This function can also be used to square up a table with uneven rows, e.g.::

        >>> table = [['foo', 'bar', 'baz'],
        ...          ['A', 1, 2],
        ...          ['B', '2', '3.4'],
        ...          [u'B', u'3', u'7.8', True],
        ...          ['D', 'xyz', 9.0],
        ...          ['E', None]]
        >>> look(cat(table))
        +-------+-------+--------+
        | 'foo' | 'bar' | 'baz'  |
        +=======+=======+========+
        | 'A'   | 1     | 2      |
        +-------+-------+--------+
        | 'B'   | '2'   | '3.4'  |
        +-------+-------+--------+
        | u'B'  | u'3'  | u'7.8' |
        +-------+-------+--------+
        | 'D'   | 'xyz' | 9.0    |
        +-------+-------+--------+
        | 'E'   | None  | None   |
        +-------+-------+--------+

    """
    
    return CatView(tables, **kwargs)
    
    
class CatView(object):
    
    def __init__(self, sources, missing=None):
        self.sources = sources
        self.padding = missing

    def __iter__(self):
        return itercat(self.sources, self.padding)
    

def itercat(sources, missing=None):
    its = [iter(t) for t in sources]
    try:
        
        # determine output flds by gathering all flds found in the sources
        source_flds_lists = [it.next() for it in its]
        out_flds = list()
        for flds in source_flds_lists:
            for f in flds:
                if f not in out_flds:
                    # add any new flds as we find them
                    out_flds.append(f)
        yield out_flds

        # output data rows
        for source_index, it in enumerate(its):
            flds = source_flds_lists[source_index]
            
            # let's define a function which will, for any row and field name,
            # return the corresponding value, or fill in any padding values
            def get_value(row, f):
                try:
                    value = row[flds.index(f)]
                except ValueError: # source does not have f in flds
                    value = missing
                except IndexError: # row is short
                    value = missing
                return value
            
            # now construct and yield the data rows
            for row in it:
                out_row = [get_value(row, f) for f in out_flds]
                yield out_row

    finally:
        # make sure all iterators are closed
        for it in its:
            close(it)
    
    
def convert(table, converters=dict(), errorvalue=None):
    """
    Transform values in invidual fields. E.g.::

        >>> from petl import convert, look    
        >>> table1 = [['foo', 'bar'],
        ...           ['1', '2.4'],
        ...           ['3', '7.9'],
        ...           ['7', '2'],
        ...           ['8.3', '42.0'],
        ...           ['2', 'abc']]
        >>> table2 = convert(table1, {'foo': int, 'bar': float})
        >>> look(table2)
        +-------+-------+
        | 'foo' | 'bar' |
        +=======+=======+
        | 1     | 2.4   |
        +-------+-------+
        | 3     | 7.9   |
        +-------+-------+
        | 7     | 2.0   |
        +-------+-------+
        | None  | 42.0  |
        +-------+-------+
        | 2     | None  |
        +-------+-------+

    Converter functions can also be specified by using the suffix notation on the
    returned table object. E.g.::

        >>> table1 = [['foo', 'bar', 'baz'],
        ...           ['1', '2.4', 14],
        ...           ['3', '7.9', 47],
        ...           ['7', '2', 11],
        ...           ['8.3', '42.0', 33],
        ...           ['2', 'abc', 'xyz']]
        >>> table2 = convert(table1)
        >>> look(table2)
        +-------+--------+-------+
        | 'foo' | 'bar'  | 'baz' |
        +=======+========+=======+
        | '1'   | '2.4'  | 14    |
        +-------+--------+-------+
        | '3'   | '7.9'  | 47    |
        +-------+--------+-------+
        | '7'   | '2'    | 11    |
        +-------+--------+-------+
        | '8.3' | '42.0' | 33    |
        +-------+--------+-------+
        | '2'   | 'abc'  | 'xyz' |
        +-------+--------+-------+
        
        >>> table2['foo'] = int
        >>> table2['bar'] = float
        >>> table2['baz'] = lambda v: v**2
        >>> look(table2)
        +-------+-------+-------+
        | 'foo' | 'bar' | 'baz' |
        +=======+=======+=======+
        | 1     | 2.4   | 196   |
        +-------+-------+-------+
        | 3     | 7.9   | 2209  |
        +-------+-------+-------+
        | 7     | 2.0   | 121   |
        +-------+-------+-------+
        | None  | 42.0  | 1089  |
        +-------+-------+-------+
        | 2     | None  | None  |
        +-------+-------+-------+

    """
    
    return ConvertView(table, converters, errorvalue)


class ConvertView(object):
    
    def __init__(self, source, converters=dict(), errorvalue=None):
        self.source = source
        self.converters = converters
        self.errorvalue = errorvalue
        
    def __iter__(self):
        return iterconvert(self.source, self.converters, self.errorvalue)
    
    def __setitem__(self, key, value):
        self.converters[key] = value
        
    def __getitem__(self, key):
        return self.converters[key]
    
    
def iterconvert(source, converters, errorvalue):
    it = iter(source)
    converters = converters.copy()
    try:
        
        # grab the fields in the source table
        flds = it.next()
        yield flds # these are not modified
        
        # define a function to transform a value
        def transform_value(i, v):
            try:
                f = flds[i]
            except IndexError:
                # row is long, just return value as-is
                return v
            else:
                try:
                    c = converters[f]
                except KeyError:
                    # no converter defined on this field, return value as-is
                    return v
                else:
                    try:
                        return c(v)
                    except ValueError:
                        return errorvalue
                    except TypeError:
                        return errorvalue

        # construct the data rows
        for row in it:
            yield [transform_value(i, v) for i, v in enumerate(row)]

    finally:
        close(it)
            

def translate(table, field, dictionary=dict()):
    """
    Translate values in a given field using a dictionary. E.g.::
    
        >>> from petl import translate, look
        >>> table1 = [['gender', 'age'],
        ...           ['M', 12],
        ...           ['F', 34],
        ...           ['-', 56]]
        >>> table2 = translate(table1, 'gender', {'M': 'male', 'F': 'female'})
        >>> look(table2)
        +----------+-------+
        | 'gender' | 'age' |
        +==========+=======+
        | 'male'   | 12    |
        +----------+-------+
        | 'female' | 34    |
        +----------+-------+
        | '-'      | 56    |
        +----------+-------+

    """
    
    return TranslateView(table, field, dictionary)


class TranslateView(object):
    
    def __init__(self, source, field, dictionary=dict()):
        self.source = source
        self.field = field
        self.dictionary = dictionary
        
    def __iter__(self):
        return itertranslate(self.source, self.field, self.dictionary)


def itertranslate(source, field, dictionary):
    it = iter(source)
    dictionary = dictionary.copy()
    try:
        
        flds = it.next()
        yield flds 
        
        if field in flds:
            index = flds.index(field)
        elif isinstance(field, int) and field < len(flds):
            index = field
        else:
            raise FieldSelectionError(field)
        
        for row in it:
            row = list(row) # copy, so we don't modify the source
            value = row[index]
            if value in dictionary:
                row[index] = dictionary[value]
            yield row
            
    finally:
        close(it)
        
        
def extend(table, field, value):
    """
    Extend a table with a fixed value or calculated field. E.g., using a fixed
    value::
    
        >>> from petl import extend, look
        >>> table1 = [['foo', 'bar'],
        ...           ['M', 12],
        ...           ['F', 34],
        ...           ['-', 56]]
        >>> table2 = extend(table1, 'baz', 42)
        >>> look(table2)
        +-------+-------+-------+
        | 'foo' | 'bar' | 'baz' |
        +=======+=======+=======+
        | 'M'   | 12    | 42    |
        +-------+-------+-------+
        | 'F'   | 34    | 42    |
        +-------+-------+-------+
        | '-'   | 56    | 42    |
        +-------+-------+-------+

    E.g., calculating the value::
    
        >>> table1 = [['foo', 'bar'],
        ...           ['M', 12],
        ...           ['F', 34],
        ...           ['-', 56]]
        >>> table2 = extend(table1, 'baz', lambda rec: rec['bar'] * 2)
        >>> look(table2)
        +-------+-------+-------+
        | 'foo' | 'bar' | 'baz' |
        +=======+=======+=======+
        | 'M'   | 12    | 24    |
        +-------+-------+-------+
        | 'F'   | 34    | 68    |
        +-------+-------+-------+
        | '-'   | 56    | 112   |
        +-------+-------+-------+

    When using a calculated value, the function should accept a record, i.e., a
    dictionary representation of the row, with values indexed by field name.
    
    """
    
    return ExtendView(table, field, value)


class ExtendView(object):
    
    def __init__(self, source, field, value):
        self.source = source
        self.field = field
        self.value = value
        
    def __iter__(self):
        return iterextend(self.source, self.field, self.value)


def iterextend(source, field, value):
    it = iter(source)
    try:
        flds = it.next()
        out_flds = list(flds)
        out_flds.append(field)
        yield out_flds

        for row in it:
            out_row = list(row) # copy so we don't modify source
            if callable(value):
                rec = asdict(flds, row)
                out_row.append(value(rec))
            else:
                out_row.append(value)
            yield out_row
    finally:
        close(it)
        
    
def rowslice(table, start=0, stop=None, step=1):
    """
    Choose a subset of data rows. E.g.::
    
        >>> from petl import rowslice, look
        >>> table1 = [['foo', 'bar'],
        ...           ['a', 1],
        ...           ['b', 2],
        ...           ['c', 5],
        ...           ['d', 7],
        ...           ['f', 42]]
        >>> table2 = rowslice(table1, 0, 2)
        >>> look(table2)
        +-------+-------+
        | 'foo' | 'bar' |
        +=======+=======+
        | 'a'   | 1     |
        +-------+-------+
        | 'b'   | 2     |
        +-------+-------+
        
        >>> table3 = rowslice(table1, 1, 4)
        >>> look(table3)
        +-------+-------+
        | 'foo' | 'bar' |
        +=======+=======+
        | 'b'   | 2     |
        +-------+-------+
        | 'c'   | 5     |
        +-------+-------+
        | 'd'   | 7     |
        +-------+-------+
        
        >>> table4 = rowslice(table1, 0, 5, 2)
        >>> look(table4)
        +-------+-------+
        | 'foo' | 'bar' |
        +=======+=======+
        | 'a'   | 1     |
        +-------+-------+
        | 'c'   | 5     |
        +-------+-------+
        | 'f'   | 42    |
        +-------+-------+
        
        >>> table5 = rowslice(table1, step=2)
        >>> look(table5)
        +-------+-------+
        | 'foo' | 'bar' |
        +=======+=======+
        | 'a'   | 1     |
        +-------+-------+
        | 'c'   | 5     |
        +-------+-------+
        | 'f'   | 42    |
        +-------+-------+

    """
    
    return RowSliceView(table, start, stop, step)


class RowSliceView(object):
    
    def __init__(self, source, start=0, stop=None, step=1):
        self.source = source
        self.start = start
        self.stop = stop
        self.step = step
        
    def __iter__(self):
        return iterrowslice(self.source, self.start, self.stop, self.step)


def iterrowslice(source, start, stop, step):    
    it = iter(source)
    try:
        yield it.next() # fields
        for row in islice(it, start, stop, step):
            yield row
    finally:
        close(it)


def head(table, n):
    """
    Choose the first n rows. E.g.::

        >>> from petl import head, look    
        >>> table1 = [['foo', 'bar'],
        ...           ['a', 1],
        ...           ['b', 2],
        ...           ['c', 5],
        ...           ['d', 7],
        ...           ['f', 42],
        ...           ['f', 3],
        ...           ['h', 90],
        ...           ['k', 12],
        ...           ['l', 77],
        ...           ['q', 2]]
        >>> table2 = head(table1, 4)
        >>> look(table2)    
        +-------+-------+
        | 'foo' | 'bar' |
        +=======+=======+
        | 'a'   | 1     |
        +-------+-------+
        | 'b'   | 2     |
        +-------+-------+
        | 'c'   | 5     |
        +-------+-------+
        | 'd'   | 7     |
        +-------+-------+
    
    """
    
    return rowslice(table, stop=n)

        
def tail(table, n):
    """
    Choose the last n rows. E.g.::

        >>> from petl import tail, look    
        >>> table1 = [['foo', 'bar'],
        ...           ['a', 1],
        ...           ['b', 2],
        ...           ['c', 5],
        ...           ['d', 7],
        ...           ['f', 42],
        ...           ['f', 3],
        ...           ['h', 90],
        ...           ['k', 12],
        ...           ['l', 77],
        ...           ['q', 2]]
        >>> table2 = tail(table1, 4)
        >>> look(table2)    
        +-------+-------+
        | 'foo' | 'bar' |
        +=======+=======+
        | 'h'   | 90    |
        +-------+-------+
        | 'k'   | 12    |
        +-------+-------+
        | 'l'   | 77    |
        +-------+-------+
        | 'q'   | 2     |
        +-------+-------+

    """

    return TailView(table, n)


class TailView(object):
    
    def __init__(self, source, n):
        self.source = source
        self.n = n
        
    def __iter__(self):
        return itertail(self.source, self.n)


def itertail(source, n):
    it = iter(source)
    try:
        yield it.next() # fields
        cache = deque()
        for row in it:
            cache.append(row)
            if len(cache) > n:
                cache.popleft()
        for row in cache:
            yield row
    finally:
        close(it)


def sort(table, key=None, reverse=False):
    """
    Sort the table. E.g.::
    
        >>> from petl import sort, look
        >>> table1 = [['foo', 'bar'],
        ...           ['C', 2],
        ...           ['A', 9],
        ...           ['A', 6],
        ...           ['F', 1],
        ...           ['D', 10]]
        >>> table2 = sort(table1, 'foo')
        >>> look(table2)
        +-------+-------+
        | 'foo' | 'bar' |
        +=======+=======+
        | 'A'   | 9     |
        +-------+-------+
        | 'A'   | 6     |
        +-------+-------+
        | 'C'   | 2     |
        +-------+-------+
        | 'D'   | 10    |
        +-------+-------+
        | 'F'   | 1     |
        +-------+-------+

    Sorting by compound key is supported, e.g.::
    
        >>> table3 = sort(table1, key=['foo', 'bar'])
        >>> look(table3)
        +-------+-------+
        | 'foo' | 'bar' |
        +=======+=======+
        | 'A'   | 6     |
        +-------+-------+
        | 'A'   | 9     |
        +-------+-------+
        | 'C'   | 2     |
        +-------+-------+
        | 'D'   | 10    |
        +-------+-------+
        | 'F'   | 1     |
        +-------+-------+

    Field names or indices (from zero) can be used to specify the key.
    
    If no key is specified, the default is a lexical sort, e.g.::

        >>> table4 = sort(table1)
        >>> look(table4)
        +-------+-------+
        | 'foo' | 'bar' |
        +=======+=======+
        | 'A'   | 6     |
        +-------+-------+
        | 'A'   | 9     |
        +-------+-------+
        | 'C'   | 2     |
        +-------+-------+
        | 'D'   | 10    |
        +-------+-------+
        | 'F'   | 1     |
        +-------+-------+
        
    TODO currently this sorts data in memory, need to add option to limit
    memory usage and merge sort from chunks on disk

    """
    
    return SortView(table, key, reverse)
    
    
class SortView(object):
    
    def __init__(self, source, key=None, reverse=False):
        self.source = source
        self.key = key
        self.reverse = reverse
        
    def __iter__(self):
        return itersort(self.source, self.key, self.reverse)
    

def itersort(source, key, reverse):
    it = iter(source)
    try:
        flds = it.next()
        yield flds
        
        # TODO merge sort on large dataset!!!
        rows = list(it)

        if key is not None:

            # convert field selection into field indices
            indices = asindices(flds, key)
             
            # now use field indices to construct a getkey function
            # N.B., this will probably raise an exception on short rows
            getkey = itemgetter(*indices)

            rows.sort(key=getkey, reverse=reverse)

        else:
            rows.sort(reverse=reverse)

        for row in rows:
            yield row
        
    finally:
        close(it)
    
    
def melt(table, key=[], variables=[], variable_field='variable', value_field='value'):
    """
    Reshape a table, melting fields into data. E.g.::

        >>> from petl import melt, look
        >>> table1 = [['id', 'gender', 'age'],
        ...           [1, 'F', 12],
        ...           [2, 'M', 17],
        ...           [3, 'M', 16]]
        >>> table2 = melt(table1, 'id')
        >>> look(table2)
        +------+------------+---------+
        | 'id' | 'variable' | 'value' |
        +======+============+=========+
        | 1    | 'gender'   | 'F'     |
        +------+------------+---------+
        | 1    | 'age'      | 12      |
        +------+------------+---------+
        | 2    | 'gender'   | 'M'     |
        +------+------------+---------+
        | 2    | 'age'      | 17      |
        +------+------------+---------+
        | 3    | 'gender'   | 'M'     |
        +------+------------+---------+
        | 3    | 'age'      | 16      |
        +------+------------+---------+

    Compound keys are supported, e.g.::
    
        >>> table3 = [['id', 'time', 'height', 'weight'],
        ...           [1, 11, 66.4, 12.2],
        ...           [2, 16, 53.2, 17.3],
        ...           [3, 12, 34.5, 9.4]]
        >>> table4 = melt(table3, key=['id', 'time'])
        >>> look(table4)
        +------+--------+------------+---------+
        | 'id' | 'time' | 'variable' | 'value' |
        +======+========+============+=========+
        | 1    | 11     | 'height'   | 66.4    |
        +------+--------+------------+---------+
        | 1    | 11     | 'weight'   | 12.2    |
        +------+--------+------------+---------+
        | 2    | 16     | 'height'   | 53.2    |
        +------+--------+------------+---------+
        | 2    | 16     | 'weight'   | 17.3    |
        +------+--------+------------+---------+
        | 3    | 12     | 'height'   | 34.5    |
        +------+--------+------------+---------+
        | 3    | 12     | 'weight'   | 9.4     |
        +------+--------+------------+---------+

    A subset of variable fields can be selected, e.g.::
    
        >>> table5 = melt(table3, key=['id', 'time'], variables=['height'])    
        >>> look(table5)
        +------+--------+------------+---------+
        | 'id' | 'time' | 'variable' | 'value' |
        +======+========+============+=========+
        | 1    | 11     | 'height'   | 66.4    |
        +------+--------+------------+---------+
        | 2    | 16     | 'height'   | 53.2    |
        +------+--------+------------+---------+
        | 3    | 12     | 'height'   | 34.5    |
        +------+--------+------------+---------+

    """
    
    return MeltView(table, key, variables, variable_field, value_field)
    
    
class MeltView(object):
    
    def __init__(self, source, key=[], variables=[], 
                 variable_field='variable', value_field='value'):
        self.source = source
        self.key = key
        self.variables = variables
        self.variable_field = variable_field
        self.value_field = value_field
        
    def __iter__(self):
        return itermelt(self.source, self.key, self.variables, 
                        self.variable_field, self.value_field)
    
    
def itermelt(source, key, variables, variable_field, value_field):
    it = iter(source)
    try:
        
        # normalise some stuff
        flds = it.next()
        if isinstance(key, basestring):
            key = (key,) # normalise to a tuple
        if isinstance(variables, basestring):
            # shouldn't expect this, but ... ?
            variables = (variables,) # normalise to a tuple
        if not key:
            # assume key is flds not in variables
            key = [f for f in flds if f not in variables]
        if not variables:
            # assume variables are flds not in key
            variables = [f for f in flds if f not in key]
        
        # determine the output flds
        out_flds = list(key)
        out_flds.append(variable_field)
        out_flds.append(value_field)
        yield out_flds
        
        key_indices = [flds.index(k) for k in key]
        getkey = rowgetter(*key_indices)
        variables_indices = [flds.index(v) for v in variables]
        
        # construct the output data
        for row in it:
            k = getkey(row)
            for v, i in zip(variables, variables_indices):
                o = list(k) # populate with key values initially
                o.append(v) # add variable
                o.append(row[i]) # add value
                yield o
                
    finally:
        close(it)



def recast(table, key=[], variable_field='variable', value_field='value', 
           sample_size=1000, reduce=dict(), missing=None):
    """
    Recast molten data. E.g.::
    
        >>> from petl import recast, look
        >>> table1 = [['id', 'variable', 'value'],
        ...           [3, 'age', 16],
        ...           [1, 'gender', 'F'],
        ...           [2, 'gender', 'M'],
        ...           [2, 'age', 17],
        ...           [1, 'age', 12],
        ...           [3, 'gender', 'M']]
        >>> table2 = recast(table1)
        >>> look(table2)
        +------+-------+----------+
        | 'id' | 'age' | 'gender' |
        +======+=======+==========+
        | 1    | 12    | 'F'      |
        +------+-------+----------+
        | 2    | 17    | 'M'      |
        +------+-------+----------+
        | 3    | 16    | 'M'      |
        +------+-------+----------+

    If variable and value fields are different from the defaults, e.g.::
    
        >>> table3 = [['id', 'vars', 'vals'],
        ...           [3, 'age', 16],
        ...           [1, 'gender', 'F'],
        ...           [2, 'gender', 'M'],
        ...           [2, 'age', 17],
        ...           [1, 'age', 12],
        ...           [3, 'gender', 'M']]
        >>> table4 = recast(table3, variable_field='vars', value_field='vals')
        >>> look(table4)
        +------+-------+----------+
        | 'id' | 'age' | 'gender' |
        +======+=======+==========+
        | 1    | 12    | 'F'      |
        +------+-------+----------+
        | 2    | 17    | 'M'      |
        +------+-------+----------+
        | 3    | 16    | 'M'      |
        +------+-------+----------+

    If there are multiple values for each key/variable pair, and no reduce
    function is provided, then all values will be listed. E.g.::
    
        >>> table6 = [['id', 'time', 'variable', 'value'],
        ...           [1, 11, 'weight', 66.4],
        ...           [1, 14, 'weight', 55.2],
        ...           [2, 12, 'weight', 53.2],
        ...           [2, 16, 'weight', 43.3],
        ...           [3, 12, 'weight', 34.5],
        ...           [3, 17, 'weight', 49.4]]
        >>> table7 = recast(table6, key='id')
        >>> look(table7)
        +------+--------------+
        | 'id' | 'weight'     |
        +======+==============+
        | 1    | [66.4, 55.2] |
        +------+--------------+
        | 2    | [53.2, 43.3] |
        +------+--------------+
        | 3    | [34.5, 49.4] |
        +------+--------------+

    Multiple values can be reduced via an aggregation function, e.g.::

        >>> def mean(values):
        ...     return float(sum(values)) / len(values)
        ... 
        >>> table8 = recast(table6, key='id', reduce={'weight': mean})
        >>> look(table8)    
        +------+--------------------+
        | 'id' | 'weight'           |
        +======+====================+
        | 1    | 60.800000000000004 |
        +------+--------------------+
        | 2    | 48.25              |
        +------+--------------------+
        | 3    | 41.95              |
        +------+--------------------+

    Missing values are padded with whatever is provided via the `padding` 
    keyword argument (`None` by default), e.g.::

        >>> table9 = [['id', 'variable', 'value'],
        ...           [1, 'gender', 'F'],
        ...           [2, 'age', 17],
        ...           [1, 'age', 12],
        ...           [3, 'gender', 'M']]
        >>> table10 = recast(table9, key='id')
        >>> look(table10)
        +------+-------+----------+
        | 'id' | 'age' | 'gender' |
        +======+=======+==========+
        | 1    | 12    | 'F'      |
        +------+-------+----------+
        | 2    | 17    | None     |
        +------+-------+----------+
        | 3    | None  | 'M'      |
        +------+-------+----------+

    """
    
    return RecastView(table, key, variable_field, value_field, sample_size, reduce, missing)
    

class RecastView(object):
    
    def __init__(self, source, key=[], variable_field='variable', 
                 value_field='value', sample_size=1000, reduce=dict(), 
                 missing=None):
        self.source = source
        self.key = key
        self.variable_field = variable_field
        self.value_field = value_field
        self.sample_size = sample_size
        self.reduce = reduce
        self.padding = missing
        
    def __iter__(self):
        return iterrecast(self.source, self.key, self.variable_field, 
                          self.value_field, self.sample_size, self.reduce,
                          self.padding)


def iterrecast(source, key=[], variable_field='variable', value_field='value', 
               sample_size=1000, reduce=dict(), missing=None):        
    #
    # TODO implementing this by making two passes through the data is a bit
    # ugly, and could be costly if there are several upstream transformations
    # that would need to be re-executed each pass - better to make one pass,
    # caching the rows sampled to discover variables to be recast as fields?
    #
    
    try:
        
        it = iter(source)
        fields = it.next()
        
        # normalise some stuff
        key_fields = key
        variable_fields = variable_field # N.B., could be more than one
        if isinstance(key_fields, basestring):
            key_fields = (key_fields,)
        if isinstance(variable_fields, basestring):
            variable_fields = (variable_fields,)
        if not key_fields:
            # assume key_fields is fields not in variables
            key_fields = [f for f in fields if f not in variable_fields and f != value_field]
        if not variable_fields:
            # assume variables are fields not in key_fields
            variable_fields = [f for f in fields if f not in key_fields and f != value_field]
        
        # sanity checks
        assert value_field in fields, 'invalid value field: %s' % value_field
        assert value_field not in key_fields, 'value field cannot be key_fields'
        assert value_field not in variable_fields, 'value field cannot be variable field'
        for f in key_fields:
            assert f in fields, 'invalid key_fields field: %s' % f
        for f in variable_fields:
            assert f in fields, 'invalid variable field: %s' % f

        # we'll need these later
        value_index = fields.index(value_field)
        key_indices = [fields.index(f) for f in key_fields]
        variable_indices = [fields.index(f) for f in variable_fields]
        
        # determine the actual variable names to be cast as fields
        if isinstance(variable_fields, dict):
            # user supplied dictionary
            variables = variable_fields
        else:
            variables = defaultdict(set)
            # sample the data to discover variables to be cast as fields
            for row in islice(it, 0, sample_size):
                for i, f in zip(variable_indices, variable_fields):
                    variables[f].add(row[i])
            for f in variables:
                variables[f] = sorted(variables[f]) # turn from sets to sorted lists
        
        close(it) # finished the first pass
        
        # determine the output fields
        out_fields = list(key_fields)
        for f in variable_fields:
            out_fields.extend(variables[f])
        yield out_fields
        
        # output data
        
        source = sort(source, key=key_fields)
        it = iter(source)
        it = islice(it, 1, None) # skip header row
        getkey = itemgetter(*key_indices)
        
        # process sorted data in newfields
        groups = groupby(it, key=getkey)
        for key_value, group in groups:
            group = list(group) # may need to iterate over the group more than once
            if len(key_fields) > 1:
                out_row = list(key_value)
            else:
                out_row = [key_value]
            for f, i in zip(variable_fields, variable_indices):
                for variable in variables[f]:
                    # collect all values for the current variable
                    values = [r[value_index] for r in group if r[i] == variable]
                    if len(values) == 0:
                        value = missing
                    elif len(values) == 1:
                        value = values[0]
                    else:
                        if variable in reduce:
                            redu = reduce[variable]
                        else:
                            redu = list # list all values
                        value = redu(values)
                    out_row.append(value)
            yield out_row
                    
    finally:
        close(it)

    
        
            
def duplicates(table, key, presorted=False):
    """
    Select rows with duplicate values under a given key. E.g.::

        >>> from petl import duplicates, look    
        >>> table1 = [['foo', 'bar', 'baz'],
        ...           ['A', 1, 2.0],
        ...           ['B', 2, 3.4],
        ...           ['D', 6, 9.3],
        ...           ['B', 3, 7.8],
        ...           ['B', 2, 12.3],
        ...           ['E', None, 1.3],
        ...           ['D', 4, 14.5]]
        >>> table2 = duplicates(table1, 'foo')
        >>> look(table2)
        +-------+-------+-------+
        | 'foo' | 'bar' | 'baz' |
        +=======+=======+=======+
        | 'B'   | 2     | 3.4   |
        +-------+-------+-------+
        | 'B'   | 3     | 7.8   |
        +-------+-------+-------+
        | 'B'   | 2     | 12.3  |
        +-------+-------+-------+
        | 'D'   | 6     | 9.3   |
        +-------+-------+-------+
        | 'D'   | 4     | 14.5  |
        +-------+-------+-------+

    Compound keys are supported, e.g.::
    
        >>> table3 = duplicates(table1, key=['foo', 'bar'])
        >>> look(table3)
        +-------+-------+-------+
        | 'foo' | 'bar' | 'baz' |
        +=======+=======+=======+
        | 'B'   | 2     | 3.4   |
        +-------+-------+-------+
        | 'B'   | 2     | 12.3  |
        +-------+-------+-------+

    """
    
    return DuplicatesView(table, key, presorted)


class DuplicatesView(object):
    
    def __init__(self, source, key, presorted=False):
        if presorted:
            self.source = source
        else:
            self.source = sort(source, key)
        self.key = key
        
    def __iter__(self):
        return iterduplicates(self.source, self.key)


def iterduplicates(source, key):
    # assume source is sorted
    # first need to sort the data
    it = iter(source)

    try:
        flds = it.next()
        yield flds

        # convert field selection into field indices
        indices = asindices(flds, key)
            
        # now use field indices to construct a getkey function
        # N.B., this may raise an exception on short rows, depending on
        # the field selection
        getkey = itemgetter(*indices)
        
        previous = None
        previous_yielded = False
        
        for row in it:
            if previous is None:
                previous = row
            else:
                kprev = getkey(previous)
                kcurr = getkey(row)
                if kprev == kcurr:
                    if not previous_yielded:
                        yield previous
                        previous_yielded = True
                    yield row
                else:
                    # reset
                    previous_yielded = False
                previous = row
        
    finally:
        close(it)

    
    
    
def conflicts(table, key, missing=None, presorted=False):
    """
    Select rows with the same key value but differing in some other field. E.g.::

        >>> from petl import conflicts, look    
        >>> table1 = [['foo', 'bar', 'baz'],
        ...           ['A', 1, 2.7],
        ...           ['B', 2, None],
        ...           ['D', 3, 9.4],
        ...           ['B', None, 7.8],
        ...           ['E', None],
        ...           ['D', 3, 12.3],
        ...           ['A', 2, None]]
        >>> table2 = conflicts(table1, 'foo')
        >>> look(table2)
        +-------+-------+-------+
        | 'foo' | 'bar' | 'baz' |
        +=======+=======+=======+
        | 'A'   | 1     | 2.7   |
        +-------+-------+-------+
        | 'A'   | 2     | None  |
        +-------+-------+-------+
        | 'D'   | 3     | 9.4   |
        +-------+-------+-------+
        | 'D'   | 3     | 12.3  |
        +-------+-------+-------+

    Missing values are not considered conflicts. By default, `None` is treated
    as the padding value, this can be changed via the `padding` keyword 
    argument.
    
    """
    
    return ConflictsView(table, key, missing, presorted)


class ConflictsView(object):
    
    def __init__(self, source, key, missing=None, presorted=False):
        if presorted:
            self.source = source
        else:
            self.source = sort(source, key)
        self.key = key
        self.padding = missing
        
        
    def __iter__(self):
        return iterconflicts(self.source, self.key, self.padding)
    
    
def iterconflicts(source, key, missing):
    it = iter(source)
    try:
        flds = it.next()
        yield flds

        # convert field selection into field indices
        indices = asindices(flds, key)
                        
        # now use field indices to construct a getkey function
        # N.B., this may raise an exception on short rows, depending on
        # the field selection
        getkey = itemgetter(*indices)
        
        previous = None
        previous_yielded = False
        
        for row in it:
            if previous is None:
                previous = row
            else:
                kprev = getkey(previous)
                kcurr = getkey(row)
                if kprev == kcurr:
                    # is there a conflict?
                    conflict = False
                    for x, y in zip(previous, row):
                        if missing not in (x, y) and x != y:
                            conflict = True
                            break
                    if conflict:
                        if not previous_yielded:
                            yield previous
                            previous_yielded = True
                        yield row
                else:
                    # reset
                    previous_yielded = False
                previous = row
        
    finally:
        close(it)


def merge(table, key, missing=None, presorted=False):
    """
    Merge rows with duplicate values under a given key. E.g.::
    
        >>> from petl import merge, look    
        >>> table1 = [['foo', 'bar', 'baz'],
        ...           ['A', 1, 2.7],
        ...           ['B', 2, None],
        ...           ['D', 3, 9.4],
        ...           ['B', None, 7.8],
        ...           ['E', None],
        ...           ['D', 3, 12.3],
        ...           ['A', 2, None]]
        >>> table2 = merge(table1, 'foo')
        >>> look(table2)
        +-------+-------+-------+
        | 'foo' | 'bar' | 'baz' |
        +=======+=======+=======+
        | 'A'   | 2     | 2.7   |
        +-------+-------+-------+
        | 'B'   | 2     | 7.8   |
        +-------+-------+-------+
        | 'D'   | 3     | 12.3  |
        +-------+-------+-------+
        | 'E'   | None  |       |
        +-------+-------+-------+

    Any conflicts are resolved by selecting the later value. Missing values are 
    not considered conflicts, and are overridden by non-padding values. 
    
    """
    
    return MergeView(table, key, missing, presorted)


class MergeView(object):
    
    def __init__(self, source, key, missing=None, presorted=False):
        if presorted:
            self.source = source
        else:
            self.source = sort(source, key)
        self.key = key
        self.padding = missing

    def __iter__(self):
        return itermerge(self.source, self.key, self.padding)
    
    
def itermerge(source, key, missing):
    it = iter(source)

    try:
        flds = it.next()
        yield flds

        # convert field selection into field indices
        indices = asindices(flds, key)
        
        # now use field indices to construct a getkey function
        # N.B., this may raise an exception on short rows, depending on
        # the field selection
        getkey = itemgetter(*indices)
        
        previous = None
        
        for row in it:
            if previous is None:
                previous = row
            else:
                kprev = getkey(previous)
                kcurr = getkey(row)
                if kprev == kcurr:
                    merge = list()
                    for i, v in enumerate(row):
                        try:
                            if v is not missing:
                                # last wins
                                merge.append(v)
                            else:
                                merge.append(previous[i])
                        except IndexError: # previous row is short
                            merge.append(v)
                    previous = merge
                else:
                    yield previous
                    previous = row
        # return the last one
        yield previous
        
    finally:
        close(it)


def complement(a, b, presorted=False):
    """
    Return rows in `a` that are not in `b`. E.g.::
    
        >>> from petl import complement, look
        >>> a = [['foo', 'bar', 'baz'],
        ...      ['A', 1, True],
        ...      ['C', 7, False],
        ...      ['B', 2, False],
        ...      ['C', 9, True]]
        >>> b = [['x', 'y', 'z'],
        ...      ['B', 2, False],
        ...      ['A', 9, False],
        ...      ['B', 3, True],
        ...      ['C', 9, True]]
        >>> aminusb = complement(a, b)
        >>> look(aminusb)
        +-------+-------+-------+
        | 'foo' | 'bar' | 'baz' |
        +=======+=======+=======+
        | 'A'   | 1     | True  |
        +-------+-------+-------+
        | 'C'   | 7     | False |
        +-------+-------+-------+
        
        >>> bminusa = complement(b, a)
        >>> look(bminusa)
        +-----+-----+-------+
        | 'x' | 'y' | 'z'   |
        +=====+=====+=======+
        | 'A' | 9   | False |
        +-----+-----+-------+
        | 'B' | 3   | True  |
        +-----+-----+-------+

    """
    
    return ComplementView(a, b, presorted)


class ComplementView(object):
    
    def __init__(self, a, b, presorted=False):
        if presorted:
            self.a = a
            self.b = b
        else:
            self.a = sort(a)
            self.b = sort(b)
            
    def __iter__(self):
        return itercomplement(self.a, self.b)


def itercomplement(a, b):
    ita = iter(a) 
    itb = iter(b)
    try:
        aflds = ita.next()
        itb.next() # ignore b fields
        yield aflds
        
        a = ita.next()
        b = itb.next()
        # we want the elements in a that are not in b
        while True:
            if b is None or a < b:
                yield a
                try:
                    a = ita.next()
                except StopIteration:
                    break
            elif a == b:
                try:
                    a = ita.next()
                except StopIteration:
                    break
            else:
                try:
                    b = itb.next()
                except StopIteration:
                    b = None
    finally:
        close(ita)
        close(itb)
        
    
def diff(a, b, presorted=False):
    """
    Find the difference between two tables. Returns a pair of tables, e.g.::
    
        >>> from petl import diff, look
        >>> a = [['foo', 'bar', 'baz'],
        ...      ['A', 1, True],
        ...      ['C', 7, False],
        ...      ['B', 2, False],
        ...      ['C', 9, True]]
        >>> b = [['x', 'y', 'z'],
        ...      ['B', 2, False],
        ...      ['A', 9, False],
        ...      ['B', 3, True],
        ...      ['C', 9, True]]
        >>> added, subtracted = diff(a, b)
        >>> # rows in b not in a
        ... look(added)
        +-----+-----+-------+
        | 'x' | 'y' | 'z'   |
        +=====+=====+=======+
        | 'A' | 9   | False |
        +-----+-----+-------+
        | 'B' | 3   | True  |
        +-----+-----+-------+
        
        >>> # rows in a not in b
        ... look(subtracted)
        +-------+-------+-------+
        | 'foo' | 'bar' | 'baz' |
        +=======+=======+=======+
        | 'A'   | 1     | True  |
        +-------+-------+-------+
        | 'C'   | 7     | False |
        +-------+-------+-------+
        
    Convenient shorthand for ``(complement(b, a), complement(a, b))``.

    """

    if not presorted:    
        a = sort(a)
        b = sort(b)
    added = complement(b, a, presorted=True)
    subtracted = complement(a, b, presorted=True)
    return added, subtracted
    
    
def capture(table, field, pattern, newfields, include_original=False):
    """
    Extend the table with one or more new fields with values captured from an
    existing field via a regular expression. E.g.::

        >>> from petl import capture, look
        >>> table1 = [['id', 'variable', 'value'],
        ...           ['1', 'A1', '12'],
        ...           ['2', 'A2', '15'],
        ...           ['3', 'B1', '18'],
        ...           ['4', 'C12', '19']]
        >>> table2 = capture(table1, 'variable', '(\\w)(\\d)', ['treat', 'time'])
        >>> look(table2)
        +------+---------+---------+--------+
        | 'id' | 'value' | 'treat' | 'time' |
        +======+=========+=========+========+
        | '1'  | '12'    | 'A'     | '1'    |
        +------+---------+---------+--------+
        | '2'  | '15'    | 'A'     | '2'    |
        +------+---------+---------+--------+
        | '3'  | '18'    | 'B'     | '1'    |
        +------+---------+---------+--------+
        | '4'  | '19'    | 'C'     | '1'    |
        +------+---------+---------+--------+

    By default the field on which the capture is performed is omitted. It can
    be included using the `include_original` argument, e.g.::
    
        >>> table3 = capture(table1, 'variable', '(\\w)(\\d)', ['treat', 'time'], include_original=True)
        >>> look(table3)
        +------+------------+---------+---------+--------+
        | 'id' | 'variable' | 'value' | 'treat' | 'time' |
        +======+============+=========+=========+========+
        | '1'  | 'A1'       | '12'    | 'A'     | '1'    |
        +------+------------+---------+---------+--------+
        | '2'  | 'A2'       | '15'    | 'A'     | '2'    |
        +------+------------+---------+---------+--------+
        | '3'  | 'B1'       | '18'    | 'B'     | '1'    |
        +------+------------+---------+---------+--------+
        | '4'  | 'C12'      | '19'    | 'C'     | '1'    |
        +------+------------+---------+---------+--------+

    """
    
    return CaptureView(table, field, pattern, newfields, include_original)


class CaptureView(object):
    
    def __init__(self, source, field, pattern, newfields, include_original):
        self.source = source
        self.field = field
        self.pattern = pattern
        self.newfields = newfields
        self.include_original = include_original
        
    def __iter__(self):
        return itercapture(self.source, self.field, self.pattern, self.newfields, self.include_original)


def itercapture(source, field, pattern, newfields, include_original):
    it = iter(source)
    try:
        prog = re.compile(pattern)
        
        flds = it.next()
        assert field in flds, 'field not found: %s' % field
        field_index = flds.index(field)
        
        # determine output flds
        out_flds = list(flds)
        if not include_original:
            out_flds.remove(field)
        out_flds.extend(newfields)
        yield out_flds
        
        # construct the output data
        for row in it:
            value = row[field_index]
            if include_original:
                out_row = list(row)
            else:
                out_row = [v for i, v in enumerate(row) if i != field_index]
            out_row.extend(prog.search(value).groups()[:len(newfields)])
            yield out_row
            
    finally:
        close(it)
    
        
def split(table, field, pattern, newfields, include_original=False):
    """
    Extend the table with one or more new fields with values generated by 
    splitting an existing value around occurrences of a regular expression. 
    E.g.::

        >>> from petl import split, look
        >>> table1 = [['id', 'variable', 'value'],
        ...           ['1', 'parad1', '12'],
        ...           ['2', 'parad2', '15'],
        ...           ['3', 'tempd1', '18'],
        ...           ['4', 'tempd2', '19']]
        >>> table2 = split(table1, 'variable', 'd', ['variable', 'day'])
        >>> look(table2)
        +------+---------+------------+-------+
        | 'id' | 'value' | 'variable' | 'day' |
        +======+=========+============+=======+
        | '1'  | '12'    | 'para'     | '1'   |
        +------+---------+------------+-------+
        | '2'  | '15'    | 'para'     | '2'   |
        +------+---------+------------+-------+
        | '3'  | '18'    | 'temp'     | '1'   |
        +------+---------+------------+-------+
        | '4'  | '19'    | 'temp'     | '2'   |
        +------+---------+------------+-------+

    """
    
    return SplitView(table, field, pattern, newfields, include_original)


class SplitView(object):
    
    def __init__(self, source, field, pattern, newfields, include_original=False):
        self.source = source
        self.field = field
        self.pattern = pattern
        self.newfields = newfields
        self.include_original = include_original
        
    def __iter__(self):
        return itersplit(self.source, self.field, self.pattern, self.newfields, self.include_original)


def itersplit(source, field, pattern, newfields, include_original):
        
    it = iter(source)
    try:
        
        flds = it.next()
        assert field in flds, 'field not found: %s' % field
        field_index = flds.index(field)
        
        # determine output flds
        out_flds = list(flds)
        if not include_original:
            out_flds.remove(field)
        out_flds.extend(newfields)
        yield out_flds
        
        # construct the output data
        for row in it:
            value = row[field_index]
            if include_original:
                out_row = list(row)
            else:
                out_row = [v for i, v in enumerate(row) if i != field_index]
            out_row.extend(value.split(pattern))
            yield out_row
            
    finally:
        close(it)
        
    
def select(table, where, padding=None):
    """
    Select rows meeting a condition. The `where` condition can be a function
    accepting a record (i.e., a dictionary representation of a row) e.g.::
    
        >>> from petl import select, look     
        >>> table1 = [['foo', 'bar', 'baz'],
        ...           ['a', 4, 9.3],
        ...           ['a', 2, 88.2],
        ...           ['b', 1, 23.3],
        ...           ['c', 8, 42.0],
        ...           ['d', 7, 100.9],
        ...           ['c', 2]]
        >>> table2 = select(table1, lambda rec: rec['foo'] == 'a' and rec['baz'] > 88.1)
        >>> look(table2)
        +-------+-------+-------+
        | 'foo' | 'bar' | 'baz' |
        +=======+=======+=======+
        | 'a'   | 2     | 88.2  |
        +-------+-------+-------+

    The where condition can also be an expression string, e.g.::
    
        >>> table3 = select(table1, "{foo} == 'a' and {baz} > 88.1")
        >>> look(table3)
        +-------+-------+-------+
        | 'foo' | 'bar' | 'baz' |
        +=======+=======+=======+
        | 'a'   | 2     | 88.2  |
        +-------+-------+-------+

    The expression string is converted into a lambda function by prepending
    the string with ``'lambda rec: '``, then replacing anything enclosed in 
    curly braces (e.g., ``"{foo}"``) with a lookup on the record (e.g., 
    ``"rec['foo']"``), then finally calling :func:`eval`.
   
    """
    
    return SelectView(table, where, padding)


class SelectView(object):
    
    def __init__(self, source, where, padding=None):
        self.source = source
        self.where = where
        self.padding = padding
        
        
    def __iter__(self):
        return iterselect(self.source, self.where, self.padding)
    
    
def iterselect(source, where, padding):
    it = iter(source)
    try:
        if isinstance(where, basestring):
            where = asrecfun(where)
        flds = it.next()
        yield flds
        for row in it:
            rec = asdict(flds, row, padding)
            if where(rec):
                yield row
    finally:
        close(it)
        
        
def asrecfun(s):
    prog = re.compile('\{([^}]+)\}')
    def repl(matchobj):
        return "rec['%s']" % matchobj.group(1)
    return eval("lambda rec: " + prog.sub(repl, s))
    
    
def fieldmap(table):
    """
    TODO doc me
    
    """    
    
        