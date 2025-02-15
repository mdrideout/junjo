import graphviz

from junjo.graph import Graph


def graph_to_graphviz_image(
        graph: Graph,
        output_filename: str = "graph",
        engine: str = "dot",
        format: str = "png"
    ) -> None:
    """Renders a junjo Graph to an image via dot notation intermediary."""

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

