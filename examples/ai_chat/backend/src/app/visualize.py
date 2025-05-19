from app.workflows.handle_message.graph import handle_message_graph


def main():
    """
    Demonstration visualization options for the sample workflow graph.
    """
    graph_dot_notation_str = handle_message_graph.to_dot_notation()
    print("Graph DOT Notation:\n", graph_dot_notation_str)

    # Export graphviz assets
    handle_message_graph.export_graphviz_assets()


if __name__ == "__main__":
    main()
