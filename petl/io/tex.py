import io
from petl.compat import next, PY2  


from petl.io.base import getcodec
from petl.io.sources import write_source_from_arg


def totex(  table, source, 
            border_style=None,
            caption=None,
            encoding=None,
            errors='strict',
            label=None, 
            line_terminator='\n',
            position='h!',
            row_separator='\\hline'
            
            ):
    """
        Export a table as Latex to a file

        >>> import petl as etl
        >>> my_table = [['id', 'name], ['1', 'Alice'], ['2', 'Bob']]
        >>> etl.totex(my_table, 'example.tex')
        >>> print(open('example.tex').read())

        \\documentclass{article}
        \\usepackage[utf8]{inputenc}

        \\begin{document}

        \\begin{table}[h!]
        \\centering
        \\begin{tabular}{c|c}
        \\hline
        id&name\\\\
        \\hline
        1&Alice\\\\
        2&Bob\\\\
        \\end{tabular}
        \\end{table}

        \\end{document}
    """

    # main structure & code to deal with encoding obtained from: https://github.com/petl-developers/petl/blob/master/petl/io/html.py
    source = write_source_from_arg(source)
    with source.open('wb') as buf:
        # deal with text encoding
        if PY2:
            codec = getcodec(encoding)
            stream = codec.streamwriter(buf, errors=errors)
        else:
            stream = io.TextIOWrapper(buf,
                    encoding=encoding,
                    errors=errors,
                    newline='')
        
        try:
            iterator = iter(table)
            table_header = next(iterator)
            if border_style is None:
                border_style = '|'.join(['c' for col in table_header])
    
            _write_beginning(stream, table_header, border_style, position, row_separator, line_terminator)
            for row in iterator:
                _write_row(stream, row, line_terminator)
            _write_ending(stream, caption, label, line_terminator)
        
        finally:
            stream.flush()



def _write_beginning(stream, header, border_style, position, row_separator, line_terminator):
    stream.write('\\documentclass{article}' + line_terminator)
    stream.write('\\usepackage[utf8]{inputenc}' + line_terminator + line_terminator) 
    stream.write('\\begin{document}' + line_terminator + line_terminator)

    stream.write('\\begin{table}[' + position + ']' + line_terminator)
    stream.write('\\centering' + line_terminator)
    stream.write('\\begin{tabular}{' + border_style + '}' + line_terminator)

    if row_separator is not None:
        stream.write(row_separator + line_terminator)

    escaped_header = list(map(_escape_characters, header))
    stream.write('&'.join(escaped_header) + '\\\\' + line_terminator)

    if row_separator is not None:
        stream.write(row_separator + line_terminator)


def _write_row(stream, row, line_terminator):
    escaped_row = list(map(_escape_characters, row))
    stream.write('&'.join(escaped_row) + '\\\\' + line_terminator)



def _write_ending(stream, caption, label, line_terminator):
    stream.write('\\end{tabular}' + line_terminator)
    if caption is not None:
        stream.write(f'\\caption{{caption}}{line_terminator}')
    if label is not None:
        stream.write(f'\\label{{label}}{line_terminator}')
    stream.write('\\end{table}' + line_terminator)
    stream.write(line_terminator + '\\end{document}' + line_terminator)


def _escape_characters (text):
    escape_with_backslash = ['&', '$', '#', '%', '_', '{', '}']
    escape_with_other_character = { 
        '<' : '$\langle$',
        '>' : '$\rangle$',
        '\\': '\\textasciibackslash',
        '^' : '\\textasciicircum',
        '~' : '\\textasciitilde',
        '||': '\\|'
    }

    if text is None:
        return ''
    else:
        text = str(text)

    for character in escape_with_other_character:
        text = text.replace(character, escape_with_other_character[character])

    for character in escape_with_backslash:
        text = text.replace(character, f'\\{character}')

    return text

