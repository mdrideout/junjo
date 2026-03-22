import graphviz

from junjo.graph import Graph


def graph_to_graphviz_image(
        graph: Graph,
        output_filename: str = "graph",
        engine: str = "dot",
        format: str = "png"
    ) -> None:
    """
    Render a Junjo graph to an image through a DOT-notation intermediary.

    :param graph: The graph to render.
    :type graph: Graph
    :param output_filename: The filename stem for the rendered output.
    :type output_filename: str
    :param engine: The Graphviz engine to use, such as ``dot``.
    :type engine: str
    :param format: The image format to render, such as ``png`` or ``svg``.
    :type format: str
    :raises ImportError: If the optional ``graphviz`` dependency is not
        installed.
    :raises RuntimeError: If Graphviz rendering fails for another reason.
    """

    dot_code = graph.to_dot_notation()

    try:
        dot = graphviz.Source(dot_code, engine=engine, format=format)
        dot.render(output_filename, cleanup=True)
        print(f"Graphviz image saved to {output_filename}.{format}")
    except ImportError as e:
        raise ImportError(
            "The 'graphviz' package is required to render DOT code to images."
            "Please install it using 'pip install junjo[graphviz]'"
        ) from e
    except Exception as e:
        raise RuntimeError(f"Error rendering DOT code using Graphviz: {e}") from e
